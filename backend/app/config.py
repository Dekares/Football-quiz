"""Uygulama ayarları (ortam değişkenleriyle override edilebilir).

Önek: APP_  (örn. APP_DB_PATH, APP_CORS_ORIGINS, APP_SERVE_STATIC).
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> repo kökü: parents[2]
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", extra="ignore")

    # Salt-okunur quiz veritabanı (her instance ile paketlenir).
    db_path: Path = REPO_ROOT / "data" / "football_quiz_v2.db"
    # Eşzamanlı SQLite okuması için thread havuzu boyutu.
    db_pool_size: int = 8

    # Boş liste aynı-origin anlamına gelir. Ayrı bir frontend origin'i
    # kullanılacaksa APP_CORS_ORIGINS ile açıkça izin verilmelidir.
    cors_origins: list[str] = []

    # Host header enjeksiyonunu engeller. Özel domain prod ortamında
    # APP_TRUSTED_HOSTS='["example.com"]' ile eklenmelidir.
    trusted_hosts: list[str] = [
        "localhost",
        "127.0.0.1",
        "testserver",
        "*.onrender.com",
    ]

    # Statikleri Python'dan servis et (dev: True, prod: CDN/nginx → False).
    serve_static: bool = True
    static_dir: Path = REPO_ROOT / "frontend" / "static"

    # Canonical/OG/sitemap mutlak URL'lerinin tabanı (örn. https://futbolquiz.com).
    # Boşsa TrustedHostMiddleware tarafından doğrulanmış istek URL'sinden
    # türetilir. Proxy başlıklarını yalnızca ASGI sunucusu, güvenilen proxy
    # adreslerinden geldiğinde işlemelidir.
    public_base_url: str = ""

    # HTTPS yanıtlarında HSTS yayınla. Yerel HTTP geliştirmesini etkilemez.
    enable_hsts: bool = True

    # OpenAPI/Swagger (/api/docs) — güvenli varsayılan kapalı; dev'de APP_ENABLE_DOCS=true.
    enable_docs: bool = False


settings = Settings()
