"""FastAPI uygulaması — stateless HTTP API (yatay ölçeklenen `api` servisi).

Entrypoint: `backend.app.main:app`
Realtime (socket.io) ayrı servistir; bkz. backend/app/realtime/server.py.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from .api import classic, health, quiz, search
from .config import settings
from .ratelimit import RateLimiter

# Per-IP HTTP hız limiti. Asıl pahalı yol arama autocomplete'i (LIKE tarama);
# insan kullanımı için bol, tarayıcı/abuse için dar.
_api_limiter = RateLimiter(rate_per_sec=15, burst=30)


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RevalidateStaticFiles(StaticFiles):
    """Statikleri her zaman doğrulatır (ETag/Last-Modified ile 304).

    İçerik-hash'li URL kullanmadığımız için ``no-cache`` ile tarayıcının her
    yüklemede yeniden doğrulamasını sağlıyoruz → deploy sonrası bayat JS/CSS
    sorunu olmaz; değişmeyen dosyalar yine 304 döner (ucuz). Production'da
    statikler CDN'e taşınınca bu yol kullanılmaz (APP_SERVE_STATIC=false).
    """

    def file_response(self, *args, **kwargs) -> Response:
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "no-cache"
        return resp


def create_app() -> FastAPI:
    app = FastAPI(
        title="Futbol Quiz API",
        docs_url="/api/docs" if settings.enable_docs else None,
        openapi_url="/api/openapi.json" if settings.enable_docs else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _rate_limit(request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/") and path != "/api/health":
            if not _api_limiter.allow(_client_ip(request)):
                return JSONResponse({"detail": "rate_limited"}, status_code=429)
        return await call_next(request)

    for module in (health, search, quiz, classic):
        app.include_router(module.router)

    if settings.serve_static:
        static_dir = settings.static_dir
        app.mount("/static", RevalidateStaticFiles(directory=static_dir), name="static")

        @app.get("/", include_in_schema=False)
        async def index() -> FileResponse:
            # index.html asla cache'lenmemeli; aksi halde yeni asset'ler görünmez.
            return FileResponse(
                static_dir / "index.html",
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )

    return app


app = create_app()
