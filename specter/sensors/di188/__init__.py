"""SPECTER-X DI-188 USB data acquisition.

The DI-188 is a 4-channel, +/-10 V differential USB DAQ that enumerates as a
CDC-ACM serial device. This package speaks its documented ASCII protocol.

Sub-modules:

``driver``       serial protocol, device identity, device flash calibration
``calibration``  counts -> volts models (nominal vs measured)
``stats``        running statistics and input-state labelling
``recorder``     CSV recorder with a provenance header
``stability``    long-run link stability harness (dropped frames, stalls)
``dashboard``    lightweight real-time monitoring dashboard (stdlib HTTP)
``measure``      adapter producing SPECTER-X Measurements from the DAQ
"""
from .calibration import CalibrationSet, ChannelCalibration
from .dashboard import Di188Dashboard
from .driver import (DI188Driver, DI188Error, DI188Identity, DeviceCalibration,
                      Sample, find_serial_ports)
from .measure import AnalogSource, DaqSnapshot, DeviceState
from .recorder import CsvRecorder, build_provenance
from .stability import (StabilityReport, run_stability_test,
                       save_stability_report)
from .stats import ChannelMonitor, ChannelSpec, ChannelState, ChannelStats, default_specs

__all__ = [
    "CalibrationSet", "ChannelCalibration", "Di188Dashboard", "DI188Driver",
    "DI188Error", "DI188Identity", "DeviceCalibration", "Sample",
    "find_serial_ports", "CsvRecorder", "build_provenance", "StabilityReport",
    "run_stability_test", "save_stability_report", "ChannelMonitor", "ChannelSpec", "ChannelState",
    "ChannelStats", "default_specs", "AnalogSource", "DaqSnapshot", "DeviceState",
]
