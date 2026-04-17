"""In-memory lobi kayıt defteri.

eventlet monkey-patch sonrası threading.Lock aslında eventlet'in green-lock'udur.
Tek worker olduğu için bu yeterli.
"""
from __future__ import annotations

import threading
from typing import Callable

from .lobby import Lobby, generate_lobby_code


class LobbyRegistry:
    def __init__(self) -> None:
        self._lobbies: dict[str, Lobby] = {}
        self._sid_index: dict[str, tuple[str, str]] = {}  # sid -> (code, player_id)
        self._lock = threading.RLock()

    # ---- CRUD ----
    def create(self, host_nickname: str) -> Lobby:
        with self._lock:
            for _ in range(20):
                code = generate_lobby_code()
                if code not in self._lobbies:
                    break
            else:
                raise RuntimeError("Yeterince benzersiz lobi kodu üretilemedi")

            lobby = Lobby(code=code, host_id="")
            player = lobby.add_player(host_nickname)
            lobby.host_id = player.player_id
            self._lobbies[code] = lobby
            return lobby

    def get(self, code: str) -> Lobby | None:
        if not code:
            return None
        return self._lobbies.get(code.upper())

    def remove(self, code: str) -> None:
        with self._lock:
            lobby = self._lobbies.pop(code.upper(), None)
            if not lobby:
                return
            for sid in list(self._sid_index.keys()):
                c, _ = self._sid_index[sid]
                if c == lobby.code:
                    self._sid_index.pop(sid, None)

    # ---- sid index ----
    def bind_sid(self, sid: str, code: str, player_id: str) -> None:
        with self._lock:
            # Aynı sid başka bir lobide kayıtlıysa temizle
            self._sid_index.pop(sid, None)
            self._sid_index[sid] = (code.upper(), player_id)

    def unbind_sid(self, sid: str) -> tuple[str, str] | None:
        with self._lock:
            return self._sid_index.pop(sid, None)

    def lookup_sid(self, sid: str) -> tuple[Lobby, str] | None:
        with self._lock:
            info = self._sid_index.get(sid)
            if not info:
                return None
            code, pid = info
            lobby = self._lobbies.get(code)
            if not lobby or pid not in lobby.players:
                return None
            return lobby, pid

    def with_lock(self, fn: Callable[[], None]) -> None:
        with self._lock:
            fn()

    def all_codes(self) -> list[str]:
        with self._lock:
            return list(self._lobbies.keys())


# Modül seviyesinde tekil
registry = LobbyRegistry()
