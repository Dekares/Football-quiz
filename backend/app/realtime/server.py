"""Realtime (socket.io) servisi — asyncio, tek node, Redis yok.

Entrypoint: `backend.app.realtime.server:app`

Tek bir AsyncServer + in-memory lobi state. FastAPI API uygulamasını sarmalar;
böylece bu entrypoint hem geliştirmede (her şey tek process) hem de ayrı bir
realtime servisinde (LB /socket.io/* trafiğini buraya yönlendirir) kullanılır.

Çok-node'a çıkmak gerekirse paylaşımlı Socket.IO manager ve lobi state'i
gerekir. Mevcut in-memory yapı tek realtime process için tasarlanmıştır.
"""
from __future__ import annotations

import socketio

from ..config import settings
from ..main import create_app
from .handlers import register_handlers

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=settings.cors_origins or None,
)
register_handlers(sio)

# socket.io /socket.io/* yolunu yakalar; geri kalan her şey FastAPI API'sine gider.
app = socketio.ASGIApp(sio, other_asgi_app=create_app())
