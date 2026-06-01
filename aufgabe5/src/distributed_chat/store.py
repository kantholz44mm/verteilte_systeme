from __future__ import annotations

from bisect import insort
from collections import defaultdict
from threading import RLock
from typing import Dict, Iterable, List, Set, Tuple

from .models import ChatMessage, PeerInfo


class ChatStore:
    """In-memory state shared by the REST API, WebSocket UI and gossip loop."""

    def __init__(self, self_peer: PeerInfo) -> None:
        self.self_peer = self_peer
        self._peers: Dict[str, PeerInfo] = {}
        self._messages: Dict[str, Dict[str, ChatMessage]] = defaultdict(dict)
        self._ordered: Dict[str, List[Tuple[tuple[int, int, str, str], str]]] = defaultdict(list)
        self._delivered: Set[str] = set()
        self._lock = RLock()

    def add_peer(self, peer: PeerInfo) -> bool:
        if peer.peer_id == self.self_peer.peer_id:
            return False
        with self._lock:
            changed = self._peers.get(peer.peer_id) != peer
            self._peers[peer.peer_id] = peer
            return changed

    def peers(self) -> List[PeerInfo]:
        with self._lock:
            return sorted(self._peers.values(), key=lambda peer: peer.peer_id)

    def store_message(self, message: ChatMessage) -> bool:
        with self._lock:
            room_messages = self._messages[message.room]
            if message.message_id in room_messages:
                return False
            room_messages[message.message_id] = message
            insort(self._ordered[message.room], (message.sort_key(), message.message_id))
            return True

    def mark_delivered(self, delivery_id: str) -> bool:
        with self._lock:
            if delivery_id in self._delivered:
                return False
            self._delivered.add(delivery_id)
            return True

    def room_messages(self, room: str) -> List[ChatMessage]:
        with self._lock:
            room_messages = self._messages.get(room, {})
            return [room_messages[message_id] for _, message_id in self._ordered.get(room, [])]

    def rooms(self) -> List[str]:
        with self._lock:
            return sorted(self._messages.keys())

    def all_messages(self) -> List[ChatMessage]:
        with self._lock:
            messages: List[ChatMessage] = []
            for room in sorted(self._ordered):
                messages.extend(self.room_messages(room))
            return messages

    def merge_messages(self, messages: Iterable[ChatMessage]) -> List[ChatMessage]:
        stored: List[ChatMessage] = []
        for message in messages:
            if self.store_message(message):
                stored.append(message)
        return stored
