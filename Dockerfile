# Coolify tek-servis deploy — render.yaml'ın birebir Docker karşılığı.
# API + statik + socket.io aynı process'ten (backend.app.realtime.server:app).
# In-memory lobi state → TEK worker. Coolify/Traefik domain+TLS+websocket'i sağlar.
FROM python:3.11-slim-bookworm

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 APP_SERVE_STATIC=true

COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY backend/ backend/
COPY data/football_quiz_v2.db data/football_quiz_v2.db
COPY frontend/ frontend/

RUN groupadd --system careerdle && useradd --system --gid careerdle --home /app careerdle \
    && chown -R careerdle:careerdle /app

USER careerdle
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"
# ponytail: $PORT verilirse onurlandır (Coolify port override), yoksa 8000.
CMD ["sh", "-c", "uvicorn backend.app.realtime.server:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
