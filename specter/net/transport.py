"""UDP-multicast transport with loopback fallback for CI.

Real path: one multicast group (default 239.10.10.10:5007, TTL 2 = team LAN).
Every datagram is an HMAC-signed envelope (see security.py); unsigned input
is dropped before it can reach fusion. In CI / single-host sims the socket
falls back to loopback broadcast so `python -m specter.sim.team` works with
no network at all. Zenoh / ROS 2 DDS can replace this module later — the
message API above it does not change.
"""
from __future__ import annotations

import socket
import struct
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import security
from .messages import Message, decode_message

GROUP, PORT, TTL = "239.10.10.10", 5007, 2
MAX_DATAGRAM = 65507


class BusHub:
    """In-process broadcast hub so N virtual units hear each other (team sim).

    Per-reader cursors: a unit only sees entries appended after its last
    receive, and entries are pruned once every member has consumed them.
    """

    def __init__(self, members=()) -> None:
        self.entries: List[bytes] = []
        self.cursors: Dict[str, int] = {}
        self.members = set(members)

    def register(self, reader: str) -> None:
        self.members.add(reader)
        self.cursors.setdefault(reader, 0)

    def publish(self, env: bytes) -> None:
        self.entries.append(env)

    def drain(self, reader: str) -> List[bytes]:
        self.cursors.setdefault(reader, 0)
        cur = self.cursors[reader]
        new = self.entries[cur:]
        self.cursors[reader] = len(self.entries)
        if (
            self.entries
            and self.members
            and all(self.cursors.get(m, -1) >= len(self.entries) for m in self.members)
        ):
            del self.entries[: len(self.entries)]
            for k in self.cursors:
                self.cursors[k] = 0
        return new


@dataclass
class UdpMulticastTransport:
    key: bytes
    group: str = GROUP
    port: int = PORT
    unit_id: str = "unit-1"
    timeout_s: float = 0.05
    _sock: Optional[socket.socket] = field(default=None, repr=False)
    loopback_only: bool = False
    hub: Optional[BusHub] = None  # shared in-process bus (team sim)
    _local: List[bytes] = field(default_factory=list, repr=False)  # self-check copies

    def __post_init__(self) -> None:
        if len(self.key) < 16:
            raise ValueError("team key must be >= 16 bytes")
        if not self.loopback_only:
            try:
                self._sock = self._open_multicast()
            except OSError:
                self._sock = None  # no multicast route: loopback fallback

    def _open_multicast(self) -> socket.socket:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            pass
        s.bind(("", self.port))
        mreq = struct.pack("4sl", socket.inet_aton(self.group), socket.INADDR_ANY)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, TTL)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        s.settimeout(self.timeout_s)
        return s

    # -- send / receive -------------------------------------------------
    def send(self, msg: Message) -> int:
        env = security.sign(msg.to_json(), self.key).encode()
        if len(env) > MAX_DATAGRAM:
            raise ValueError(f"signed datagram {len(env)}B exceeds UDP limit")
        n = 0
        if self._sock is not None:
            n = self._sock.sendto(env, (self.group, self.port))
        if self.hub is not None:
            self.hub.publish(env)  # every virtual unit hears it
        else:
            self._local.append(env)  # loopback copy: self-checks always work
        return n or len(env)

    def receive(self, clock=None) -> List[Message]:
        """Return verified, fresh, non-self messages. Stale/rogue dropped."""
        raw: List[bytes] = []
        if self.hub is not None:
            raw.extend(self.hub.drain(self.unit_id))
        elif self._local:
            raw.extend(self._local)
            self._local.clear()
        if self._sock is not None:
            deadline = time.time() + self.timeout_s
            while time.time() < deadline:
                try:
                    data, _ = self._sock.recvfrom(MAX_DATAGRAM)
                    raw.append(data)
                except socket.timeout:
                    break
                except OSError:
                    break
        out: List[Message] = []
        for env in raw:
            try:
                inner = security.verify(env.decode(), self.key)
                m = decode_message(inner)
            except ValueError:
                continue  # rogue / corrupt: drop silently, counted by caller
            if m.unit_id == self.unit_id:
                continue  # our own loopback copy
            if clock is not None:
                if clock.is_stale(m.t_host):
                    continue
                clock.observe(m.unit_id, m.t_host)
            out.append(m)
        return out

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
