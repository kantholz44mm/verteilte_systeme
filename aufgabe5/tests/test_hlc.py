import unittest

from distributed_chat.hlc import HLCTimestamp, HybridLogicalClock


class HybridLogicalClockTests(unittest.TestCase):
    def test_local_events_are_monotonic(self) -> None:
        clock = HybridLogicalClock("a", initial_wall_ms=1)

        first = clock.now()
        second = clock.now()

        self.assertGreater(second, first)

    def test_observe_remote_timestamp_moves_clock_forward(self) -> None:
        clock = HybridLogicalClock("a", initial_wall_ms=1)
        local = clock.now()
        observed = clock.observe(HLCTimestamp(local.wall_ms + 10_000, 3, "b"))

        self.assertGreaterEqual(observed.wall_ms, local.wall_ms + 10_000)
        self.assertEqual(observed.counter, 4)


if __name__ == "__main__":
    unittest.main()
