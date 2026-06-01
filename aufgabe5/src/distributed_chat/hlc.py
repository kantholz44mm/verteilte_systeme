from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, Optional


@dataclass(frozen=True, order=True)
class HLCTimestamp:
    wall_ms: int
    counter: int
    node_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "wall_ms": self.wall_ms,
            "counter": self.counter,
            "node_id": self.node_id,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "HLCTimestamp":
        return cls(
            wall_ms=int(payload["wall_ms"]),
            counter=int(payload["counter"]),
            node_id=str(payload["node_id"]),
        )

    def compact(self) -> str:
        return f"{self.wall_ms:013d}-{self.counter:04d}-{self.node_id}"


class HybridLogicalClock:
    """Small HLC implementation based on the Kulkarni/Demirbas algorithm."""

    def __init__(self, node_id: str, initial_wall_ms: Optional[int] = None) -> None:
        self.node_id = node_id
        self._wall_ms = initial_wall_ms or self._physical_ms()
        self._counter = 0
        self._lock = Lock()

    @staticmethod
    def _physical_ms() -> int:
        return int(time.time() * 1000)

    def now(self) -> HLCTimestamp:
        with self._lock:
            physical_ms = self._physical_ms()
            if physical_ms > self._wall_ms:
                self._wall_ms = physical_ms
                self._counter = 0
            else:
                self._counter += 1
            return HLCTimestamp(self._wall_ms, self._counter, self.node_id)

    def observe(self, remote: HLCTimestamp) -> HLCTimestamp:
        with self._lock:
            physical_ms = self._physical_ms()
            max_wall = max(physical_ms, self._wall_ms, remote.wall_ms)

            if max_wall == self._wall_ms and max_wall == remote.wall_ms:
                self._counter = max(self._counter, remote.counter) + 1
            elif max_wall == self._wall_ms:
                self._counter += 1
            elif max_wall == remote.wall_ms:
                self._counter = remote.counter + 1
            else:
                self._counter = 0

            self._wall_ms = max_wall
            return HLCTimestamp(self._wall_ms, self._counter, self.node_id)
