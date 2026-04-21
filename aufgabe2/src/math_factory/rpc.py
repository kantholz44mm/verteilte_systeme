from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .operations import OperationValidationError
from .state import MathFactoryState, OperationDisabledError, UnknownOperationError


JSON_RPC_VERSION = "2.0"


@dataclass
class RPCError(Exception):
    code: int
    message: str
    data: Optional[Any] = None


def process_jsonrpc_bytes(state: MathFactoryState, payload: bytes) -> Optional[bytes]:
    try:
        request = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _dump_json(_error_response(None, -32700, "Parse error"))

    if isinstance(request, list):
        if not request:
            return _dump_json(_error_response(None, -32600, "Invalid Request"))
        responses = [response for item in request if (response := _handle_single(state, item)) is not None]
        if not responses:
            return None
        return _dump_json(responses)

    response = _handle_single(state, request)
    if response is None:
        return None
    return _dump_json(response)


def _handle_single(state: MathFactoryState, request: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(request, dict):
        return _error_response(None, -32600, "Invalid Request")

    request_id = request.get("id")
    is_notification = "id" not in request

    try:
        if request.get("jsonrpc") != JSON_RPC_VERSION:
            raise RPCError(-32600, "Invalid Request", "'jsonrpc' must be '2.0'.")

        method = request.get("method")
        if not isinstance(method, str) or not method:
            raise RPCError(-32600, "Invalid Request", "'method' must be a non-empty string.")

        result = _dispatch(state, method, request.get("params"))
        if is_notification:
            return None
        return {"jsonrpc": JSON_RPC_VERSION, "result": result, "id": request_id}
    except RPCError as error:
        if is_notification:
            return None
        return _error_response(request_id, error.code, error.message, error.data)


def _dispatch(state: MathFactoryState, method: str, params: Any) -> Any:
    try:
        if method == "factorial":
            arguments, session_id = _parse_factorial_params(params)
        elif method in {"addition", "subtraction", "multiplication", "division", "power"}:
            arguments, session_id = _parse_binary_params(params)
        else:
            raise RPCError(-32601, "Method not found", method)
        return state.execute(method, arguments, session_id=session_id)
    except UnknownOperationError:
        raise RPCError(-32601, "Method not found", method)
    except OperationDisabledError:
        raise RPCError(-32010, "Operation disabled", method)
    except OperationValidationError as error:
        raise RPCError(-32602, "Invalid params", str(error))
    except ValueError as error:
        raise RPCError(-32602, "Invalid params", str(error))
    except RPCError:
        raise
    except Exception as error:
        raise RPCError(-32603, "Internal error", str(error))


def _parse_binary_params(params: Any) -> Tuple[List[Any], Optional[str]]:
    if isinstance(params, dict):
        if "a" not in params or "b" not in params:
            raise RPCError(-32602, "Invalid params", "Parameters 'a' and 'b' are required.")
        return [params["a"], params["b"]], _extract_session_id(params.get("session_id"))
    if isinstance(params, list):
        if len(params) not in (2, 3):
            raise RPCError(-32602, "Invalid params", "Expected [a, b] or [a, b, session_id].")
        session_id = _extract_session_id(params[2]) if len(params) == 3 else None
        return [params[0], params[1]], session_id
    raise RPCError(-32602, "Invalid params", "Parameters must be an object or an array.")


def _parse_factorial_params(params: Any) -> Tuple[List[Any], Optional[str]]:
    if isinstance(params, dict):
        if "a" in params:
            value = params["a"]
        elif "n" in params:
            value = params["n"]
        else:
            raise RPCError(-32602, "Invalid params", "Parameter 'a' or 'n' is required.")
        return [value], _extract_session_id(params.get("session_id"))
    if isinstance(params, list):
        if len(params) not in (1, 2):
            raise RPCError(-32602, "Invalid params", "Expected [a] or [a, session_id].")
        session_id = _extract_session_id(params[1]) if len(params) == 2 else None
        return [params[0]], session_id
    raise RPCError(-32602, "Invalid params", "Parameters must be an object or an array.")


def _extract_session_id(value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise RPCError(-32602, "Invalid params", "'session_id' must be a non-empty string.")
    return value


def _error_response(request_id: Any, code: int, message: str, data: Optional[Any] = None) -> Dict[str, Any]:
    error: Dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": JSON_RPC_VERSION, "error": error, "id": request_id}


def _dump_json(payload: Any) -> bytes:
    return json.dumps(payload, indent=2).encode("utf-8")

