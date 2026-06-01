from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List

from .hlc import HLCTimestamp


def _stable_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True)
class PeerInfo:
    peer_id: str
    base_url: str

    def to_dict(self) -> Dict[str, str]:
        return {"peer_id": self.peer_id, "base_url": self.base_url.rstrip("/")}

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "PeerInfo":
        peer_id = str(payload["peer_id"]).strip()
        base_url = str(payload["base_url"]).strip().rstrip("/")
        if not peer_id:
            raise ValueError("peer_id must not be empty")
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return cls(peer_id=peer_id, base_url=base_url)


@dataclass(frozen=True)
class ChatMessage:
    room: str
    sender: str
    text: str
    timestamp: HLCTimestamp
    physical_ms: int
    message_id: str = ""

    def __post_init__(self) -> None:
        if self.message_id:
            return
        payload = {
            "room": self.room,
            "sender": self.sender,
            "text": self.text,
            "timestamp": self.timestamp.to_dict(),
            "physical_ms": self.physical_ms,
        }
        digest = hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()
        object.__setattr__(self, "message_id", digest[:32])

    def sort_key(self) -> tuple[int, int, str, str]:
        return (
            self.timestamp.wall_ms,
            self.timestamp.counter,
            self.timestamp.node_id,
            self.message_id,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "room": self.room,
            "sender": self.sender,
            "text": self.text,
            "timestamp": self.timestamp.to_dict(),
            "physical_ms": self.physical_ms,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ChatMessage":
        return cls(
            message_id=str(payload["message_id"]),
            room=str(payload["room"]),
            sender=str(payload["sender"]),
            text=str(payload["text"]),
            timestamp=HLCTimestamp.from_dict(payload["timestamp"]),
            physical_ms=int(payload["physical_ms"]),
        )


@dataclass(frozen=True)
class GossipEnvelope:
    message: ChatMessage
    qos: int = 2
    ttl: int = 8
    path: List[str] = field(default_factory=list)
    delivery_id: str = ""

    def __post_init__(self) -> None:
        if self.qos != 2:
            raise ValueError("qos must be 2")
        if not self.delivery_id:
            payload = {
                "message_id": self.message.message_id,
                "qos": self.qos,
                "path": self.path,
            }
            digest = hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()
            object.__setattr__(self, "delivery_id", digest[:32])

    def forwarded_by(self, peer_id: str) -> "GossipEnvelope":
        return GossipEnvelope(
            message=self.message,
            qos=self.qos,
            ttl=max(0, self.ttl - 1),
            path=[*self.path, peer_id],
            delivery_id=self.delivery_id,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message": self.message.to_dict(),
            "qos": self.qos,
            "ttl": self.ttl,
            "path": list(self.path),
            "delivery_id": self.delivery_id,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "GossipEnvelope":
        return cls(
            message=ChatMessage.from_dict(payload["message"]),
            qos=int(payload.get("qos", 2)),
            ttl=int(payload.get("ttl", 8)),
            path=[str(item) for item in payload.get("path", [])],
            delivery_id=str(payload.get("delivery_id", "")),
        )
