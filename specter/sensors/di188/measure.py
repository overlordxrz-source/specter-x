"""DI-188 -> SPECTER-X Measurement adapter.

Two facts are kept deliberately apart, because conflating them is how a
device ends up lying on a screen:

**device connectivity** - is the instrument present and streaming?
    ``DeviceState.CONNECTED`` / ``ABSENT`` / ``BUSY`` / ``ERROR``. This is
    what the HUD's sensor-health row shows.

**measurement validity** - is what the instrument is reading actually a
    measurement? A perfectly healthy DI-188 with nothing plugged into it is
    CONNECTED but its channels are *not* measurements; the readings are ADC
    noise. That distinction lives on the channel, in
    :class:`specter.sensors.di188.stats.ChannelState`.

Acquisition runs on a background thread and publishes bounded snapshots under
a short lock, so the HUD never blocks on the serial port. Nothing here ever
waits on the instrument while the caller is running.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence

from specter.fusion.measurement import Measurement, Provenance
from specter.sensors.base import Health, SensorStatus

from .calibration import CalibrationSet
from .driver import (DI188Driver, DI188Error, find_di188_ports, find_serial_ports,
                     probe_di188_port)
from .stats import ChannelMonitor, ChannelReport, ChannelSpec, ChannelState, default_specs

#: Source key used in SENSOR_LABELS / Provenance.source.
SOURCE = "analog"
#: Sensor id prefix for the provenance chain.
SENSOR_PREFIX = "di188"


class DeviceState(str, Enum):
    """Connectivity of the instrument itself."""

    CONNECTED = "CONNECTED"
    CONNECTING = "CONNECTING"
    SILENT = "SILENT"
    ABSENT = "ABSENT"
    BUSY = "BUSY"
    ERROR = "ERROR"

    @property
    def health(self) -> Health:
        return {
            DeviceState.CONNECTED: Health.OK,
            DeviceState.CONNECTING: Health.DEGRADED,
            DeviceState.BUSY: Health.DEGRADED,
            DeviceState.SILENT: Health.OFFLINE,
            DeviceState.ABSENT: Health.NOT_INSTALLED,
            DeviceState.ERROR: Health.OFFLINE,
        }[self]


@dataclass
class DaqSnapshot:
    """Everything the HUD needs about the DAQ, captured at one instant."""

    device_state: DeviceState = DeviceState.ABSENT
    device_detail: str = ""
    model: str = ""
    serial: str = ""
    port: str = ""
    rate_hz: float = 0.0
    frames: int = 0
    calibration_basis: str = "UNCALIBRATED (nominal)"
    channels: List[ChannelReport] = field(default_factory=list)
    series: Dict[int, List] = field(default_factory=dict)
    updated_at: float = 0.0

    @property
    def connected(self) -> bool:
        return self.device_state is DeviceState.CONNECTED

    @property
    def any_measurement(self) -> bool:
        """True only if at least one channel is actually a measurement."""
        return any(c.state is ChannelState.CONNECTED for c in self.channels)

    def as_dict(self) -> Dict:
        return {
            "device_state": self.device_state.value,
            "device_detail": self.device_detail,
            "model": self.model,
            "serial": self.serial,
            "port": self.port,
            "rate_hz": self.rate_hz,
            "frames": self.frames,
            "calibration_basis": self.calibration_basis,
            "any_measurement": self.any_measurement,
            "channels": [
                {
                    "index": c.index,
                    "label": c.label,
                    "terminal": c.terminal,
                    "state": c.state.value,
                    "is_measurement": c.state.is_measurement,
                    "counts": c.stats.last,
                    "mean_counts": c.stats.mean,
                    "std_counts": c.stats.std,
                    "volts": c.volts,
                    "volts_mean": c.volts_mean,
                    "calibration_basis": c.calibration_basis,
                    "note": c.note,
                }
                for c in self.channels
            ],
        }


class AnalogSource:
    """Runs the DI-188 in the background and publishes bounded snapshots."""

    def __init__(self, port: Optional[str] = None, channels: Sequence[int] = (0, 1, 2, 3),
                 rate: float = 100.0, specs: Optional[Sequence[ChannelSpec]] = None,
                 calibration: Optional[CalibrationSet] = None,
                 log_interval: float = 1.0, history: int = 240,
                 probe_candidates: bool = False,
                 stall_timeout: Optional[float] = None):
        self.port = port
        self.channels = list(channels)
        self.rate = rate
        self.log_interval = log_interval
        self.history = history
        self.probe_candidates = probe_candidates
        self.stall_timeout = stall_timeout
        self.specs = list(specs) if specs else default_specs(max(self.channels) + 1)
        self.calibration = calibration   # None -> derived from the instrument

        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._cancel = threading.Event()
        self._driver: Optional[DI188Driver] = None
        self._device = DeviceState.ABSENT
        self._detail = "not started"
        self._model = ""
        self._serial = ""
        self._port = port or ""
        self._rate_real = rate
        self._frames = 0
        self._monitor = ChannelMonitor(self.specs)
        self._series: Dict[int, deque] = {c: deque(maxlen=history) for c in self.channels}
        self._updated = 0.0
        self._last_log = 0.0

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> "AnalogSource":
        """Spawn the acquisition thread. Returns immediately, never blocks."""
        if self._thread is not None:
            return self
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="specter-di188", daemon=True)
        self._thread.start()
        return self

    def stop(self, timeout: float = 2.0) -> None:
        """Stop acquisition and **always** release the serial port."""
        self._stop.set()
        self._cancel.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        if thread is not None and thread.is_alive():
            driver = self._driver
            if driver is not None:
                driver.force_close()
            thread.join(timeout=timeout)
        if thread is not None and not thread.is_alive():
            self._thread = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
        return False

    # -- acquisition -------------------------------------------------------

    def _set_device(self, state: DeviceState, detail: str) -> None:
        with self._lock:
            self._device = state
            self._detail = detail

    def _run(self) -> None:
        try:
            self._acquire()
        except DI188Error as exc:
            # the instrument stopped sending bytes - that is a dead link, not
            # a configuration error
            text = str(exc).lower()
            state = DeviceState.SILENT if ("silent" in text or "no data" in text) \
                else DeviceState.ERROR
            self._set_device(state, str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            self._set_device(DeviceState.ERROR, f"{type(exc).__name__}: {exc}")

    def _select_port(self) -> Optional[str]:
        """Pick the serial node that really is the DAQ."""
        matched = find_di188_ports()
        if matched:
            return matched[0]
        if not self.probe_candidates:
            return None
        for cand in find_serial_ports():
            if probe_di188_port(cand):
                return cand
        return None

    def _acquire(self) -> None:
        port = self.port or self._select_port()
        if not port:
            self._set_device(DeviceState.ABSENT, "no DI-188 found on USB")
            return
        self._set_device(DeviceState.CONNECTING, f"{port}: opening")
        try:
            driver = DI188Driver(port).open()
            with self._lock:
                self._driver = driver
        except DI188Error as exc:
            # the node exists but could not be opened: almost always another
            # process holds the port (the dashboard, the CLI, a soak run)
            text = str(exc).lower()
            if "pyserial" in text:
                self._set_device(DeviceState.ERROR, f"{port}: pyserial is not installed")
            else:
                self._set_device(DeviceState.BUSY, f"{port}: {exc}")
            return
        except Exception as exc:  # pragma: no cover - defensive
            self._set_device(DeviceState.ERROR, f"{port}: {exc}")
            return

        try:
            self._set_device(DeviceState.CONNECTING, f"{port}: identifying")
            ident = driver.read_identity()
            try:
                device_cal = driver.read_device_calibration()
            except DI188Error:
                device_cal = None
            # If the caller did not supply a calibration, derive the nominal
            # one from the instrument's own front-end profile. It stays
            # UNCALIBRATED either way - this only fixes the volts-per-count.
            if self.calibration is None and device_cal is not None:
                with self._lock:
                    self.calibration = CalibrationSet.nominal(
                        device_cal.profile, self.channels,
                        device_serial=ident.serial_number,
                        device_model=ident.model_name)
            self._set_device(DeviceState.CONNECTING, f"{port}: configuring")
            realised = driver.configure(self.channels, self.rate)
            with self._lock:
                self._detail = f"{ident.model_name} streaming"
                self._model = ident.model_name
                self._serial = ident.serial_number
                self._port = ident.port
                self._rate_real = realised
            driver.start()
            stall = self.stall_timeout
            if stall is None:
                stall = max(5.0, 10.0 / max(self.rate, 1.0))
            for sample in driver.stream(stall_timeout=stall, cancel=self._cancel):
                if self._stop.is_set():
                    break
                with self._lock:
                    if self._device is not DeviceState.CONNECTED:
                        self._device = DeviceState.CONNECTED
                        self._detail = f"{ident.model_name} streaming"
                    self._frames += 1
                    self._monitor.add(sample.values)
                    for i, ch in enumerate(self.channels):
                        if i < len(sample.values):
                            self._series[ch].append((sample.t, float(sample.values[i])))
                    self._updated = time.time()
        finally:
            try:
                driver.close()
            except Exception:
                pass
            with self._lock:
                if self._driver is driver:
                    self._driver = None
            if self._stop.is_set():
                self._set_device(DeviceState.ABSENT, "stopped")

    # -- publishing --------------------------------------------------------

    @property
    def _cal(self) -> CalibrationSet:
        """The calibration in force (possibly derived from the instrument)."""
        if self.calibration is None:
            return CalibrationSet.nominal("unknown", self.channels)
        return self.calibration

    def snapshot(self, series_points: int = 120) -> DaqSnapshot:
        """A bounded, self-contained view of the current state."""
        with self._lock:
            reports = self._monitor.report(self._cal)
            series = {c: list(self._series[c])[-series_points:] for c in self.channels}
            return DaqSnapshot(
                device_state=self._device,
                device_detail=self._detail,
                model=self._model,
                serial=self._serial,
                port=self._port,
                rate_hz=self._rate_real,
                frames=self._frames,
                calibration_basis=self._cal.basis_label(),
                channels=reports,
                series=series,
                updated_at=self._updated,
            )

    def status(self, snap: Optional[DaqSnapshot] = None) -> SensorStatus:
        """Sensor-health row: device connectivity only.

        Measurement validity is deliberately *not* folded into the health
        colour - a connected instrument with floating inputs is ``OK``
        because the instrument is fine; the channel badges say the rest.

        Pass an existing snapshot to avoid taking a second one.
        """
        if snap is None:
            snap = self.snapshot(series_points=0)
        if snap.device_state is DeviceState.CONNECTED:
            floating = sum(1 for c in snap.channels
                           if c.state is not ChannelState.CONNECTED)
            # keep it short: the HUD truncates the detail at 30 characters
            detail = f"{snap.serial[-8:]} | {len(snap.channels)} ch"
            if floating:
                detail += f" | {floating} floating"
            return SensorStatus(SOURCE, "ANALOG DI-188", Health.OK, detail)
        return SensorStatus(SOURCE, "ANALOG DI-188", snap.device_state.health,
                            snap.device_detail[:60])

    def take_measurement(self) -> Optional[Measurement]:
        """One Measurement, rate-limited to ``log_interval`` seconds.

        Returns ``None`` when it is not time yet, so the caller can call this
        every frame without flooding the event log.
        """
        now = time.time()
        if now - self._last_log < self.log_interval:
            return None
        self._last_log = now
        snap = self.snapshot(series_points=0)
        if snap.device_state is not DeviceState.CONNECTED:
            return None

        value = {
            "device": {
                "state": snap.device_state.value,
                "model": snap.model,
                "serial": snap.serial,
                "port": snap.port,
                "rate_hz": snap.rate_hz,
            },
            "calibration_basis": snap.calibration_basis,
            "frames": snap.frames,
            "channels": snap.as_dict()["channels"],
        }
        notes = ("floating inputs are noise, not measurements"
                 if not snap.any_measurement else
                 "volts are nominal/uncertified" if not self._cal.any_calibrated
                 else "calibrated")
        prov = Provenance(
            sensor_id=f"{SENSOR_PREFIX}-{snap.serial or '188'}",
            source=SOURCE,
            algorithm="di188-ascii",
            model_version=None,
            frame_index=snap.frames,
            parents=(),
            notes=notes,
        )
        # confidence stays None: nothing here is a calibrated measurement yet
        return Measurement(
            sensor=SOURCE,
            kind="analog4",
            t_host=now,
            frame_id="daq",
            value=value,
            provenance=prov,
            t_sensor=None,
            confidence=None,
            covariance=None,
        )
