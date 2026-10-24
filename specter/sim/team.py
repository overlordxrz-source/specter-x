"""Two-process-style team simulator (single process, shared bus for CI).

`python -m specter.sim.team --units 2` runs virtual units walking a path:
UWB-sim pairwise ranging, synthetic GNSS fixes, signed Heartbeat /
PoseStamped / TrackReport exchange over the team transport, clock-offset
logging and stale rejection. The CI demo for Stage 4b networking.

All data here is synthetic and labelled SIM — it proves the pipes run, not
that any radio works.
"""
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np

from specter.fusion.measurement import Measurement
from specter.localization.ekf import PoseEKF
from specter.net import (
    BusHub, ClockSync, Heartbeat, PoseStamped, TrackReport,
    UdpMulticastTransport, generate_key,
)
from specter.sensors.gnss.neom9n import SyntheticGnss
from specter.sensors.uwb.dw1000 import UwbSimulator


@dataclass
class VirtualUnit:
    unit_id: str
    transport: UdpMulticastTransport
    ekf: PoseEKF
    gnss: SyntheticGnss
    true_pos: np.ndarray
    true_vel: np.ndarray
    clock: ClockSync = field(default_factory=ClockSync)
    seq: int = 0
    heard: Dict[str, int] = field(default_factory=dict)
    inbox: List = field(default_factory=list)
    track_seq: int = 0

    def step_truth(self, dt: float) -> None:
        self.true_pos = self.true_pos + self.true_vel * dt

    def _next_seq(self) -> int:
        self.seq += 1
        return self.seq

    def broadcast_state(self) -> None:
        pose = self.ekf.pose()
        self.transport.send(Heartbeat(
            self.unit_id, self._next_seq(), time.time(),
            mode=pose.mode, pos_rmse=pose.pos_rmse))
        self.transport.send(PoseStamped(
            self.unit_id, self._next_seq(), time.time(),
            pose.position, pose.velocity, pose.covariance[:3, :3],
            mode=pose.mode,
            anchor=list(pose.anchor) if pose.anchor else None))

    def broadcast_contact(self, contact_enu: np.ndarray, label: str = "contact") -> None:
        """Share a compact local track (never video). SIM-labelled."""
        d = float(np.linalg.norm(contact_enu - self.true_pos))
        if d > 15.0:
            return
        self.track_seq += 1
        sim_mid = f"sim-{self.unit_id}-thermal-{self.track_seq}"
        self.transport.send(TrackReport(
            self.unit_id, self._next_seq(), time.time(), self.track_seq,
            contact_enu, np.eye(3) * (0.5**2),
            source_unit=self.unit_id, source_sensor="thermal",
            measurement_ids=[sim_mid], confidence=0.8, label=label))

    def receive_all(self) -> None:
        for m in self.transport.receive(clock=self.clock):
            self.heard[m.unit_id] = self.heard.get(m.unit_id, 0) + 1
            self.inbox.append(m)


def run_team(units: int = 2, steps: int = 40, dt: float = 0.2,
             seed: int = 5, gnss_on: bool = True) -> Dict:
    """Run the virtual team; return a summary dict (used by tests + CLI)."""
    key = generate_key()
    hub = BusHub()
    uwb = UwbSimulator(seed=seed)
    rng = np.random.default_rng(seed)
    # Team anchor agreed at mission start (unit-1's fix): one shared ENU frame.
    # Each unit's synthetic GNSS walks north from *its own* start offset so
    # fixes stay consistent with UWB truth (no phantom 3 m disagreement).
    team_lat0, team_lon0 = 47.3769, 8.5417
    anchor = (team_lat0, team_lon0, 400.0)
    vu: List[VirtualUnit] = []
    for i in range(units):
        uid = f"unit-{i + 1}"
        hub.register(uid)  # membership upfront: no step-1 message loss
        ekf = PoseEKF(uid, allow_simulated=True)
        ekf.anchor = anchor
        vu.append(VirtualUnit(
            unit_id=uid,
            transport=UdpMulticastTransport(key=key, hub=hub, unit_id=uid,
                                            loopback_only=True),
            ekf=ekf,
            gnss=SyntheticGnss(lat0=team_lat0, lon0=team_lon0, seed=seed + i),
            true_pos=np.array([i * 3.0, 0.0, 0.0]),
            true_vel=np.array([0.9 + 0.05 * i, 0.15 * (1 if i % 2 == 0 else -1), 0.0]),
        ))
    contact = np.array([12.0, 4.0, 0.0])  # static "victim" the team should share
    tracks_shared = 0
    for _ in range(steps):
        truth = {u.unit_id: u.true_pos.copy() for u in vu}
        ranges = uwb.ranging(truth)
        for u in vu:
            u.step_truth(dt)
            u.ekf.predict(dt)
            if gnss_on:
                # GNSS follows this unit's truth: fixes stay consistent with ranges.
                u.ekf.update_gnss(u.gnss.read_at(float(u.true_pos[0]),
                                                 float(u.true_pos[1]), dt))
            pose = u.ekf.pose()
            for m in ranges[u.unit_id]:
                peer = m.value["peer_id"]
                u.ekf.update_range(m, truth[peer], np.eye(3) * 0.5)
            u.broadcast_state()
            before = len(u.inbox)
            u.broadcast_contact(contact)
            _ = before
        for u in vu:
            u.receive_all()
        tracks_shared += sum(
            1 for u in vu for m in u.inbox if getattr(m, "type", "") == "track")
        _ = rng  # deterministic motion already; rng reserved for drop models
    summary = {
        "units": units, "steps": steps, "sim": True,
        "heard": {u.unit_id: dict(u.heard) for u in vu},
        "modes": {u.unit_id: u.ekf.pose().mode for u in vu},
        "rmse": {u.unit_id: round(float(u.ekf.pose().pos_rmse), 3) for u in vu},
        "final_enu": {u.unit_id: [round(float(v), 2) for v in u.ekf.pose().position]
                      for u in vu},
        "tracks_seen": {u.unit_id: sum(1 for m in u.inbox
                                       if getattr(m, "type", "") == "track")
                        for u in vu},
        "offsets": {u.unit_id: {p: round(u.clock.offset(p), 4) for p in u.heard}
                    for u in vu},
    }
    for u in vu:
        u.transport.close()
    return summary


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="specter.sim.team",
                                description="Virtual team walk (SIM — CI demo)")
    p.add_argument("--units", type=int, default=2)
    p.add_argument("--steps", type=int, default=40)
    p.add_argument("--dt", type=float, default=0.2)
    p.add_argument("--seed", type=int, default=5)
    p.add_argument("--no-gnss", action="store_true", help="indoor: relative frame only")
    a = p.parse_args(argv)
    if a.units < 1 or a.units > 8:
        p.error("--units must be 1..8")
    s = run_team(a.units, a.steps, a.dt, a.seed, gnss_on=not a.no_gnss)
    print(f"TEAM-SIM units={s['units']} steps={s['steps']} modes={s['modes']} "
          f"rmse={s['rmse']} tracks_seen={s['tracks_seen']}")
    for uid, heard in s["heard"].items():
        print(f"  {uid}: heard={heard} offsets={s['offsets'][uid]} final={s['final_enu'][uid]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
