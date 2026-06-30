"""Socket.IO event handler'ları (python-socketio AsyncServer / asyncio).

server.py şöyle kaydeder:
    sio = socketio.AsyncServer(async_mode="asgi", ...)
    register_handlers(sio)

DB salt-okunur ve paylaşımlı; bloklayıcı sorgular backend.app.db.query ile
thread havuzunda çalışır. Lobi state'i in-memory'dir (tek node; Redis yok).
"""
from __future__ import annotations

import sqlite3
import time
from typing import Any

import socketio

from ..db import query
from ..ratelimit import RateLimiter
from .lobby import (
    DISCONNECT_GRACE_S,
    DUEL_PICK_DURATION_S,
    DUEL_ROUND_DURATION_S,
    IDLE_LOBBY_TIMEOUT_S,
    IDLE_SWEEP_INTERVAL_S,
    MAX_LOBBIES,
    MAX_SCORELESS_ROUNDS,
    MIN_PLAYERS,
    ROUND_DURATION_S,
    ROUND_RESULT_DURATION_S,
    Lobby,
    PickState,
    Round,
    clean_nickname,
    validate_settings,
)
from .matchmaking import pick_club_pair, random_partner
from .questions import (
    build_question,
    get_player_public,
    pair_is_valid,
    pick_reveal_player,
    verify_free_answer,
)
from .store import registry

ANSWER_TEXT_MAX = 64  # serbest cevap metni üst sınırı (DoS: sınırsız LIKE'ı engeller)


def _pick_round(
    c: sqlite3.Connection, settings: dict[str, Any], recent_pairs: list
) -> tuple[dict | None, dict | None]:
    """Tek bağlantıda uygun (pair, question) bulana kadar dener (max 8)."""
    for _ in range(8):
        pair = pick_club_pair(c, settings["difficulty"], recent_pairs)
        if not pair:
            return None, None
        question = build_question(c, pair[0], pair[1], settings["mode"])
        if question:
            return pair, question
    return None, None


def register_handlers(sio: socketio.AsyncServer) -> None:
    """Tüm Socket.IO event handler'larını kaydeder."""

    # Per-sid event hız limiti (spam / DoS koruması).
    event_limiter = RateLimiter(rate_per_sec=10, burst=20)
    reaper_state = {"started": False}

    # ---------- Idle lobi temizleyici ----------

    async def _reaper_loop() -> None:
        """Uzun süre etkinlik görmeyen (terk edilmiş) lobileri periyodik kapatır."""
        while True:
            await sio.sleep(IDLE_SWEEP_INTERVAL_S)
            now = time.time()
            for code in registry.all_codes():
                lobby = registry.get(code)
                if lobby and now - lobby.last_activity > IDLE_LOBBY_TIMEOUT_S:
                    await sio.emit("lobby_closed", {"reason": "idle"}, to=code)
                    registry.remove(code)

    # ---------- Yardımcılar ----------

    async def _broadcast_state(lobby: Lobby) -> None:
        await sio.emit("lobby_state", lobby.public_state(), to=lobby.code)

    async def _emit_error(sid: str, code: str, message: str) -> None:
        await sio.emit("error", {"code": code, "message": message}, to=sid)

    async def _start_new_round(lobby: Lobby) -> None:
        if lobby.round_no > 0 and len(lobby.connected_players()) < MIN_PLAYERS:
            await _end_game_abandoned(lobby, reason="opponent_left")
            return
        if lobby.settings["mode"] == "duel":
            await _start_pick_phase(lobby)
            return

        pair, question = await query(
            lambda c: _pick_round(c, lobby.settings, lobby.recent_pairs)
        )
        if not pair or not question:
            await sio.emit("error", {
                "code": "no_question",
                "message": "Bu zorluk için uygun soru bulunamadı",
            }, to=lobby.code)
            lobby.phase = "WAITING"
            await _broadcast_state(lobby)
            return

        club_a, club_b = pair
        lobby.round_no += 1
        lobby.reset_round_answers()
        lobby.phase = "IN_ROUND"

        now = time.time()
        round_obj = Round(
            round_no=lobby.round_no,
            club1=club_a,
            club2=club_b,
            correct_player=question["correct_player"],
            choices=question.get("choices"),
            starts_at=now,
            ends_at=now + ROUND_DURATION_S,
        )
        lobby.current_round = round_obj

        # Doğru cevap istemciye GÖNDERİLMEZ (tur bitişinde açıklanır).
        payload: dict[str, Any] = {
            "round_no": round_obj.round_no,
            "club1": club_a,
            "club2": club_b,
            "mode": lobby.settings["mode"],
            "ends_at": round_obj.ends_at,
            "duration_s": ROUND_DURATION_S,
        }
        if round_obj.choices:
            payload["choices"] = [
                {"player_id": c["player_id"], "name": c["name"], "image_url": c.get("image_url")}
                for c in round_obj.choices
            ]

        await sio.emit("round_start", payload, to=lobby.code)
        await _broadcast_state(lobby)
        sio.start_background_task(_round_timer, lobby.code, round_obj.round_no, round_obj.ends_at)

    # ---------- Harman 1v1: iki oyuncu aynı anda takım seçer ----------

    async def _start_pick_phase(lobby: Lobby) -> None:
        """İki seçiciyi (turlar arası dönen) belirle ve eşzamanlı seçim fazını başlat."""
        connected = sorted(lobby.connected_players(), key=lambda p: p.joined_at)
        if len(connected) < MIN_PLAYERS:
            if lobby.round_no > 0:                 # oyun başlamışken rakip kaçtı → bitir
                await _end_game_abandoned(lobby, reason="opponent_left")
            else:                                  # henüz başlamadı → bekleme odasına dön
                lobby.phase = "WAITING"
                lobby.pick = None
                await _broadcast_state(lobby)
            return

        n = len(connected)
        i = lobby.picker_cursor % n
        a = connected[i]
        b = connected[(i + 1) % n]
        lobby.picker_cursor = (lobby.picker_cursor + 1) % n

        now = time.time()
        pick = PickState(
            picker_a=a.player_id, picker_b=b.player_id,
            ends_at=now + DUEL_PICK_DURATION_S,
        )
        lobby.pick = pick
        lobby.phase = "PICKING"

        await sio.emit("pick_phase", {
            "round_no": lobby.round_no + 1,
            "pick": pick.public_dict(lobby),
            "duration_s": DUEL_PICK_DURATION_S,
        }, to=lobby.code)
        await _broadcast_state(lobby)
        sio.start_background_task(_pick_timer, lobby.code, pick)

    async def _pick_timer(code: str, pick: PickState) -> None:
        """Süre dolunca eksik/uyumsuz seçimleri sunucu rastgele tamamlar."""
        await sio.sleep(DUEL_PICK_DURATION_S + 0.2)
        lobby = registry.get(code)
        if not lobby or lobby.pick is not pick or lobby.phase != "PICKING":
            return
        await _finalize_pick(lobby)

    async def _finalize_pick(lobby: Lobby) -> None:
        """İki seçim de gelince (ya da süre dolunca) tur sorusunu kurup başlat.

        Seçimler gizli + eşzamanlı olduğundan çiftin ORTAK oyuncusu garanti değil;
        eksik/uyumsuzsa sunucu tamamlar → her zaman çözülebilir tur.
        """
        pick = lobby.pick
        if not pick or lobby.phase != "PICKING":
            return
        if len(lobby.connected_players()) < MIN_PLAYERS:
            await _end_game_abandoned(lobby, reason="opponent_left")
            return
        difficulty = lobby.settings["difficulty"]

        def work(c: sqlite3.Connection):
            a, b = pick.club_a, pick.club_b
            if a and b:
                if pair_is_valid(c, a["club_id"], b["club_id"]):
                    return a, b
                # ponytail: ortak oyuncu yoksa B'yi A'nın bir partneriyle değiştir (nadir kenar durum)
                partner = random_partner(c, a["club_id"])
                return (a, partner) if partner else None
            if a and not b:
                partner = random_partner(c, a["club_id"])
                return (a, partner) if partner else None
            if b and not a:
                partner = random_partner(c, b["club_id"])
                return (partner, b) if partner else None
            pair = pick_club_pair(c, difficulty, lobby.recent_pairs)
            return (pair[0], pair[1]) if pair else None

        res = await query(work)
        if not res:
            lobby.phase = "WAITING"
            lobby.pick = None
            await _broadcast_state(lobby)
            return
        pick.club_a, pick.club_b = res
        await _start_answer_phase(lobby)

    async def _start_answer_phase(lobby: Lobby) -> None:
        """Seçilen iki kulüple cevap turunu başlat (free-style; ilk doğru +1, anında biter)."""
        pick = lobby.pick
        if not pick or not pick.club_a or not pick.club_b:
            return
        club_a, club_b = pick.club_a, pick.club_b

        lobby.round_no += 1
        lobby.reset_round_answers()
        lobby.phase = "IN_ROUND"
        lobby.pick = None

        now = time.time()
        round_obj = Round(
            round_no=lobby.round_no,
            club1=club_a,
            club2=club_b,
            correct_player=None,
            choices=None,
            starts_at=now,
            ends_at=now + DUEL_ROUND_DURATION_S,
        )
        lobby.current_round = round_obj

        lobby.recent_pairs.append((club_a["club_id"], club_b["club_id"]))
        if len(lobby.recent_pairs) > 10:
            lobby.recent_pairs.pop(0)

        await sio.emit("round_start", {
            "round_no": round_obj.round_no,
            "club1": club_a,
            "club2": club_b,
            "mode": "duel",
            "ends_at": round_obj.ends_at,
            "duration_s": DUEL_ROUND_DURATION_S,
        }, to=lobby.code)
        await _broadcast_state(lobby)
        sio.start_background_task(_round_timer, lobby.code, round_obj.round_no, round_obj.ends_at)

    async def _round_timer(code: str, round_no: int, ends_at: float) -> None:
        """Süre dolarsa turu bitirir (süre moda göre: mc/free vs duel ends_at'tan gelir)."""
        await sio.sleep(max(0.0, ends_at - time.time()) + 0.2)
        lobby = registry.get(code)
        if not lobby or not lobby.current_round:
            return
        if lobby.current_round.round_no != round_no or lobby.phase != "IN_ROUND":
            return
        await _end_round(lobby, reason="timeout")

    async def _end_round(lobby: Lobby, reason: str) -> None:
        # Idempotent: yalnız IN_ROUND'dan çıkışta çalışır. Aynı turun timeout'u ile
        # "çözüldü" yolu yarışırsa (ya da çift submit) ikinci çağrı erken döner.
        if lobby.phase != "IN_ROUND" or not lobby.current_round:
            return
        lobby.phase = "ROUND_RESULT"
        rnd = lobby.current_round

        scores = {p.player_id: p.score for p in lobby.players.values()}
        correct_ids = [p.player_id for p in lobby.players.values() if p.was_correct]
        player_results = {
            p.player_id: {
                "answered": p.answered_this_round,
                "correct": p.was_correct,
                "answer_text": p.answer_text,
            }
            for p in lobby.players.values()
        }

        # Duel: çözen olduysa TAM OLARAK bilinen oyuncu açılır (solve'da rnd.correct_player set edildi);
        # kimse çözemediyse kayda değer bir ortak oyuncu örnek olarak gösterilir.
        correct_answer = rnd.correct_player
        solver_id = None
        if lobby.settings["mode"] == "duel":
            solver_id = rnd.first_correct_player_id
            if not rnd.correct_player:
                correct_answer = await query(
                    lambda c: pick_reveal_player(c, rnd.club1["club_id"], rnd.club2["club_id"])
                )

        await sio.emit("round_end", {
            "round_no": rnd.round_no,
            "correct_answer": correct_answer,
            "scores": scores,
            "correct_player_ids": correct_ids,
            "player_results": player_results,
            "reason": reason,
            "solver_id": solver_id,
        }, to=lobby.code)

        # Stalemate sayacı: bu turda kimse skor yapmadıysa artır, yaptıysa sıfırla.
        lobby.scoreless_rounds = 0 if correct_ids else lobby.scoreless_rounds + 1

        winner = lobby.reached_target()
        if winner:
            lobby.phase = "GAME_OVER"
            lobby.winner_id = winner.player_id
            await sio.emit("game_over", {
                "winner": {"player_id": winner.player_id, "nickname": winner.nickname},
                "final_scores": scores,
            }, to=lobby.code)
            lobby.current_round = None
            await _broadcast_state(lobby)
            return

        if lobby.scoreless_rounds >= MAX_SCORELESS_ROUNDS:
            # Uzun süredir kimse skor yapmıyor (boşa dönen oyun) → lider/beraberlikle bitir.
            await _end_game_abandoned(lobby, reason="stalemate")
            return

        sio.start_background_task(_next_round_after_delay, lobby.code, rnd.round_no)

    async def _next_round_after_delay(code: str, prev_round_no: int) -> None:
        await sio.sleep(ROUND_RESULT_DURATION_S)
        lobby = registry.get(code)
        if not lobby or lobby.phase != "ROUND_RESULT":
            return
        if lobby.current_round and lobby.current_round.round_no != prev_round_no:
            return
        await _start_new_round(lobby)

    async def _maybe_end_round_if_all_answered(lobby: Lobby) -> None:
        if lobby.phase != "IN_ROUND":
            return
        connected = lobby.connected_players()
        if connected and all(p.answered_this_round for p in connected):
            await _end_round(lobby, reason="all_answered")

    async def _end_game_abandoned(lobby: Lobby, reason: str) -> None:
        """Oyun devam edemiyor (rakip kaçtı / stalemate) → bitir, kalan lider kazanır."""
        lobby.current_round = None
        lobby.pick = None
        connected = lobby.connected_players()
        if not connected:
            registry.remove(lobby.code)
            return
        winner = max(connected, key=lambda p: (p.score, -p.joined_at))
        lobby.phase = "GAME_OVER"
        lobby.winner_id = winner.player_id
        scores = {p.player_id: p.score for p in lobby.players.values()}
        await sio.emit("game_over", {
            "winner": {"player_id": winner.player_id, "nickname": winner.nickname},
            "final_scores": scores,
            "reason": reason,
        }, to=lobby.code)
        await _broadcast_state(lobby)

    async def _after_player_removed(lobby: Lobby) -> None:
        """Bir oyuncu (leave/kick/grace) silindikten sonra oyun durumunu toparla."""
        if lobby.phase not in ("PICKING", "IN_ROUND", "ROUND_RESULT"):
            return
        if len(lobby.connected_players()) < MIN_PLAYERS:
            await _end_game_abandoned(lobby, reason="opponent_left")
        elif lobby.phase == "PICKING":
            await _start_pick_phase(lobby)          # ghost picker'ı temizle, fazı yeniden kur
        elif lobby.phase == "IN_ROUND":
            await _maybe_end_round_if_all_answered(lobby)

    async def _disconnect_grace(code: str, player_id: str) -> None:
        await sio.sleep(DISCONNECT_GRACE_S)
        lobby = registry.get(code)
        if not lobby:
            return
        player = lobby.players.get(player_id)
        if not player or player.is_connected():
            return  # rejoin etti
        # Tamamen boş lobiyi SİLME: host kodu paylaşmak için telefonda uygulamadan
        # çıkmış olabilir; token ile geri dönebilsin. Gerçek terk → idle reaper (30 dk).
        if not lobby.connected_players():
            return
        lobby.remove_player(player_id)
        await sio.emit("player_left", {"player_id": player_id}, to=code)
        if not lobby.players:
            registry.remove(code)
            return
        await _broadcast_state(lobby)
        await _after_player_removed(lobby)

    # ---------- Events ----------

    @sio.on("connect")
    async def on_connect(sid: str, environ: dict, auth: Any = None) -> None:
        # Reaper'ı ilk bağlantıda (event-loop kesin çalışırken) başlat.
        if not reaper_state["started"]:
            reaper_state["started"] = True
            sio.start_background_task(_reaper_loop)

    @sio.on("create_lobby")
    async def on_create_lobby(sid: str, data: dict[str, Any]) -> None:
        if not event_limiter.allow(sid):
            await _emit_error(sid, "rate_limited", "Çok hızlı, biraz yavaşla")
            return
        if registry.count() >= MAX_LOBBIES:
            await _emit_error(sid, "server_busy", "Sunucu şu an dolu, sonra tekrar dene")
            return
        nickname = clean_nickname(data.get("nickname", ""))
        settings = validate_settings(data.get("settings") or {})

        lobby = registry.create(nickname)
        lobby.settings = settings
        host = lobby.players[lobby.host_id]
        host.sid = sid
        registry.bind_sid(sid, lobby.code, host.player_id)
        await sio.enter_room(sid, lobby.code)

        await sio.emit("lobby_created", {
            "lobby_code": lobby.code,
            "player_id": host.player_id,
            "player_token": host.token,
            "state": lobby.public_state(),
        }, to=sid)

    @sio.on("join_lobby")
    async def on_join_lobby(sid: str, data: dict[str, Any]) -> None:
        if not event_limiter.allow(sid):
            await _emit_error(sid, "rate_limited", "Çok hızlı, biraz yavaşla")
            return
        code = (data.get("lobby_code") or "").upper().strip()
        nickname = clean_nickname(data.get("nickname", ""))
        lobby = registry.get(code)
        if not lobby:
            await _emit_error(sid, "invalid_code", "Geçersiz lobi kodu")
            return
        if lobby.is_full():
            await _emit_error(sid, "lobby_full", "Lobi dolu")
            return
        if lobby.phase == "IN_ROUND":
            await _emit_error(sid, "in_game", "Oyun zaten başladı")
            return

        player = lobby.add_player(nickname)
        player.sid = sid
        registry.bind_sid(sid, lobby.code, player.player_id)
        await sio.enter_room(sid, lobby.code)

        await sio.emit("joined_lobby", {
            "lobby_code": lobby.code,
            "player_id": player.player_id,
            "player_token": player.token,
            "state": lobby.public_state(),
        }, to=sid)
        await sio.emit("player_joined", {"player": player.public_dict()}, to=lobby.code, skip_sid=sid)
        await _broadcast_state(lobby)

    @sio.on("rejoin")
    async def on_rejoin(sid: str, data: dict[str, Any]) -> None:
        code = (data.get("lobby_code") or "").upper().strip()
        token = data.get("player_token")
        lobby = registry.get(code)
        if not lobby or not token:
            await _emit_error(sid, "invalid_code", "Geçersiz lobi/token")
            return
        player = next((p for p in lobby.players.values() if p.token == token), None)
        if not player:
            await _emit_error(sid, "unknown_player", "Bu lobide bu oyuncu yok")
            return

        player.sid = sid
        player.disconnected_at = None
        registry.bind_sid(sid, lobby.code, player.player_id)
        await sio.enter_room(sid, lobby.code)

        await sio.emit("rejoined", {
            "lobby_code": lobby.code,
            "player_id": player.player_id,
            "state": lobby.public_state(),
        }, to=sid)
        await _broadcast_state(lobby)

    @sio.on("leave_lobby")
    async def on_leave_lobby(sid: str) -> None:
        info = registry.lookup_sid(sid)
        if not info:
            return
        lobby, pid = info
        await sio.leave_room(sid, lobby.code)
        registry.unbind_sid(sid)
        lobby.remove_player(pid)
        await sio.emit("player_left", {"player_id": pid}, to=lobby.code)
        if not lobby.players:
            registry.remove(lobby.code)
        else:
            await _broadcast_state(lobby)
            await _after_player_removed(lobby)

    @sio.on("update_settings")
    async def on_update_settings(sid: str, data: dict[str, Any]) -> None:
        info = registry.lookup_sid(sid)
        if not info:
            return
        lobby, pid = info
        if pid != lobby.host_id:
            await _emit_error(sid, "not_host", "Sadece host ayarları değiştirebilir")
            return
        if lobby.phase == "IN_ROUND":
            await _emit_error(sid, "in_game", "Tur sırasında değiştirilemez")
            return
        lobby.settings = validate_settings(data or {})
        await sio.emit("settings_updated", {"settings": lobby.settings}, to=lobby.code)

    @sio.on("start_game")
    async def on_start_game(sid: str) -> None:
        info = registry.lookup_sid(sid)
        if not info:
            return
        lobby, pid = info
        if pid != lobby.host_id:
            await _emit_error(sid, "not_host", "Sadece host başlatabilir")
            return
        if not lobby.can_start():
            await _emit_error(sid, "cannot_start", "Başlatılamaz (en az 2 oyuncu gerekli)")
            return
        for p in lobby.players.values():
            p.score = 0
        lobby.round_no = 0
        lobby.winner_id = None
        lobby.pick = None
        lobby.picker_cursor = 0
        lobby.scoreless_rounds = 0
        await _start_new_round(lobby)

    @sio.on("submit_answer")
    async def on_submit_answer(sid: str, data: dict[str, Any]) -> None:
        if not event_limiter.allow(sid):
            return
        info = registry.lookup_sid(sid)
        if not info:
            return
        lobby, pid = info
        player = lobby.players.get(pid)
        if not player:
            return

        # Metni daha doğrulamadan ÖNCE kes → sınırsız LIKE üreten sorgu engellenir.
        text = (data.get("text") or "").strip()[:ANSWER_TEXT_MAX]
        mode = lobby.settings["mode"]
        expected_round = data.get("round_no")

        # Skor/first-correct mantığı lobi başına serileşir (TOCTOU: çift puan olmaz).
        async with lobby.answer_lock:
            if lobby.phase != "IN_ROUND" or not lobby.current_round:
                return
            rnd = lobby.current_round
            if expected_round is not None and expected_round != rnd.round_no:
                return  # eski turdan geldi

            if mode == "duel":
                # İlk doğru bilen +1 alır ve tur anında biter; yanlışta tekrar denenir.
                if rnd.first_correct_player_id is not None or not text:
                    return
                matched = await query(lambda c: verify_free_answer(
                    c, text, rnd.club1["club_id"], rnd.club2["club_id"]))
                is_correct = matched is not None
                if is_correct:
                    rnd.first_correct_player_id = pid
                    # Bilinen oyuncuyu her iki ekranda göstermek için sakla (tur sonu reveal).
                    rnd.correct_player = await query(lambda c: get_player_public(c, matched))
                    player.score += 1
                    player.was_correct = True
                    player.answered_this_round = True
                    player.answer_text = text
                await sio.emit("answer_result", {
                    "round_no": rnd.round_no,
                    "correct": is_correct,
                    "delta_score": 1 if is_correct else 0,
                    "total_score": player.score,
                }, to=sid)
                if is_correct:
                    await sio.emit("player_answered", {"player_id": pid, "correct": True},
                                   to=lobby.code, skip_sid=sid)
                    await _end_round(lobby, reason="solved")
                return

            # ----- mc / free -----
            if player.answered_this_round:
                return

            is_correct = False
            if mode == "mc":
                try:
                    chosen_id = int(data.get("player_id"))
                except (TypeError, ValueError):
                    chosen_id = None
                is_correct = chosen_id == int(rnd.correct_player["player_id"])
            else:  # free
                player.answer_text = text or None
                if text:
                    matched_pid = await query(lambda c: verify_free_answer(
                        c, text, rnd.club1["club_id"], rnd.club2["club_id"],
                    ))
                    is_correct = matched_pid is not None

            delta = 0
            if is_correct:
                if rnd.first_correct_player_id is None:
                    rnd.first_correct_player_id = pid
                    delta = 3
                else:
                    delta = 1
                player.score += delta
                player.was_correct = True

            player.answered_this_round = True

            await sio.emit("answer_result", {
                "round_no": rnd.round_no,
                "correct": is_correct,
                "delta_score": delta,
                "total_score": player.score,
            }, to=sid)
            await sio.emit("player_answered", {
                "player_id": pid,
                "correct": is_correct,
            }, to=lobby.code, skip_sid=sid)

            await _maybe_end_round_if_all_answered(lobby)

    @sio.on("pick_club")
    async def on_pick_club(sid: str, data: dict[str, Any]) -> None:
        if not event_limiter.allow(sid):
            return
        info = registry.lookup_sid(sid)
        if not info:
            return
        lobby, pid = info
        if lobby.phase != "PICKING" or not lobby.pick:
            return
        pick = lobby.pick
        if pid == pick.picker_a:
            slot = "a"
        elif pid == pick.picker_b:
            slot = "b"
        else:
            return  # bu oyuncu seçici değil
        # İlk seçim kilitlenir (gizli + eşzamanlı: rakibe göre doğrulama yapılamaz).
        if (slot == "a" and pick.club_a) or (slot == "b" and pick.club_b):
            return
        try:
            club_id = int(data.get("club_id"))
        except (TypeError, ValueError):
            return

        club = await query(lambda c: c.execute(
            "SELECT club_id, name, logo_url FROM clubs WHERE club_id = ?", (club_id,),
        ).fetchone())
        if not club:
            return
        club_dict = {"club_id": club[0], "name": club[1], "logo_url": club[2]}

        if slot == "a":
            pick.club_a = club_dict
        else:
            pick.club_b = club_dict
        await sio.emit("pick_update", {"pick": pick.public_dict(lobby)}, to=lobby.code)
        # İki seçim de geldiyse turu kur (uyumsuz çift sunucuda düzeltilir).
        if pick.club_a and pick.club_b:
            await _finalize_pick(lobby)

    @sio.on("kick_player")
    async def on_kick_player(sid: str, data: dict[str, Any]) -> None:
        info = registry.lookup_sid(sid)
        if not info:
            return
        lobby, pid = info
        if pid != lobby.host_id:
            await _emit_error(sid, "not_host", "Sadece host çıkarabilir")
            return
        target = lobby.players.get(data.get("player_id") or "")
        if not target or target.player_id == lobby.host_id:
            return
        target_sid = target.sid
        lobby.remove_player(target.player_id)
        if target_sid:
            await sio.emit("kicked", {}, to=target_sid)
            await sio.leave_room(target_sid, lobby.code)
        await sio.emit("player_left", {"player_id": target.player_id}, to=lobby.code)
        await _broadcast_state(lobby)
        await _after_player_removed(lobby)

    @sio.on("request_rematch")
    async def on_request_rematch(sid: str) -> None:
        info = registry.lookup_sid(sid)
        if not info:
            return
        lobby, pid = info
        if pid != lobby.host_id:
            await _emit_error(sid, "not_host", "Sadece host rematch başlatabilir")
            return
        if lobby.phase != "GAME_OVER":
            return
        for p in lobby.players.values():
            p.score = 0
        lobby.round_no = 0
        lobby.winner_id = None
        lobby.recent_pairs.clear()
        lobby.pick = None
        lobby.picker_cursor = 0
        lobby.scoreless_rounds = 0
        await _start_new_round(lobby)

    @sio.on("disconnect")
    async def on_disconnect(sid: str) -> None:
        event_limiter.forget(sid)
        info = registry.unbind_sid(sid)
        if not info:
            return
        code, pid = info
        lobby = registry.get(code)
        if not lobby:
            return
        player = lobby.players.get(pid)
        if not player:
            return
        player.sid = None
        player.disconnected_at = time.time()
        await sio.emit("player_disconnected", {"player_id": pid}, to=code)

        # Aktif oyunda 2'nin altına düştüyse (1v1 rakip kaçtı / ikisi de gitti) bitir.
        # 0 bağlı kaldıysa _end_game_abandoned lobiyi temizler.
        if lobby.phase in ("PICKING", "IN_ROUND", "ROUND_RESULT") \
                and len(lobby.connected_players()) < MIN_PLAYERS:
            await _end_game_abandoned(lobby, reason="opponent_left")
            return
        # Seçim fazında aktif picker düştü ama yeterli oyuncu var → fazı yeniden kur.
        if lobby.phase == "PICKING" and lobby.pick \
                and pid in (lobby.pick.picker_a, lobby.pick.picker_b):
            await _start_pick_phase(lobby)
            return
        # Aksi halde (WAITING/GAME_OVER): grace ver. Lobi boş kalsa bile hemen silinmez;
        # host kod paylaşıp geri dönebilsin (mobil arka plan). _disconnect_grace boş
        # lobiyi yaşatır, idle reaper gerçek terkleri 30 dk sonra temizler.
        sio.start_background_task(_disconnect_grace, code, pid)
