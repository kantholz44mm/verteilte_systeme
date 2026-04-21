from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set

from .operations import DEFAULT_OPERATION_DEFINITIONS


class UnknownOperationError(KeyError):
    """Raised when an operation does not exist."""


class OperationDisabledError(RuntimeError):
    """Raised when an operation is configured but currently disabled."""


@dataclass
class OperationConfig:
    name: str
    description: str
    expression: str
    cost: int
    enabled: bool = True

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "expression": self.expression,
            "cost": self.cost,
            "enabled": self.enabled,
        }


@dataclass
class SessionState:
    session_id: str
    total_cost: int = 0
    threshold: Optional[int] = None
    threshold_exceeded: bool = False

    def to_dict(self) -> Dict[str, object]:
        return {
            "session_id": self.session_id,
            "total_cost": self.total_cost,
            "threshold": self.threshold,
            "threshold_exceeded": self.threshold_exceeded,
        }


class MathFactoryState:
    """Shared mutable state for REST, JSON-RPC, and WebSocket interfaces."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._operations: Dict[str, OperationConfig] = {
            name: OperationConfig(
                name=definition.name,
                description=definition.description,
                expression=definition.expression,
                cost=definition.default_cost,
                enabled=True,
            )
            for name, definition in DEFAULT_OPERATION_DEFINITIONS.items()
        }
        self._sessions: Dict[str, SessionState] = {}
        self._connections: Dict[str, Set[object]] = {}

    def list_operations(self) -> List[Dict[str, object]]:
        with self._lock:
            return [self._operations[name].to_dict() for name in self._operations]

    def get_operation(self, name: str) -> Dict[str, object]:
        with self._lock:
            return self._get_operation_config(name).to_dict()

    def update_operation(
        self,
        name: str,
        *,
        cost: Optional[int] = None,
        enabled: Optional[bool] = None,
    ) -> Dict[str, object]:
        with self._lock:
            config = self._get_operation_config(name)
            if cost is not None:
                if isinstance(cost, bool) or not isinstance(cost, int) or cost < 0:
                    raise ValueError("'cost' must be a non-negative integer.")
                config.cost = cost
            if enabled is not None:
                if not isinstance(enabled, bool):
                    raise ValueError("'enabled' must be a boolean value.")
                config.enabled = enabled
            return config.to_dict()

    def get_session(self, session_id: str) -> Dict[str, object]:
        with self._lock:
            return self._get_or_create_session(session_id).to_dict()

    def execute(self, name: str, arguments: List[object], session_id: Optional[str] = None) -> object:
        definition = DEFAULT_OPERATION_DEFINITIONS.get(name)
        if definition is None:
            raise UnknownOperationError(name)

        with self._lock:
            config = self._get_operation_config(name)
            if not config.enabled:
                raise OperationDisabledError(name)
            cost = config.cost

        result = definition.evaluator(*arguments)
        if session_id:
            self._charge_session(session_id, cost)
        return result

    def register_connection(self, session_id: str, connection: object) -> Dict[str, object]:
        with self._lock:
            session = self._get_or_create_session(session_id)
            self._connections.setdefault(session_id, set()).add(connection)
            snapshot = session.to_dict()
        self._safe_send(connection, self._registered_payload(snapshot))
        return snapshot

    def unregister_connection(self, session_id: str, connection: object) -> None:
        with self._lock:
            connections = self._connections.get(session_id)
            if not connections:
                return
            connections.discard(connection)
            if not connections:
                self._connections.pop(session_id, None)

    def set_threshold(self, session_id: str, threshold: int) -> Dict[str, object]:
        if isinstance(threshold, bool) or not isinstance(threshold, int) or threshold < 0:
            raise ValueError("'threshold' must be a non-negative integer.")

        recipients: List[object]
        update_payload: Dict[str, object]
        exceeded_payload: Optional[Dict[str, object]] = None
        with self._lock:
            session = self._get_or_create_session(session_id)
            session.threshold = threshold
            session.threshold_exceeded = session.total_cost >= threshold
            recipients = list(self._connections.get(session_id, set()))
            update_payload = self._threshold_updated_payload(session)
            if session.threshold_exceeded:
                exceeded_payload = self._threshold_exceeded_payload(session)
            snapshot = session.to_dict()

        self._broadcast(recipients, update_payload, session_id=session_id)
        if exceeded_payload is not None:
            self._broadcast(recipients, exceeded_payload, session_id=session_id)
        return snapshot

    def _get_operation_config(self, name: str) -> OperationConfig:
        config = self._operations.get(name)
        if config is None:
            raise UnknownOperationError(name)
        return config

    def _get_or_create_session(self, session_id: str) -> SessionState:
        if not session_id or not isinstance(session_id, str):
            raise ValueError("'session_id' must be a non-empty string.")
        session = self._sessions.get(session_id)
        if session is None:
            session = SessionState(session_id=session_id)
            self._sessions[session_id] = session
        return session

    def _charge_session(self, session_id: str, cost: int) -> None:
        recipients: List[object] = []
        payload: Optional[Dict[str, object]] = None
        with self._lock:
            session = self._get_or_create_session(session_id)
            session.total_cost += cost
            if session.threshold is not None and not session.threshold_exceeded:
                if session.total_cost >= session.threshold:
                    session.threshold_exceeded = True
                    recipients = list(self._connections.get(session_id, set()))
                    payload = self._threshold_exceeded_payload(session)
        if payload is not None:
            self._broadcast(recipients, payload, session_id=session_id)

    def _broadcast(self, recipients: Iterable[object], payload: Dict[str, object], *, session_id: str) -> None:
        for connection in list(recipients):
            if not self._safe_send(connection, payload):
                self.unregister_connection(session_id, connection)

    @staticmethod
    def _safe_send(connection: object, payload: Dict[str, object]) -> bool:
        try:
            connection.send_json(payload)
            return True
        except Exception:
            return False

    @staticmethod
    def _registered_payload(snapshot: Dict[str, object]) -> Dict[str, object]:
        return {
            "type": "registered",
            "session_id": snapshot["session_id"],
            "threshold": snapshot["threshold"],
            "total_cost": snapshot["total_cost"],
            "threshold_exceeded": snapshot["threshold_exceeded"],
        }

    @staticmethod
    def _threshold_updated_payload(session: SessionState) -> Dict[str, object]:
        return {
            "type": "threshold_updated",
            "session_id": session.session_id,
            "threshold": session.threshold,
            "total_cost": session.total_cost,
            "threshold_exceeded": session.threshold_exceeded,
        }

    @staticmethod
    def _threshold_exceeded_payload(session: SessionState) -> Dict[str, object]:
        return {
            "type": "threshold_exceeded",
            "session_id": session.session_id,
            "threshold": session.threshold,
            "total_cost": session.total_cost,
            "message": "The configured cost threshold has been exceeded.",
        }

