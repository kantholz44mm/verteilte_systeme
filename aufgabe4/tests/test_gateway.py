import unittest

from math_factory.gateway import RoundRobinRouter


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_round_robin_router_cycles_workers(self):
        router = RoundRobinRouter(["http://mf-1:8081", "http://mf-2:8081"])

        self.assertEqual(await router.next_url(), "http://mf-1:8081")
        self.assertEqual(await router.next_url(), "http://mf-2:8081")
        self.assertEqual(await router.next_url(), "http://mf-1:8081")


if __name__ == "__main__":
    unittest.main()
