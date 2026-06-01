import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from math_factory.data_manager import DataManagerStore, OperationEvent, create_app


class DataManagerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.store = DataManagerStore(str(root / "ops.sqlite3"), str(root / "cust.sqlite3"))

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

    async def test_operation_event_updates_ops_and_customer_state_atomically(self):
        await self.store.set_threshold("app-1", 10)
        result = await self.store.record_operation(
            OperationEvent(
                app_id="app-1",
                operation="addition",
                cost=2,
                instance_id="mf-1",
                request_id="req-1",
                result=7,
            )
        )

        self.assertEqual(result["snapshot"]["total_cost"], 2)
        self.assertEqual(result["notifications"], [])
        operations = await self.store.recent_operations()
        self.assertEqual(len(operations), 1)
        self.assertEqual(operations[0]["instance_id"], "mf-1")

    async def test_threshold_notification_is_emitted_once_on_crossing(self):
        await self.store.set_threshold("app-1", 5)

        first = await self.store.record_operation(
            OperationEvent(app_id="app-1", operation="addition", cost=2, instance_id="mf-1")
        )
        second = await self.store.record_operation(
            OperationEvent(app_id="app-1", operation="multiplication", cost=25, instance_id="mf-2")
        )
        third = await self.store.record_operation(
            OperationEvent(app_id="app-1", operation="subtraction", cost=3, instance_id="mf-3")
        )

        self.assertEqual(first["notifications"], [])
        self.assertEqual(second["notifications"][0]["type"], "threshold_exceeded")
        self.assertEqual(third["notifications"], [])


class DataManagerApiTests(unittest.TestCase):
    def test_rest_api_exposes_costs_thresholds_and_events(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = DataManagerStore(str(root / "ops.sqlite3"), str(root / "cust.sqlite3"))
            app = create_app(store)

            with TestClient(app) as client:
                threshold = client.put("/apps/demo/threshold", json={"threshold": 4})
                self.assertEqual(threshold.status_code, 200)
                self.assertEqual(threshold.json()["threshold"], 4)

                event = client.post(
                    "/events/operation",
                    json={
                        "app_id": "demo",
                        "operation": "addition",
                        "cost": 5,
                        "instance_id": "mf-1",
                    },
                )
                self.assertEqual(event.status_code, 200)
                self.assertEqual(event.json()["snapshot"]["total_cost"], 5)
                self.assertEqual(event.json()["notifications"][0]["type"], "threshold_exceeded")

                costs = client.get("/apps/demo/costs")
                self.assertEqual(costs.json()["total_cost"], 5)


if __name__ == "__main__":
    unittest.main()
