from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import socketserver
import struct
import threading
from typing import Dict, Optional, Tuple


WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
OPCODE_TEXT = 0x1
OPCODE_CLOSE = 0x8
OPCODE_PING = 0x9
OPCODE_PONG = 0xA


class WebSocketError(RuntimeError):
    """Raised for WebSocket protocol problems."""


def _create_accept_value(key: str) -> str:
    data = (key + WEBSOCKET_GUID).encode("ascii")
    return base64.b64encode(hashlib.sha1(data).digest()).decode("ascii")


def _read_http_headers(sock: socket.socket) -> Tuple[str, Dict[str, str]]:
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            raise WebSocketError("Socket closed before headers were received.")
        data += chunk
        if len(data) > 65536:
            raise WebSocketError("HTTP header section is too large.")

    raw_headers = data.split(b"\r\n\r\n", 1)[0].decode("utf-8")
    lines = raw_headers.split("\r\n")
    request_line = lines[0]
    headers: Dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    return request_line, headers


def _build_frame(payload: bytes, opcode: int, *, masked: bool) -> bytes:
    first_byte = 0x80 | opcode
    length = len(payload)

    if length <= 125:
        second_byte = length
        extra = b""
    elif length < 65536:
        second_byte = 126
        extra = struct.pack("!H", length)
    else:
        second_byte = 127
        extra = struct.pack("!Q", length)

    if not masked:
        return bytes([first_byte, second_byte]) + extra + payload

    mask_key = os.urandom(4)
    masked_payload = bytes(byte ^ mask_key[index % 4] for index, byte in enumerate(payload))
    return bytes([first_byte, second_byte | 0x80]) + extra + mask_key + masked_payload


def _recv_exact(sock: socket.socket, amount: int) -> bytes:
    data = b""
    while len(data) < amount:
        chunk = sock.recv(amount - len(data))
        if not chunk:
            raise ConnectionError("Socket closed while reading a frame.")
        data += chunk
    return data


def _recv_frame(sock: socket.socket) -> Tuple[int, bytes]:
    header = _recv_exact(sock, 2)
    first_byte, second_byte = header
    opcode = first_byte & 0x0F
    masked = bool(second_byte & 0x80)
    payload_length = second_byte & 0x7F

    if payload_length == 126:
        payload_length = struct.unpack("!H", _recv_exact(sock, 2))[0]
    elif payload_length == 127:
        payload_length = struct.unpack("!Q", _recv_exact(sock, 8))[0]

    mask_key = _recv_exact(sock, 4) if masked else b""
    payload = _recv_exact(sock, payload_length)
    if masked:
        payload = bytes(byte ^ mask_key[index % 4] for index, byte in enumerate(payload))
    return opcode, payload


class WebSocketConnection:
    def __init__(self, sock: socket.socket) -> None:
        self._socket = sock
        self._send_lock = threading.Lock()
        self._closed = False

    def send_json(self, payload: Dict[str, object]) -> None:
        self.send_text(json.dumps(payload))

    def send_text(self, message: str) -> None:
        frame = _build_frame(message.encode("utf-8"), OPCODE_TEXT, masked=False)
        with self._send_lock:
            if self._closed:
                raise ConnectionError("Connection is already closed.")
            self._socket.sendall(frame)

    def send_pong(self, payload: bytes = b"") -> None:
        frame = _build_frame(payload, OPCODE_PONG, masked=False)
        with self._send_lock:
            if not self._closed:
                self._socket.sendall(frame)

    def close(self) -> None:
        with self._send_lock:
            if self._closed:
                return
            try:
                self._socket.sendall(_build_frame(b"", OPCODE_CLOSE, masked=False))
            except OSError:
                pass
            self._closed = True
            try:
                self._socket.close()
            except OSError:
                pass


class ThreadedWebSocketServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class WebSocketRequestHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        session_id: Optional[str] = None
        connection: Optional[WebSocketConnection] = None
        try:
            session_id, connection = self._run_session()
        finally:
            if session_id and connection:
                self.server.state.unregister_connection(session_id, connection)
            if connection:
                connection.close()

    def _run_session(self) -> Tuple[Optional[str], WebSocketConnection]:
        request_line, headers = _read_http_headers(self.request)
        parts = request_line.split()
        if len(parts) < 2 or parts[0].upper() != "GET":
            raise WebSocketError("WebSocket handshake must be a GET request.")

        if headers.get("upgrade", "").lower() != "websocket":
            raise WebSocketError("Missing Upgrade: websocket header.")

        key = headers.get("sec-websocket-key")
        if not key:
            raise WebSocketError("Missing Sec-WebSocket-Key header.")

        accept_value = _create_accept_value(key)
        response = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept_value}\r\n\r\n"
        )
        self.request.sendall(response.encode("utf-8"))

        connection = WebSocketConnection(self.request)
        session_id: Optional[str] = None
        while True:
            opcode, payload = _recv_frame(self.request)

            if opcode == OPCODE_CLOSE:
                return session_id, connection
            if opcode == OPCODE_PING:
                connection.send_pong(payload)
                continue
            if opcode != OPCODE_TEXT:
                continue

            message = json.loads(payload.decode("utf-8"))
            action = message.get("action")
            if action == "register":
                next_session_id = _require_session_id(message.get("session_id"))
                if session_id and session_id != next_session_id:
                    self.server.state.unregister_connection(session_id, connection)
                session_id = next_session_id
                self.server.state.register_connection(session_id, connection)
                if "threshold" in message:
                    self.server.state.set_threshold(session_id, int(message["threshold"]))
            elif action == "set_threshold":
                current_session_id = _require_session_id(message.get("session_id"))
                if session_id and session_id != current_session_id:
                    self.server.state.unregister_connection(session_id, connection)
                    self.server.state.register_connection(current_session_id, connection)
                session_id = current_session_id
                self.server.state.set_threshold(session_id, int(message["threshold"]))
            elif action == "ping":
                connection.send_json({"type": "pong"})
            else:
                connection.send_json({"type": "error", "message": "Unknown WebSocket action."})


class SimpleWebSocketClient:
    def __init__(self, host: str, port: int, path: str = "/ws", timeout: float = 5.0) -> None:
        self._host = host
        self._port = port
        self._path = path
        self._timeout = timeout
        self._socket: Optional[socket.socket] = None
        self._send_lock = threading.Lock()

    def connect(self) -> None:
        sock = socket.create_connection((self._host, self._port), timeout=self._timeout)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {self._path} HTTP/1.1\r\n"
            f"Host: {self._host}:{self._port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(request.encode("utf-8"))
        _, headers = _read_http_headers(sock)
        if headers.get("sec-websocket-accept") != _create_accept_value(key):
            sock.close()
            raise WebSocketError("WebSocket handshake validation failed.")
        self._socket = sock

    def send_json(self, payload: Dict[str, object]) -> None:
        self.send_text(json.dumps(payload))

    def send_text(self, message: str) -> None:
        if self._socket is None:
            raise ConnectionError("WebSocket client is not connected.")
        frame = _build_frame(message.encode("utf-8"), OPCODE_TEXT, masked=True)
        with self._send_lock:
            self._socket.sendall(frame)

    def receive_json(self, timeout: Optional[float] = None) -> Optional[Dict[str, object]]:
        if self._socket is None:
            raise ConnectionError("WebSocket client is not connected.")

        self._socket.settimeout(timeout)
        while True:
            opcode, payload = _recv_frame(self._socket)
            if opcode == OPCODE_CLOSE:
                return None
            if opcode == OPCODE_PING:
                self._socket.sendall(_build_frame(payload, OPCODE_PONG, masked=True))
                continue
            if opcode != OPCODE_TEXT:
                continue
            return json.loads(payload.decode("utf-8"))

    def close(self) -> None:
        if self._socket is None:
            return
        with self._send_lock:
            try:
                self._socket.sendall(_build_frame(b"", OPCODE_CLOSE, masked=True))
            except OSError:
                pass
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None


def _require_session_id(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("'session_id' must be a non-empty string.")
    return value

