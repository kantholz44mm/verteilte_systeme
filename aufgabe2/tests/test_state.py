import unittest

from math_factory.state import MathFactoryState, OperationDisabledError


class MathFactoryStateTests(unittest.TestCase):
    def test_execute_addition_updates_session_costs(self):
        state = MathFactoryState()

        result = state.execute("addition", [2, 3], session_id="session-1")
        session = state.get_session("session-1")

        self.assertEqual(result, 5)
        self.assertEqual(session["total_cost"], 2)

    def test_threshold_notification_is_returned_once_when_crossed(self):
        state = MathFactoryState()

        threshold_update = state.set_threshold_with_notifications("session-1", 100)
        first_outcome = state.execute_with_notifications("factorial", [5], session_id="session-1")
        second_outcome = state.execute_with_notifications("addition", [1, 2], session_id="session-1")

        threshold_messages = [
            *[message for message in threshold_update.notifications if message["type"] == "threshold_exceeded"],
            *[message for message in first_outcome.notifications if message["type"] == "threshold_exceeded"],
            *[message for message in second_outcome.notifications if message["type"] == "threshold_exceeded"],
        ]
        self.assertEqual(len(threshold_messages), 1)

    def test_disabled_operation_raises(self):
        state = MathFactoryState()
        state.update_operation("power", enabled=False)

        with self.assertRaises(OperationDisabledError):
            state.execute("power", [2, 4], session_id="session-1")


if __name__ == "__main__":
    unittest.main()
