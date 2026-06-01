import unittest

from fastapi.testclient import TestClient

from math_factory.server import ConnectionManager, create_rest_app, create_rpc_app, create_ws_app
from math_factory.state import MathFactoryState


class FastApiIntegrationTests(unittest.TestCase):
    def test_rest_openapi_and_operation_update(self):
        """REST exposes OpenAPI, Swagger UI, and can update operation costs."""
        state = MathFactoryState()
        app = create_rest_app(state)

        with TestClient(app) as client:
            openapi_response = client.get("/openapi.json")
            self.assertEqual(openapi_response.status_code, 200)
            self.assertEqual(openapi_response.json()["info"]["title"], "Math Factory REST API")

            swagger_response = client.get("/docs")
            self.assertEqual(swagger_response.status_code, 200)
            self.assertIn("swagger-ui", swagger_response.text)

            update_response = client.patch(
                "/operations/power",
                json={"cost": 900, "enabled": False},
            )
            self.assertEqual(update_response.status_code, 200)
            self.assertEqual(update_response.json()["cost"], 900)
            self.assertFalse(update_response.json()["enabled"])

    def test_rpc_endpoint_and_websocket_registration(self):
        """RPC execution charges a registered WebSocket session and emits threshold_exceeded."""
        state = MathFactoryState()
        manager = ConnectionManager()
        rpc_app = create_rpc_app(state, manager)
        ws_app = create_ws_app(state, manager)

        with TestClient(ws_app) as ws_client:
            with ws_client.websocket_connect("/ws") as websocket:
                websocket.send_json({"action": "register", "session_id": "demo-session", "threshold": 100})

                registered_message = websocket.receive_json()
                threshold_message = websocket.receive_json()

                self.assertEqual(registered_message["type"], "registered")
                self.assertEqual(threshold_message["type"], "threshold_updated")

                with TestClient(rpc_app) as rpc_client:
                    rpc_response = rpc_client.post(
                        "/rpc",
                        json={
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "factorial",
                            "params": {"a": 5, "session_id": "demo-session"},
                        },
                    )
                    self.assertEqual(rpc_response.status_code, 200)
                    self.assertEqual(rpc_response.json()["result"], 120)

                threshold_exceeded_message = websocket.receive_json()
                self.assertEqual(threshold_exceeded_message["type"], "threshold_exceeded")
                self.assertEqual(threshold_exceeded_message["session_id"], "demo-session")


if __name__ == "__main__":
    unittest.main()
