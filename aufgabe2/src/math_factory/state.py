from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Tuple

from .operations import DEFAULT_OPERATION_DEFINITIONS


class MathFactoryState:
    """Shared mutable state for REST, JSON-RPC, and WebSocket interfaces."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._operations: Dict[str, Dict[str, object]] = {
            name: {
                "name": definition["name"],
                "description": definition["description"],
                "expression": definition["expression"],
                "cost": definition["default_cost"],
                "enabled": True,
            }
            for name, definition in DEFAULT_OPERATION_DEFINITIONS.items()
        }
        self._sessions: Dict[str, Dict[str, object]] = {}

    def list_operations(self) -> List[Dict[str, object]]:
        with self._lock:
            return [dict(operation) for operation in self._operations.values()]

    def get_operation(self, name: str) -> Dict[str, object]:
        with self._lock:
            operation = self._operations.get(name)
            if operation is None:
                raise KeyError(name)
            return dict(operation)

    def update_operation(
        self,
        name: str,
        *,
        cost: Optional[int] = None,
        enabled: Optional[bool] = None,
    ) -> Dict[str, object]:
        with self._lock:
            config = self._operations.get(name)
            if config is None:
                raise KeyError(name)
            if cost is not None:
                if isinstance(cost, bool) or not isinstance(cost, int) or cost < 0:
                    raise ValueError("'cost' must be a non-negative integer.")
                config["cost"] = cost
            if enabled is not None:
                if not isinstance(enabled, bool):
                    raise ValueError("'enabled' must be a boolean value.")
                config["enabled"] = enabled
            return dict(config)

    def execute_with_notifications(
        self, name: str, arguments: List[object], session_id: Optional[str] = None
    ) -> Tuple[Any, List[Dict[str, object]]]:
        definition = DEFAULT_OPERATION_DEFINITIONS.get(name)
        if definition is None:
            raise KeyError(name)

        with self._lock:
            config = self._operations.get(name)
            if config is None:
                raise KeyError(name)
            if not config["enabled"]:
                raise RuntimeError(name)
            cost = config["cost"]

        result = definition["evaluator"](*arguments)
        notifications = self._charge_session(session_id, cost) if session_id is not None else []
        return result, notifications

    def set_threshold_with_notifications(
        self, session_id: str, threshold: int
    ) -> Tuple[Dict[str, object], List[Dict[str, object]]]:
        if isinstance(threshold, bool) or not isinstance(threshold, int) or threshold < 0:
            raise ValueError("'threshold' must be a non-negative integer.")

        notifications: List[Dict[str, object]] = []
        with self._lock:
            session = self._get_or_create_session(session_id)
            session["threshold"] = threshold
            session["threshold_exceeded"] = session["total_cost"] >= threshold
            snapshot = dict(session)
            notifications.append({"type": "threshold_updated", **snapshot})
            if snapshot["threshold_exceeded"]:
                notifications.append(
                    {
                        "type": "threshold_exceeded",
                        **snapshot,
                        "message": "The configured cost threshold has been exceeded.",
                    }
                )
        return snapshot, notifications

    def _get_or_create_session(self, session_id: str) -> Dict[str, object]:
        if not session_id or not isinstance(session_id, str):
            raise ValueError("'session_id' must be a non-empty string.")
        session = self._sessions.get(session_id)
        if session is None:
            session = {
                "session_id": session_id,
                "total_cost": 0,
                "threshold": None,
                "threshold_exceeded": False,
            }
            self._sessions[session_id] = session
        return session

    def _charge_session(self, session_id: str, cost: int) -> List[Dict[str, object]]:
        notifications: List[Dict[str, object]] = []
        with self._lock:
            session = self._get_or_create_session(session_id)
            session["total_cost"] += cost
            if session["threshold"] is not None and not session["threshold_exceeded"]:
                if session["total_cost"] >= session["threshold"]:
                    session["threshold_exceeded"] = True
                    notifications.append(
                        {
                            "type": "threshold_exceeded",
                            **dict(session),
                            "message": "The configured cost threshold has been exceeded.",
                        }
                    )
        return notifications
