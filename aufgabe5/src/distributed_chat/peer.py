from __future__ import annotations

import asyncio
import os
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .hlc import HybridLogicalClock
from .models import ChatMessage, GossipEnvelope, PeerInfo
from .store import ChatStore


def _model_payload(model: BaseModel) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


class PublishRequest(BaseModel):
    room: str = Field(default="general", min_length=1)
    text: str = Field(min_length=1)


class PeerRequest(BaseModel):
    peer_id: str = Field(min_length=1)
    base_url: str = Field(min_length=1)


class SyncRequest(BaseModel):
    messages: List[Dict[str, Any]] = Field(default_factory=list)


@dataclass(frozen=True)
class OutboxItem:
    peer: PeerInfo
    envelope: GossipEnvelope


class WebSocketHub:
    def __init__(self) -> None:
        self._connections: Dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, room: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.setdefault(room, set()).add(websocket)

    async def unsubscribe(self, room: str, websocket: WebSocket) -> None:
        async with self._lock:
            sockets = self._connections.get(room)
            if not sockets:
                return
            sockets.discard(websocket)
            if not sockets:
                self._connections.pop(room, None)

    async def publish(self, message: ChatMessage) -> None:
        async with self._lock:
            sockets = list(self._connections.get(message.room, set()))

        for websocket in sockets:
            try:
                await websocket.send_json({"type": "message", "message": message.to_dict()})
            except Exception:
                await self.unsubscribe(message.room, websocket)


class ChatPeer:
    def __init__(self, peer_id: str, base_url: str, bootstrap: List[str]) -> None:
        self.self_peer = PeerInfo(peer_id=peer_id, base_url=base_url)
        self.clock = HybridLogicalClock(peer_id)
        self.store = ChatStore(self.self_peer)
        self.hub = WebSocketHub()
        self.bootstrap = [url.rstrip("/") for url in bootstrap if url.strip()]
        self._outbox: Optional[asyncio.Queue[OutboxItem]] = None

    async def start_background_tasks(self) -> None:
        self._outbox = asyncio.Queue()
        await self._join_bootstrap_peers()
        asyncio.create_task(self._bootstrap_loop())
        asyncio.create_task(self._outbox_loop())
        asyncio.create_task(self._anti_entropy_loop())

    async def _bootstrap_loop(self) -> None:
        while True:
            await asyncio.sleep(3.0)
            await self._join_bootstrap_peers()

    async def _join_bootstrap_peers(self) -> None:
        async with httpx.AsyncClient(timeout=3.0) as client:
            for url in self.bootstrap:
                try:
                    response = await client.post(f"{url}/peers", json=self.self_peer.to_dict())
                    response.raise_for_status()
                    payload = response.json()
                    for peer_payload in payload.get("peers", []):
                        self.store.add_peer(PeerInfo.from_dict(peer_payload))
                    self.store.add_peer(PeerInfo(peer_id=payload["peer_id"], base_url=url))
                except Exception:
                    continue

    async def publish_local(self, request: PublishRequest) -> ChatMessage:
        timestamp = self.clock.now()
        message = ChatMessage(
            room=request.room,
            sender=self.self_peer.peer_id,
            text=request.text,
            timestamp=timestamp,
            physical_ms=timestamp.wall_ms,
        )
        self.store.store_message(message)
        await self.hub.publish(message)
        await self.gossip(GossipEnvelope(message=message, path=[self.self_peer.peer_id]))
        return message

    async def receive_gossip(self, envelope: GossipEnvelope) -> Dict[str, Any]:
        if not self.store.mark_delivered(envelope.delivery_id):
            return {"status": "duplicate", "message_id": envelope.message.message_id}

        self.clock.observe(envelope.message.timestamp)
        stored = self.store.store_message(envelope.message)
        if stored:
            await self.hub.publish(envelope.message)
            if envelope.ttl > 0:
                await self.gossip(envelope.forwarded_by(self.self_peer.peer_id))

        return {
            "status": "stored" if stored else "duplicate",
            "message_id": envelope.message.message_id,
        }

    async def gossip(self, envelope: GossipEnvelope) -> None:
        for peer in self.store.peers():
            if peer.peer_id in envelope.path:
                continue
            await self._send_or_queue(peer, envelope.forwarded_by(self.self_peer.peer_id))

    async def _send_or_queue(self, peer: PeerInfo, envelope: GossipEnvelope) -> None:
        if not await self._send_with_retry(peer, envelope):
            if self._outbox is not None:
                await self._outbox.put(OutboxItem(peer=peer, envelope=envelope))

    async def _send_once(self, peer: PeerInfo, envelope: GossipEnvelope) -> bool:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.post(f"{peer.base_url}/p2p/gossip", json=envelope.to_dict())
                return response.status_code < 500
        except Exception:
            return False

    async def _send_with_retry(self, peer: PeerInfo, envelope: GossipEnvelope) -> bool:
        for attempt in range(5):
            if await self._send_once(peer, envelope):
                return True
            await asyncio.sleep(0.25 * (attempt + 1))
        return False

    async def _outbox_loop(self) -> None:
        if self._outbox is None:
            return
        while True:
            item = await self._outbox.get()
            await asyncio.sleep(1.0)
            if not await self._send_with_retry(item.peer, item.envelope):
                await self._outbox.put(item)

    async def _anti_entropy_loop(self) -> None:
        while True:
            await asyncio.sleep(5.0)
            messages = [message.to_dict() for message in self.store.all_messages()]
            if not messages:
                continue
            async with httpx.AsyncClient(timeout=4.0) as client:
                for peer in self.store.peers():
                    try:
                        response = await client.post(f"{peer.base_url}/p2p/sync", json={"messages": messages})
                        response.raise_for_status()
                        for message_payload in response.json().get("messages", []):
                            message = ChatMessage.from_dict(message_payload)
                            self.clock.observe(message.timestamp)
                            if self.store.store_message(message):
                                await self.hub.publish(message)
                    except Exception:
                        continue


def create_app(peer: ChatPeer) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await peer.start_background_tasks()
        yield

    app = FastAPI(
        title="Distributed Chat Service",
        version="1.0.0",
        description="Homogeneous Python peer implementing gossip chat rooms with HLC ordering.",
        lifespan=lifespan,
    )

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index() -> str:
        return UI_HTML

    @app.get("/health")
    async def health() -> Dict[str, str]:
        return {"status": "ok", "peer_id": peer.self_peer.peer_id}

    @app.get("/peers")
    async def peers() -> Dict[str, Any]:
        return {
            "peer_id": peer.self_peer.peer_id,
            "base_url": peer.self_peer.base_url,
            "peers": [known_peer.to_dict() for known_peer in peer.store.peers()],
        }

    @app.post("/peers")
    async def add_peer(request: PeerRequest) -> Dict[str, Any]:
        new_peer = PeerInfo.from_dict(_model_payload(request))
        changed = peer.store.add_peer(new_peer)
        if changed:
            await peer._send_once(new_peer, GossipEnvelope(
                message=ChatMessage(
                    room="system",
                    sender=peer.self_peer.peer_id,
                    text=f"{peer.self_peer.peer_id} kennt jetzt {new_peer.peer_id}",
                    timestamp=peer.clock.now(),
                    physical_ms=int(time.time() * 1000),
                ),
                ttl=1,
                path=[peer.self_peer.peer_id],
            ))
        return await peers()

    @app.post("/messages")
    async def publish(request: PublishRequest) -> Dict[str, Any]:
        message = await peer.publish_local(request)
        return {"message": message.to_dict()}

    @app.get("/rooms")
    async def rooms() -> Dict[str, Any]:
        room_names = peer.store.rooms()
        if "general" not in room_names:
            room_names.insert(0, "general")
        return {"rooms": room_names}

    @app.get("/rooms/{room}/messages")
    async def room_messages(room: str) -> Dict[str, Any]:
        return {"messages": [message.to_dict() for message in peer.store.room_messages(room)]}

    @app.post("/p2p/gossip")
    async def p2p_gossip(request: Request) -> Dict[str, Any]:
        envelope = GossipEnvelope.from_dict(await request.json())
        return await peer.receive_gossip(envelope)

    @app.post("/p2p/sync")
    async def p2p_sync(request: SyncRequest) -> Dict[str, Any]:
        incoming = [ChatMessage.from_dict(payload) for payload in request.messages]
        for message in incoming:
            peer.clock.observe(message.timestamp)
        stored = peer.store.merge_messages(incoming)
        for message in stored:
            await peer.hub.publish(message)
        return {"messages": [message.to_dict() for message in peer.store.all_messages()]}

    @app.websocket("/ws/{room}")
    async def websocket_room(websocket: WebSocket, room: str) -> None:
        await websocket.accept()
        await peer.hub.subscribe(room, websocket)
        try:
            for message in peer.store.room_messages(room):
                await websocket.send_json({"type": "message", "message": message.to_dict()})
            while True:
                payload = await websocket.receive_json()
                if payload.get("type") == "publish":
                    request = PublishRequest(
                        room=room,
                        text=str(payload.get("text", "")),
                    )
                    await peer.publish_local(request)
        except WebSocketDisconnect:
            pass
        finally:
            await peer.hub.unsubscribe(room, websocket)

    return app


UI_HTML = """
<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Distributed Chat</title>
  <style>
    :root {
      color-scheme: light dark;
      font-family: Inter, ui-sans-serif, system-ui, sans-serif;
      background: #d7dbd6;
      color: #17211c;
    }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; background: linear-gradient(#1f6f5b 0 128px, #d7dbd6 128px); }
    main { height: 100vh; max-width: 1180px; margin: 0 auto; padding: 24px; }
    .app {
      display: grid;
      grid-template-columns: 340px minmax(0, 1fr);
      height: calc(100vh - 48px);
      min-height: 560px;
      border: 1px solid #c5cbc8;
      background: #f5f3ef;
      box-shadow: 0 16px 40px rgba(24, 35, 31, 0.18);
      overflow: hidden;
    }
    aside { display: grid; grid-template-rows: auto auto 1fr; border-right: 1px solid #d5dbd8; background: #fff; min-width: 0; }
    .sidebar-head, .chat-head {
      display: flex;
      align-items: center;
      gap: 12px;
      min-height: 68px;
      padding: 12px 16px;
      background: #f0f2f1;
    }
    .avatar {
      display: grid;
      place-items: center;
      width: 42px;
      height: 42px;
      flex: 0 0 42px;
      border-radius: 50%;
      background: #d7efe7;
      color: #0f6b55;
      font-weight: 700;
    }
    .identity, .chat-title { min-width: 0; }
    h1, h2 { margin: 0; letter-spacing: 0; }
    h1 { font-size: 17px; }
    h2 { font-size: 18px; }
    .status, .subtitle { color: #62736d; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .settings { display: grid; gap: 8px; padding: 12px; border-bottom: 1px solid #eef1ef; }
    .group-form { display: grid; grid-template-columns: 1fr auto; gap: 8px; }
    input, select, button {
      min-width: 0;
      border: 1px solid #cdd5d1;
      border-radius: 6px;
      padding: 10px 12px;
      font: inherit;
      background: #fff;
      color: inherit;
    }
    button { background: #1f8f73; color: #fff; border-color: #1f8f73; cursor: pointer; font-weight: 600; }
    .group-list { overflow: auto; }
    .group {
      display: grid;
      grid-template-columns: 44px minmax(0, 1fr);
      gap: 12px;
      width: 100%;
      border: 0;
      border-bottom: 1px solid #edf0ee;
      border-radius: 0;
      padding: 12px 14px;
      background: #fff;
      color: inherit;
      text-align: left;
    }
    .group:hover, .group.active { background: #eef8f5; }
    .group .avatar { width: 44px; height: 44px; }
    .group-name { display: block; font-weight: 650; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .group-preview { display: block; margin-top: 3px; color: #6a7672; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .chat { display: grid; grid-template-rows: auto 1fr auto; min-width: 0; background: #efe6dc; }
    #messages {
      overflow: auto;
      padding: 18px clamp(14px, 4vw, 48px);
      background:
        radial-gradient(circle at 20px 20px, rgba(31, 143, 115, 0.05) 0 2px, transparent 2px 28px),
        #efe6dc;
    }
    .message { display: flex; margin: 7px 0; }
    .bubble {
      max-width: min(680px, 82%);
      padding: 8px 10px 7px;
      border-radius: 7px;
      background: #fff;
      box-shadow: 0 1px 1px rgba(20, 31, 28, 0.08);
    }
    .message.own { justify-content: flex-end; }
    .message.own .bubble { background: #d9fdd3; }
    .meta { display: flex; gap: 8px; align-items: baseline; color: #62736d; font-size: 12px; margin-bottom: 3px; }
    .text { white-space: pre-wrap; word-break: break-word; line-height: 1.35; }
    form { display: grid; grid-template-columns: 1fr auto; gap: 10px; padding: 12px 16px; background: #f0f2f1; }
    @media (max-width: 780px) {
      main { height: 100dvh; padding: 0; }
      .app { height: 100dvh; min-height: 0; grid-template-columns: 1fr; border: 0; }
      aside { display: none; }
      aside.open { display: grid; position: fixed; inset: 0; z-index: 2; }
      .chat { height: 100dvh; }
      .chat-head { cursor: pointer; }
    }
  </style>
</head>
<body>
  <main>
    <div class="app">
      <aside id="sidebar">
        <div class="sidebar-head">
          <div class="avatar">DC</div>
          <div class="identity">
            <h1>Distributed Chat</h1>
            <div class="status" id="status">Verbinde...</div>
          </div>
        </div>
        <div class="settings">
          <div class="group-form">
            <input id="new-room" placeholder="Neue Gruppe" aria-label="Neue Gruppe" />
            <button id="add-room" type="button">+</button>
          </div>
        </div>
        <nav class="group-list" id="groups" aria-label="Gruppen"></nav>
      </aside>
      <section class="chat">
        <div class="chat-head" id="chat-head">
          <div class="avatar" id="room-avatar">G</div>
          <div class="chat-title">
            <h2 id="room-title">general</h2>
            <div class="subtitle" id="room-subtitle">Gruppe als Chatraum</div>
          </div>
        </div>
        <section id="messages" aria-live="polite"></section>
        <form id="form">
          <input id="text" placeholder="Nachricht" autocomplete="off" />
          <button>Senden</button>
        </form>
      </section>
    </div>
  </main>
  <script>
    const statusEl = document.querySelector("#status");
    const messagesEl = document.querySelector("#messages");
    const textInput = document.querySelector("#text");
    const form = document.querySelector("#form");
    const groupsEl = document.querySelector("#groups");
    const newRoomInput = document.querySelector("#new-room");
    const roomTitle = document.querySelector("#room-title");
    const roomSubtitle = document.querySelector("#room-subtitle");
    const roomAvatar = document.querySelector("#room-avatar");
    const sidebar = document.querySelector("#sidebar");
    let socket;
    let activeRoom = "general";
    let localPeerId = "peer";
    let groups = ["general", "team", "projekt"];
    const previews = new Map();
    const seen = new Set();

    function groupInitial(room) {
      return (room || "G").trim().charAt(0).toUpperCase();
    }

    function roomLabel(room) {
      return room.replace(/[-_]+/g, " ");
    }

    function normalizeRoom(room) {
      return room.trim().toLowerCase().replace(/\\s+/g, "-");
    }

    function renderGroups() {
      groupsEl.textContent = "";
      [...new Set(groups)].sort((a, b) => a.localeCompare(b)).forEach(room => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `group${room === activeRoom ? " active" : ""}`;
        button.innerHTML = `<span class="avatar">${groupInitial(room)}</span><span><span class="group-name"></span><span class="group-preview"></span></span>`;
        button.querySelector(".group-name").textContent = roomLabel(room);
        button.querySelector(".group-preview").textContent = previews.get(room) || "Noch keine Nachrichten";
        button.addEventListener("click", () => {
          connect(room);
          sidebar.classList.remove("open");
        });
        groupsEl.appendChild(button);
      });
    }

    async function loadRooms() {
      try {
        const response = await fetch("/rooms");
        const payload = await response.json();
        groups = [...new Set([...groups, ...(payload.rooms || [])])];
        renderGroups();
      } catch (_) {
        renderGroups();
      }
    }

    async function loadPeerId() {
      try {
        const response = await fetch("/health");
        const payload = await response.json();
        localPeerId = payload.peer_id || localPeerId;
      } catch (_) {
        localPeerId = "peer";
      }
    }

    function connect() {
      const room = arguments[0] || activeRoom || "general";
      if (socket) socket.close();
      activeRoom = room;
      seen.clear();
      messagesEl.textContent = "";
      roomTitle.textContent = roomLabel(room);
      roomSubtitle.textContent = "Gruppe als Chatraum";
      roomAvatar.textContent = groupInitial(room);
      renderGroups();
      const scheme = location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${scheme}://${location.host}/ws/${encodeURIComponent(room)}`);
      socket.onopen = () => statusEl.textContent = `${localPeerId} online in ${roomLabel(room)}`;
      socket.onclose = () => statusEl.textContent = "offline";
      socket.onmessage = event => {
        const payload = JSON.parse(event.data);
        if (payload.type !== "message" || seen.has(payload.message.message_id)) return;
        seen.add(payload.message.message_id);
        groups = [...new Set([...groups, payload.message.room])];
        previews.set(payload.message.room, payload.message.text);
        renderGroups();
        const item = document.createElement("article");
        const own = payload.message.sender === localPeerId;
        item.className = `message${own ? " own" : ""}`;
        const ts = new Date(payload.message.physical_ms).toLocaleString();
        item.innerHTML = `<div class="bubble"><div class="meta"><strong>${payload.message.sender}</strong><span>${ts}</span></div><div class="text"></div></div>`;
        item.querySelector(".text").textContent = payload.message.text;
        messagesEl.appendChild(item);
        messagesEl.scrollTop = messagesEl.scrollHeight;
      };
    }

    document.querySelector("#add-room").addEventListener("click", () => {
      const room = normalizeRoom(newRoomInput.value);
      if (!room) return;
      groups = [...new Set([...groups, room])];
      newRoomInput.value = "";
      connect(room);
    });
    document.querySelector("#chat-head").addEventListener("click", () => sidebar.classList.add("open"));
    form.addEventListener("submit", event => {
      event.preventDefault();
      const text = textInput.value.trim();
      if (!text || !socket || socket.readyState !== WebSocket.OPEN) return;
      socket.send(JSON.stringify({type: "publish", text}));
      textInput.value = "";
    });
    Promise.all([loadPeerId(), loadRooms()]).then(() => connect("general"));
  </script>
</body>
</html>
"""


def build_peer_from_env() -> ChatPeer:
    peer_id = os.getenv("PEER_ID", f"peer-{uuid.uuid4().hex[:8]}")
    port = int(os.getenv("PORT", "8000"))
    base_url = os.getenv("BASE_URL", f"http://127.0.0.1:{port}")
    bootstrap = [item.strip() for item in os.getenv("BOOTSTRAP_PEERS", "").split(",") if item.strip()]
    return ChatPeer(peer_id=peer_id, base_url=base_url, bootstrap=bootstrap)


def main() -> None:
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run(create_app(build_peer_from_env()), host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
