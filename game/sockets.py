"""Flask-SocketIO event handler'ları.

app.py şu şekilde register eder:
    from flask_socketio import SocketIO
    from game.sockets import register_socket_handlers
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")
    register_socket_handlers(socketio, get_db)
"""
from __future__ import annotations

import time
from typing import Any, Callable

from flask import request
from flask_socketio import SocketIO, emit, join_room, leave_room

from .lobby import (
    DISCONNECT_GRACE_S,
    MAX_PLAYERS,
    ROUND_DURATION_S,
    ROUND_RESULT_DURATION_S,
    Lobby,
    Round,
    clean_nickname,
    validate_settings,
)
from .matchmaking import pick_club_pair
from .questions import build_question, verify_free_answer
from .store import registry


def register_socket_handlers(socketio: SocketIO, get_db: Callable[[], Any]) -> None:
    """Tüm Socket.IO event handler'larını register eder."""

    # ---------- Yardımcılar ----------

    def _broadcast_state(lobby: Lobby) -> None:
        socketio.emit("lobby_state", lobby.public_state(), to=lobby.code)

    def _emit_error(sid: str, code: str, message: str) -> None:
        emit("error", {"code": code, "message": message}, to=sid)

    def _start_new_round(lobby: Lobby) -> None:
        """Bir sonraki turu hazırla ve yayımla."""
        conn = get_db()
        try:
            # Uygun bir pair bul (question üretilemezse birkaç kere dene)
            for _ in range(8):
                pair = pick_club_pair(conn, lobby.settings["difficulty"], lobby.recent_pairs)
                if not pair:
                    break
                club_a, club_b = pair
                question = build_question(conn, club_a, club_b, lobby.settings["mode"])
                if question:
                    break
            else:
                pair = None
                question = None

            if not pair or not question:
                socketio.emit("error", {
                    "code": "no_question",
                    "message": "Bu zorluk için uygun soru bulunamadı",
                }, to=lobby.code)
                lobby.phase = "WAITING"
                _broadcast_state(lobby)
                return
        finally:
            conn.close()

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

        # İstemciye gönderirken doğru cevabı saklıyoruz (tur bitişinde açıklanır)
        payload: dict[str, Any] = {
            "round_no": round_obj.round_no,
            "club1": club_a,
            "club2": club_b,
            "mode": lobby.settings["mode"],
            "ends_at": round_obj.ends_at,
            "duration_s": ROUND_DURATION_S,
        }
        if round_obj.choices:
            # MC: seçenekleri gönder ama id'leri ifşa etme zorunluluğu yok; id lazım (tıklamada göndereceğiz)
            payload["choices"] = [
                {"player_id": c["player_id"], "name": c["name"], "image_url": c.get("image_url")}
                for c in round_obj.choices
            ]

        socketio.emit("round_start", payload, to=lobby.code)
        _broadcast_state(lobby)

        # Tur zamanlayıcısı: süre dolunca tur bitir
        socketio.start_background_task(_round_timer, lobby.code, round_obj.round_no)

    def _round_timer(code: str, round_no: int) -> None:
        """Süre dolarsa turu bitirir."""
        socketio.sleep(ROUND_DURATION_S + 0.2)
        lobby = registry.get(code)
        if not lobby or not lobby.current_round:
            return
        if lobby.current_round.round_no != round_no:
            return
        if lobby.phase != "IN_ROUND":
            return
        _end_round(lobby, reason="timeout")

    def _end_round(lobby: Lobby, reason: str) -> None:
        if not lobby.current_round:
            return
        lobby.phase = "ROUND_RESULT"
        rnd = lobby.current_round

        scores = {p.player_id: p.score for p in lobby.players.values()}
        correct_ids = [p.player_id for p in lobby.players.values() if p.was_correct]

        socketio.emit("round_end", {
            "round_no": rnd.round_no,
            "correct_answer": rnd.correct_player,
            "scores": scores,
            "correct_player_ids": correct_ids,
            "reason": reason,
        }, to=lobby.code)

        # Hedef puan kontrolü
        winner = lobby.reached_target()
        if winner:
            lobby.phase = "GAME_OVER"
            lobby.winner_id = winner.player_id
            socketio.emit("game_over", {
                "winner": {"player_id": winner.player_id, "nickname": winner.nickname},
                "final_scores": scores,
            }, to=lobby.code)
            lobby.current_round = None
            _broadcast_state(lobby)
            return

        # Aksi halde, kısa bir bekleme sonra yeni tur başlat
        socketio.start_background_task(_next_round_after_delay, lobby.code, rnd.round_no)

    def _next_round_after_delay(code: str, prev_round_no: int) -> None:
        socketio.sleep(ROUND_RESULT_DURATION_S)
        lobby = registry.get(code)
        if not lobby:
            return
        if lobby.phase != "ROUND_RESULT":
            return
        if lobby.current_round and lobby.current_round.round_no != prev_round_no:
            return
        _start_new_round(lobby)

    def _maybe_end_round_if_all_answered(lobby: Lobby) -> None:
        if lobby.phase != "IN_ROUND":
            return
        connected = lobby.connected_players()
        if not connected:
            return
        if all(p.answered_this_round for p in connected):
            _end_round(lobby, reason="all_answered")

    def _disconnect_grace(code: str, player_id: str) -> None:
        socketio.sleep(DISCONNECT_GRACE_S)
        lobby = registry.get(code)
        if not lobby:
            return
        player = lobby.players.get(player_id)
        if not player:
            return
        if player.is_connected():
            return  # rejoin etti
        lobby.remove_player(player_id)
        socketio.emit("player_left", {"player_id": player_id}, to=code)
        if not lobby.players:
            registry.remove(code)
            return
        _broadcast_state(lobby)
        if lobby.phase == "IN_ROUND":
            _maybe_end_round_if_all_answered(lobby)

    # ---------- Events ----------

    @socketio.on("create_lobby")
    def on_create_lobby(data: dict[str, Any]) -> None:
        nickname = clean_nickname(data.get("nickname", ""))
        settings = validate_settings(data.get("settings") or {})

        lobby = registry.create(nickname)
        lobby.settings = settings
        host = lobby.players[lobby.host_id]
        host.sid = request.sid
        registry.bind_sid(request.sid, lobby.code, host.player_id)
        join_room(lobby.code)

        emit("lobby_created", {
            "lobby_code": lobby.code,
            "player_id": host.player_id,
            "player_token": host.token,
            "state": lobby.public_state(),
        })

    @socketio.on("join_lobby")
    def on_join_lobby(data: dict[str, Any]) -> None:
        code = (data.get("lobby_code") or "").upper().strip()
        nickname = clean_nickname(data.get("nickname", ""))
        lobby = registry.get(code)
        if not lobby:
            _emit_error(request.sid, "invalid_code", "Geçersiz lobi kodu")
            return
        if lobby.is_full():
            _emit_error(request.sid, "lobby_full", "Lobi dolu")
            return
        if lobby.phase == "IN_ROUND":
            _emit_error(request.sid, "in_game", "Oyun zaten başladı")
            return

        player = lobby.add_player(nickname)
        player.sid = request.sid
        registry.bind_sid(request.sid, lobby.code, player.player_id)
        join_room(lobby.code)

        emit("joined_lobby", {
            "lobby_code": lobby.code,
            "player_id": player.player_id,
            "player_token": player.token,
            "state": lobby.public_state(),
        })
        socketio.emit("player_joined", {"player": player.public_dict()}, to=lobby.code, include_self=False)
        _broadcast_state(lobby)

    @socketio.on("rejoin")
    def on_rejoin(data: dict[str, Any]) -> None:
        code = (data.get("lobby_code") or "").upper().strip()
        token = data.get("player_token")
        lobby = registry.get(code)
        if not lobby or not token:
            _emit_error(request.sid, "invalid_code", "Geçersiz lobi/token")
            return
        player = next((p for p in lobby.players.values() if p.token == token), None)
        if not player:
            _emit_error(request.sid, "unknown_player", "Bu lobide bu oyuncu yok")
            return

        player.sid = request.sid
        player.disconnected_at = None
        registry.bind_sid(request.sid, lobby.code, player.player_id)
        join_room(lobby.code)

        emit("rejoined", {
            "lobby_code": lobby.code,
            "player_id": player.player_id,
            "state": lobby.public_state(),
        })
        _broadcast_state(lobby)

    @socketio.on("leave_lobby")
    def on_leave_lobby() -> None:
        info = registry.lookup_sid(request.sid)
        if not info:
            return
        lobby, pid = info
        leave_room(lobby.code)
        registry.unbind_sid(request.sid)
        lobby.remove_player(pid)
        socketio.emit("player_left", {"player_id": pid}, to=lobby.code)
        if not lobby.players:
            registry.remove(lobby.code)
        else:
            _broadcast_state(lobby)

    @socketio.on("update_settings")
    def on_update_settings(data: dict[str, Any]) -> None:
        info = registry.lookup_sid(request.sid)
        if not info:
            return
        lobby, pid = info
        if pid != lobby.host_id:
            _emit_error(request.sid, "not_host", "Sadece host ayarları değiştirebilir")
            return
        if lobby.phase == "IN_ROUND":
            _emit_error(request.sid, "in_game", "Tur sırasında değiştirilemez")
            return
        lobby.settings = validate_settings(data or {})
        socketio.emit("settings_updated", {"settings": lobby.settings}, to=lobby.code)

    @socketio.on("start_game")
    def on_start_game() -> None:
        info = registry.lookup_sid(request.sid)
        if not info:
            return
        lobby, pid = info
        if pid != lobby.host_id:
            _emit_error(request.sid, "not_host", "Sadece host başlatabilir")
            return
        if not lobby.can_start():
            _emit_error(request.sid, "cannot_start", "Başlatılamaz (en az 2 oyuncu gerekli)")
            return
        # Skorları sıfırla (yeni oyun / rematch)
        for p in lobby.players.values():
            p.score = 0
        lobby.round_no = 0
        lobby.winner_id = None
        _start_new_round(lobby)

    @socketio.on("submit_answer")
    def on_submit_answer(data: dict[str, Any]) -> None:
        info = registry.lookup_sid(request.sid)
        if not info:
            return
        lobby, pid = info
        player = lobby.players.get(pid)
        if not player:
            return
        if lobby.phase != "IN_ROUND" or not lobby.current_round:
            return
        if player.answered_this_round:
            return

        rnd = lobby.current_round
        expected_round = data.get("round_no")
        if expected_round is not None and expected_round != rnd.round_no:
            return  # eski turdan geldi

        is_correct = False
        if lobby.settings["mode"] == "mc":
            try:
                chosen_id = int(data.get("player_id"))
            except (TypeError, ValueError):
                chosen_id = None
            is_correct = chosen_id == int(rnd.correct_player["player_id"])
        else:  # free
            text = (data.get("text") or "").strip()
            if text:
                conn = get_db()
                try:
                    matched_pid = verify_free_answer(
                        conn, text,
                        rnd.club1["club_id"], rnd.club2["club_id"],
                    )
                finally:
                    conn.close()
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

        emit("answer_result", {
            "round_no": rnd.round_no,
            "correct": is_correct,
            "delta_score": delta,
            "total_score": player.score,
        })
        socketio.emit("player_answered", {
            "player_id": pid,
            "correct": is_correct,
        }, to=lobby.code, include_self=False)

        _maybe_end_round_if_all_answered(lobby)

    @socketio.on("kick_player")
    def on_kick_player(data: dict[str, Any]) -> None:
        info = registry.lookup_sid(request.sid)
        if not info:
            return
        lobby, pid = info
        if pid != lobby.host_id:
            _emit_error(request.sid, "not_host", "Sadece host çıkarabilir")
            return
        target_id = data.get("player_id")
        target = lobby.players.get(target_id or "")
        if not target or target.player_id == lobby.host_id:
            return
        target_sid = target.sid
        lobby.remove_player(target.player_id)
        if target_sid:
            socketio.emit("kicked", {}, to=target_sid)
            try:
                leave_room(lobby.code, sid=target_sid)
            except Exception:
                pass
        socketio.emit("player_left", {"player_id": target.player_id}, to=lobby.code)
        _broadcast_state(lobby)

    @socketio.on("request_rematch")
    def on_request_rematch() -> None:
        info = registry.lookup_sid(request.sid)
        if not info:
            return
        lobby, pid = info
        if pid != lobby.host_id:
            _emit_error(request.sid, "not_host", "Sadece host rematch başlatabilir")
            return
        if lobby.phase != "GAME_OVER":
            return
        for p in lobby.players.values():
            p.score = 0
        lobby.round_no = 0
        lobby.winner_id = None
        lobby.recent_pairs.clear()
        _start_new_round(lobby)

    @socketio.on("disconnect")
    def on_disconnect() -> None:
        info = registry.unbind_sid(request.sid)
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
        socketio.emit("player_disconnected", {"player_id": pid}, to=code)

        # Eğer hiç bağlı oyuncu kalmadıysa lobi'yi hemen kapat
        # (oyun WAITING/GAME_OVER'daysa reconnect bekleme anlamsız)
        if not lobby.connected_players():
            registry.remove(code)
            return

        # Aksi halde grace period sonrası bu oyuncuyu kaldır
        socketio.start_background_task(_disconnect_grace, code, pid)
