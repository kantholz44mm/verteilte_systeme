from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from .state import MathFactoryState


JSON_RPC_VERSION = "2.0"


def process_jsonrpc_bytes_with_notifications(
    state: MathFactoryState, payload: bytes
) -> Tuple[Optional[bytes], List[Dict[str, Any]]]:
    try:
        request = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return json.dumps(_error_response(None, -32700, "Parse error"), indent=2).encode("utf-8"), []

    if isinstance(request, list):
        notifications: List[Dict[str, Any]] = []
        responses = []
        for item in request:
            response, item_notifications = _handle_single(state, item)
            notifications.extend(item_notifications)
            if response is not None:
                responses.append(response)
        if not responses:
            return None, notifications
        return json.dumps(responses, indent=2).encode("utf-8"), notifications

    response, notifications = _handle_single(state, request)
    if response is None:
        return None, notifications
    return json.dumps(response, indent=2).encode("utf-8"), notifications


def _handle_single(
    state: MathFactoryState, request: Any
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    if not isinstance(request, dict):
        request = {}

    request_id = request.get("id")
    is_notification = "id" not in request

    try:
        result, notifications = _dispatch(state, request.get("method"), request.get("params"))
    except KeyError:
        if is_notification:
            return None, []
        return _error_response(request_id, -32601, "Method not found", request.get("method")), []
    except RuntimeError:
        if is_notification:
            return None, []
        return _error_response(request_id, -32010, "Operation disabled", request.get("method")), []
    except ValueError as error:
        if is_notification:
            return None, []
        return _error_response(request_id, -32602, "Invalid params", str(error)), []
    except Exception as error:
        if is_notification:
            return None, []
        return _error_response(request_id, -32603, "Internal error", str(error)), []

    if is_notification:
        return None, notifications
    return {"jsonrpc": JSON_RPC_VERSION, "result": result, "id": request_id}, notifications


def _dispatch(state: MathFactoryState, method: Any, params: Any) -> Tuple[Any, List[Dict[str, Any]]]:
    if method == "factorial":
        arguments, session_id = _parse_factorial_params(params)
    else:
        arguments, session_id = _parse_binary_params(params)
    return state.execute_with_notifications(method, arguments, session_id=session_id)


def _parse_binary_params(params: Any) -> Tuple[List[Any], Optional[str]]:
    if isinstance(params, dict):
        return [params.get("a"), params.get("b")], params.get("session_id")
    if isinstance(params, list):
        session_id = params[2] if len(params) > 2 else None
        first = params[0] if len(params) > 0 else None
        second = params[1] if len(params) > 1 else None
        return [first, second], session_id
    return [None, None], None


def _parse_factorial_params(params: Any) -> Tuple[List[Any], Optional[str]]:
    if isinstance(params, dict):
        return [params.get("a", params.get("n"))], params.get("session_id")
    if isinstance(params, list):
        session_id = params[1] if len(params) > 1 else None
        value = params[0] if len(params) > 0 else None
        return [value], session_id
    return [None], None


def _error_response(request_id: Any, code: int, message: str, data: Optional[Any] = None) -> Dict[str, Any]:
    error: Dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": JSON_RPC_VERSION, "error": error, "id": request_id}
