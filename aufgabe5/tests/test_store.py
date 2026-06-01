import unittest

from distributed_chat.hlc import HLCTimestamp
from distributed_chat.models import ChatMessage, GossipEnvelope, PeerInfo
from distributed_chat.store import ChatStore


class ChatStoreTests(unittest.TestCase):
    def test_messages_are_returned_in_hlc_order(self) -> None:
        store = ChatStore(PeerInfo("self", "http://self"))
        later = ChatMessage("general", "alice", "second", HLCTimestamp(20, 0, "a"), 20)
        earlier = ChatMessage("general", "bob", "first", HLCTimestamp(10, 0, "b"), 10)

        store.store_message(later)
        store.store_message(earlier)

        self.assertEqual([message.text for message in store.room_messages("general")], ["first", "second"])

    def test_duplicate_messages_are_ignored(self) -> None:
        store = ChatStore(PeerInfo("self", "http://self"))
        message = ChatMessage("general", "alice", "hello", HLCTimestamp(1, 0, "a"), 1)

        self.assertTrue(store.store_message(message))
        self.assertFalse(store.store_message(message))
        self.assertEqual(len(store.room_messages("general")), 1)

    def test_rooms_returns_known_chat_rooms(self) -> None:
        store = ChatStore(PeerInfo("self", "http://self"))
        store.store_message(ChatMessage("team", "alice", "hello", HLCTimestamp(1, 0, "a"), 1))
        store.store_message(ChatMessage("projekt", "bob", "status", HLCTimestamp(2, 0, "b"), 2))

        self.assertEqual(store.rooms(), ["projekt", "team"])

    def test_gossip_envelope_is_always_qos_2(self) -> None:
        message = ChatMessage("general", "alice", "hello", HLCTimestamp(1, 0, "a"), 1)

        self.assertEqual(GossipEnvelope(message).qos, 2)
        with self.assertRaises(ValueError):
            GossipEnvelope(message, qos=1)


if __name__ == "__main__":
    unittest.main()
