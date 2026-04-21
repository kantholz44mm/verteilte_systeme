import json
import unittest

from math_factory.rpc import process_jsonrpc_bytes
from math_factory.state import MathFactoryState


class JsonRpcTests(unittest.TestCase):
    def test_successful_request_returns_result(self):
        state = MathFactoryState()
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "addition",
                "params": {"a": 3, "b": 4, "session_id": "client-1"},
            }
        ).encode("utf-8")

        response = json.loads(process_jsonrpc_bytes(state, payload).decode("utf-8"))

        self.assertEqual(response["result"], 7)
        self.assertEqual(state.get_session("client-1")["total_cost"], 2)

    def test_unknown_method_returns_jsonrpc_error(self):
        state = MathFactoryState()
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": 2, "method": "unknown", "params": {}}
        ).encode("utf-8")

        response = json.loads(process_jsonrpc_bytes(state, payload).decode("utf-8"))

        self.assertEqual(response["error"]["code"], -32601)

    def test_notification_returns_no_http_body(self):
        state = MathFactoryState()
        payload = json.dumps(
            {"jsonrpc": "2.0", "method": "addition", "params": {"a": 1, "b": 2}}
        ).encode("utf-8")

        response = process_jsonrpc_bytes(state, payload)

        self.assertIsNone(response)


if __name__ == "__main__":
    unittest.main()

