import json
import unittest

from math_factory.rpc import process_jsonrpc_bytes_with_notifications
from math_factory.worker import AccountingMathFactoryState


class WorkerAccountingTests(unittest.TestCase):
    def test_worker_adds_operation_charged_notification(self):
        state = AccountingMathFactoryState("mf-1")
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": "req-1",
                "method": "addition",
                "params": {"a": 3, "b": 4, "session_id": "app-1"},
            }
        ).encode("utf-8")

        response_body, notifications = process_jsonrpc_bytes_with_notifications(state, payload)

        self.assertEqual(json.loads(response_body.decode("utf-8"))["result"], 7)
        accounting_events = [
            notification for notification in notifications if notification["type"] == "operation_charged"
        ]
        self.assertEqual(accounting_events[0]["app_id"], "app-1")
        self.assertEqual(accounting_events[0]["instance_id"], "mf-1")
        self.assertEqual(accounting_events[0]["cost"], 2)


if __name__ == "__main__":
    unittest.main()
