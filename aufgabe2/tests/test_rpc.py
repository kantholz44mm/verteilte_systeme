import json
import unittest

from math_factory.rpc import process_jsonrpc_bytes_with_notifications
from math_factory.state import MathFactoryState


class JsonRpcTests(unittest.TestCase):
    def test_successful_request_returns_result(self):
        """JSON-RPC addition returns 7 and charges the session with cost 2."""
        state = MathFactoryState()
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "addition",
                "params": {"a": 3, "b": 4, "session_id": "client-1"},
            }
        ).encode("utf-8")

        response_body, notifications = process_jsonrpc_bytes_with_notifications(state, payload)
        response = json.loads(response_body.decode("utf-8"))

        self.assertEqual(response["result"], 7)
        self.assertEqual(notifications, [])
        self.assertEqual(state._get_or_create_session("client-1")["total_cost"], 2)

    def test_unknown_method_returns_jsonrpc_error(self):
        """Unknown JSON-RPC methods return the Method not found error code."""
        state = MathFactoryState()
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": 2, "method": "unknown", "params": {}}
        ).encode("utf-8")

        response_body, notifications = process_jsonrpc_bytes_with_notifications(state, payload)
        response = json.loads(response_body.decode("utf-8"))

        self.assertEqual(response["error"]["code"], -32601)
        self.assertEqual(notifications, [])

    def test_notification_returns_no_http_body(self):
        """JSON-RPC notifications without an id produce no response body."""
        state = MathFactoryState()
        payload = json.dumps(
            {"jsonrpc": "2.0", "method": "addition", "params": {"a": 1, "b": 2}}
        ).encode("utf-8")

        response, notifications = process_jsonrpc_bytes_with_notifications(state, payload)

        self.assertIsNone(response)
        self.assertEqual(notifications, [])


if __name__ == "__main__":
    unittest.main()
