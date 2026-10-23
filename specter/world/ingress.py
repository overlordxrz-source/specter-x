"""Offline-tested ingress seam. No hardware transport is instantiated here."""

from collections import deque
import time
from specter.platform.observation import Observation, ContractError
from specter.platform.registry import default_registry


class Ingress:
    """Bounded validated envelopes from a future dispatcher/driver worker.

    A software test connection is never LIVE. Hardware authorization and a
    physical acceptance artifact must be supplied by a future transport owner.
    This seam deliberately contains no port discovery or serial-open path.
    """

    def __init__(self, capacity=256, clock=time.monotonic_ns):
        if type(capacity) is not int or capacity < 1:
            raise ValueError("positive ingress capacity required")
        self.queue = deque(maxlen=capacity)
        self.registry = default_registry(capacity)
        self.clock = clock
        self.state = "OFFLINE"
        self.dropped = 0
        self.last_receive = None
        self.error = None

    def connect_test(self):
        self.state = "TEST CONNECTION / UNVERIFIED"
        self.last_receive = None

    def submit(self, observation):
        if self.state == "OFFLINE":
            raise ContractError("transport disconnected")
        if not isinstance(observation, Observation):
            raise ContractError("validated Observation required")
        if len(self.queue) == self.queue.maxlen:
            self.dropped += 1
        self.queue.append((self.clock(), observation))

    def drain(self):
        while self.queue:
            when, observation = self.queue.popleft()
            try:
                self.registry.ingest(observation, when)
                self.last_receive = when
            except ContractError as exc:
                self.error = str(exc)
                self.state = "ERROR"
                raise

    def health(self, stale_ns=2_000_000_000):
        if (
            self.last_receive is not None
            and self.state != "OFFLINE"
            and self.clock() - self.last_receive > stale_ns
        ):
            return "STALE / TEST CONNECTION"
        return self.state

    def disconnect(self):
        self.queue.clear()
        self.state = "OFFLINE"
        for sid in self.registry.streams:
            self.registry.disconnect(sid)
