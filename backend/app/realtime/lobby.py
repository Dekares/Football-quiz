"""Lobi ve state makinesi."""
from __future__ import annotations

import asyncio
import secrets
import string
import time
from dataclasses import dataclass, field
from typing import Any

LOBBY_CODE_ALPHABET = string.ascii_uppercase + string.digits
LOBBY_CODE_LEN = 6
# Lobi kapasitesi moda bağlı: Düello (mc/free) 6 kişi, Harman 1v1 (duel) 2 kişi.
MAX_PLAYERS_DEFAULT = 6
MAX_PLAYERS_DUEL = 2
MIN_PLAYERS = 2
MAX_LOBBIES = 5000               # toplam aktif lobi tavanı (bellek DoS koruması)

ROUND_DURATION_S = 20
ROUND_RESULT_DURATION_S = 3
DISCONNECT_GRACE_S = 30
PICK_DURATION_S = 15  # düello: seçici takım seçmezse sunucu otomatik seçer
MAX_SCORELESS_ROUNDS = 8  # üst üste bu kadar tur kimse skor yapmazsa oyun biter (stalemate)

# Idle lobi temizliği: bu süre boyunca hiç etkinlik görmeyen lobi kapatılır.
IDLE_LOBBY_TIMEOUT_S = 1800       # 30 dk
IDLE_SWEEP_INTERVAL_S = 120       # tarama periyodu

VALID_MODES = {"mc", "free", "duel"}
VALID_DIFFICULTIES = {"easy", "medium", "hard"}
TARGET_SCORE_MIN = 3
TARGET_SCORE_MAX = 50

DEFAULT_SETTINGS = {
    "mode": "mc",
    "difficulty": "medium",
    "target_score": 7,
}


def generate_lobby_code() -> str:
    return "".join(secrets.choice(LOBBY_CODE_ALPHABET) for _ in range(LOBBY_CODE_LEN))


def generate_player_token() -> str:
    return secrets.token_urlsafe(24)


@dataclass
class Player:
    player_id: str
    nickname: str
    token: str
    sid: str | None = None
    score: int = 0
    joined_at: float = field(default_factory=time.time)
    disconnected_at: float | None = None
    answered_this_round: bool = False
    was_correct: bool = False
    answer_text: str | None = None  # free modda gönderilen metin (tur sonu ekranında gösterilir)

    def is_connected(self) -> bool:
        return self.sid is not None

    def public_dict(self) -> dict[str, Any]:
        return {
            "player_id": self.player_id,
            "nickname": self.nickname,
            "score": self.score,
            "connected": self.is_connected(),
        }


@dataclass
class PickState:
    """Düello: iki seçici sırayla birer takım seçer (önce A, sonra B)."""
    picker_a: str
    picker_b: str
    turn: str = "a"                     # 'a' -> 'b'
    club_a: dict[str, Any] | None = None
    club_b: dict[str, Any] | None = None

    def public_dict(self, lobby: "Lobby") -> dict[str, Any]:
        def nick(pid: str) -> str:
            p = lobby.players.get(pid)
            return p.nickname if p else "?"
        # Seçilen takımların KİMLİĞİ gizlenir: rakip, tur başlamadan görmesin.
        # İki takım da round_start'ta aynı anda açılır. Burada yalnız "seçildi mi".
        return {
            "picker_a": self.picker_a, "picker_a_nick": nick(self.picker_a),
            "picker_b": self.picker_b, "picker_b_nick": nick(self.picker_b),
            "turn": self.turn,
            "a_chosen": self.club_a is not None,
            "b_chosen": self.club_b is not None,
        }


@dataclass
class Round:
    round_no: int
    club1: dict[str, Any]  # {club_id, name, logo_url}
    club2: dict[str, Any]
    correct_player: dict[str, Any] | None  # mc/free: doğru oyuncu; duel: None (sonda örnek açılır)
    choices: list[dict[str, Any]] | None  # mc modunda 4 şık, diğerlerinde None
    starts_at: float
    ends_at: float
    first_correct_player_id: str | None = None


@dataclass
class Lobby:
    code: str
    host_id: str
    players: dict[str, Player] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_SETTINGS))
    phase: str = "WAITING"  # WAITING | PICKING | IN_ROUND | ROUND_RESULT | GAME_OVER
    round_no: int = 0
    current_round: Round | None = None
    recent_pairs: list[tuple[int, int]] = field(default_factory=list)  # son 10 tur
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time, compare=False)  # idle reaper için
    winner_id: str | None = None
    pick: "PickState | None" = None      # düello: aktif seçim fazı
    picker_cursor: int = 0               # düello: seçicileri turlar arası döndürür
    scoreless_rounds: int = 0            # üst üste skorsuz tur sayacı (stalemate tespiti)
    # Cevap işlemeyi seri hale getirir (TOCTOU: iki doğru cevap çift puan almasın).
    answer_lock: asyncio.Lock = field(default_factory=asyncio.Lock, compare=False, repr=False)

    def player_list(self) -> list[dict[str, Any]]:
        return [p.public_dict() for p in self.players.values()]

    def connected_players(self) -> list[Player]:
        return [p for p in self.players.values() if p.is_connected()]

    def can_start(self) -> bool:
        return (
            self.phase in ("WAITING", "GAME_OVER")
            and len(self.connected_players()) >= MIN_PLAYERS
        )

    def max_players(self) -> int:
        return MAX_PLAYERS_DUEL if self.settings.get("mode") == "duel" else MAX_PLAYERS_DEFAULT

    def is_full(self) -> bool:
        return len(self.players) >= self.max_players()

    def add_player(self, nickname: str) -> Player:
        pid = secrets.token_urlsafe(8)
        player = Player(player_id=pid, nickname=nickname, token=generate_player_token())
        self.players[pid] = player
        return player

    def remove_player(self, player_id: str) -> None:
        self.players.pop(player_id, None)
        if player_id == self.host_id:
            self._promote_new_host()

    def _promote_new_host(self) -> None:
        connected = [p for p in self.connected_players() if p.joined_at is not None]
        if not connected:
            self.host_id = ""
            return
        connected.sort(key=lambda p: p.joined_at)
        self.host_id = connected[0].player_id

    def public_state(self) -> dict[str, Any]:
        state = {
            "code": self.code,
            "host_id": self.host_id,
            "phase": self.phase,
            "settings": self.settings,
            "players": self.player_list(),
            "max_players": self.max_players(),
            "round_no": self.round_no,
        }
        if self.phase == "PICKING" and self.pick:
            state["pick"] = self.pick.public_dict(self)
        return state

    def reset_round_answers(self) -> None:
        for p in self.players.values():
            p.answered_this_round = False
            p.was_correct = False
            p.answer_text = None

    def reached_target(self) -> Player | None:
        target = self.settings.get("target_score", 7)
        winners = [p for p in self.players.values() if p.score >= target]
        if not winners:
            return None
        winners.sort(key=lambda p: (-p.score, p.joined_at))
        return winners[0]


def validate_settings(raw: dict[str, Any]) -> dict[str, Any]:
    """Host'tan gelen ayarları doğrula ve normalize et."""
    mode = raw.get("mode", DEFAULT_SETTINGS["mode"])
    if mode not in VALID_MODES:
        mode = DEFAULT_SETTINGS["mode"]

    difficulty = raw.get("difficulty", DEFAULT_SETTINGS["difficulty"])
    if difficulty not in VALID_DIFFICULTIES:
        difficulty = DEFAULT_SETTINGS["difficulty"]

    try:
        target_score = int(raw.get("target_score", DEFAULT_SETTINGS["target_score"]))
    except (TypeError, ValueError):
        target_score = DEFAULT_SETTINGS["target_score"]
    if target_score < TARGET_SCORE_MIN:
        target_score = TARGET_SCORE_MIN
    elif target_score > TARGET_SCORE_MAX:
        target_score = TARGET_SCORE_MAX

    return {"mode": mode, "difficulty": difficulty, "target_score": target_score}


def clean_nickname(nickname: str) -> str:
    nick = (nickname or "").strip()
    # sadece printable, max 16 karakter
    nick = "".join(c for c in nick if c.isprintable())
    return nick[:16] or "Player"
