"""Sağlık kontrolü (load balancer / cold-start ısıtma)."""
from __future__ import annotations

from fastapi import APIRouter

from ..db import query

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> dict:
    build_id = await query(
        lambda conn: conn.execute(
            "SELECT value FROM build_metadata WHERE key = 'build_id'"
        ).fetchone()[0]
    )
    return {"ok": True, "build_id": build_id}
