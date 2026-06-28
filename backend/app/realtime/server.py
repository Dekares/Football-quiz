"""Realtime (socket.io) servisi — asyncio, tek node, Redis yok.

Entrypoint: `backend.app.realtime.server:app`

Tek bir AsyncServer + in-memory lobi state. FastAPI API uygulamasını sarmalar;
böylece bu entrypoint hem geliştirmede (her şey tek process) hem de ayrı bir
realtime servisinde (LB /socket.io/* trafiğini buraya yönlendirir) kullanılır.

Çok-node'a çıkmak gerekirse: LB'de lobi koduna göre consistent-hash routing →
her node kendi lobilerini in-memory sahiplenir, mesaj kuyruğu (Redis) gerekmez.
"""
from __future__ import annotations

import socketio

from ..config import settings
from ..main import create_app
from .handlers import register_handlers

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=settings.cors_origins if settings.cors_origins != ["*"] else "*",
)
register_handlers(sio)

# socket.io /socket.io/* yolunu yakalar; geri kalan her şey FastAPI API'sine gider.
app = socketio.ASGIApp(sio, other_asgi_app=create_app())
