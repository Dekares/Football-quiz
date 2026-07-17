# Coolify tek-servis deploy — render.yaml'ın birebir Docker karşılığı.
# API + statik + socket.io aynı process'ten (backend.app.realtime.server:app).
# In-memory lobi state → TEK worker. Coolify/Traefik domain+TLS+websocket'i sağlar.
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 APP_SERVE_STATIC=true

COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY backend/ backend/
COPY data/football_quiz_v2.db data/football_quiz_v2.db
COPY frontend/ frontend/

EXPOSE 8000
# ponytail: $PORT verilirse onurlandır (Coolify port override), yoksa 8000.
CMD ["sh", "-c", "uvicorn backend.app.realtime.server:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
