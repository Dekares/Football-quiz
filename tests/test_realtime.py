import unittest

from backend.app.realtime.lobby import Lobby, clean_nickname, validate_settings
from backend.app.realtime.store import LobbyRegistry


class RealtimeStateTests(unittest.TestCase):
    def test_lobby_starts_only_with_two_connected_players_in_idle_phase(self):
        lobby = Lobby(code="ABC123", host_id="")
        host = lobby.add_player("Host")
        guest = lobby.add_player("Guest")
        lobby.host_id = host.player_id

        self.assertFalse(lobby.can_start())
        host.sid = "sid-host"
        guest.sid = "sid-guest"
        self.assertTrue(lobby.can_start())

        lobby.phase = "STARTING"
        self.assertFalse(lobby.can_start())
        lobby.phase = "GAME_OVER"
        self.assertTrue(lobby.can_start())
        guest.sid = None
        self.assertFalse(lobby.can_start())

    def test_settings_and_nickname_are_bounded(self):
        settings = validate_settings({
            "mode": "invalid",
            "difficulty": "invalid",
            "target_score": 10_000,
        })
        self.assertEqual(settings, {
            "mode": "mc",
            "difficulty": "medium",
            "target_score": 50,
        })
        self.assertEqual(clean_nickname("  A\x00B" + "x" * 30), "AB" + "x" * 14)

    def test_registry_remove_clears_socket_index(self):
        registry = LobbyRegistry()
        lobby = registry.create("Host")
        host = lobby.players[lobby.host_id]
        host.sid = "sid-host"
        registry.bind_sid(host.sid, lobby.code, host.player_id)

        self.assertIsNotNone(registry.lookup_sid(host.sid))
        registry.remove(lobby.code)
        self.assertIsNone(registry.lookup_sid(host.sid))
        self.assertEqual(registry.count(), 0)


if __name__ == "__main__":
    unittest.main()
