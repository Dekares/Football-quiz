"""Salt-okunur SQLite erişimi.

SQLite çağrıları bloklayıcıdır; event loop'u tıkamamak için sabit bir thread
havuzunda çalıştırılır. Her worker thread'i kendi salt-okunur bağlantısını
(immutable=1) tembel açar — açılış maliyeti thread başına bir kez ödenir.

immutable=1: dosyanın çalışma anında değişmediğini SQLite'a garanti eder →
kilitleme yok, agresif sayfa cache. DB build/prune offline yapılır.
"""
from __future__ import annotations

import asyncio
import sqlite3
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

from .config import settings
from .text import normalize_text

T = TypeVar("T")

_executor = ThreadPoolExecutor(max_workers=settings.db_pool_size, thread_name_prefix="sqlite")
_local = threading.local()


def _open_connection() -> sqlite3.Connection:
    uri = f"file:{settings.db_path.as_posix()}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.create_function("normalize", 1, normalize_text, deterministic=True)
    conn.execute("PRAGMA query_only = ON")
    conn.execute("PRAGMA mmap_size = 268435456")   # 256MB
    conn.execute("PRAGMA cache_size = -32000")      # 32MB
    conn.execute("PRAGMA temp_store = MEMORY")
    return conn


def _connection() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = _open_connection()
        _local.conn = conn
    return conn


async def query(fn: Callable[[sqlite3.Connection], T]) -> T:
    """`fn(conn)`'i havuzda çalıştırır ve sonucunu döndürür."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, lambda: fn(_connection()))
