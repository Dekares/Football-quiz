"""Hafif, Redis'siz token-bucket rate limiter (per-IP / per-sid).

Tek process / tek event-loop için yeterli. Anahtar başına kova tutar; her
erişimde refill eder. Bellek sızmasın diye anahtar sayısı tavanlı ve eskiyenler
(kovası dolmuş = uzun süredir görülmemiş) periyodik atılır.
"""
from __future__ import annotations

import time


class RateLimiter:
    def __init__(self, rate_per_sec: float, burst: int, max_keys: int = 50_000) -> None:
        self.rate = rate_per_sec
        self.burst = float(burst)
        self.max_keys = max_keys
        self._buckets: dict[str, list[float]] = {}   # key -> [tokens, last_ts]

    def allow(self, key: str, cost: float = 1.0) -> bool:
        now = time.monotonic()
        b = self._buckets.get(key)
        if b is None:
            if len(self._buckets) >= self.max_keys:
                self._prune(now)
            self._buckets[key] = [self.burst - cost, now]
            return True
        # refill
        b[0] = min(self.burst, b[0] + (now - b[1]) * self.rate)
        b[1] = now
        if b[0] >= cost:
            b[0] -= cost
            return True
        return False

    def forget(self, key: str) -> None:
        self._buckets.pop(key, None)

    def _prune(self, now: float) -> None:
        full_after = self.burst / self.rate if self.rate else 0
        for k in [k for k, v in self._buckets.items() if now - v[1] > full_after]:
            del self._buckets[k]
        # Hâlâ tavandaysa en eski %10'u sertçe at.
        if len(self._buckets) >= self.max_keys:
            oldest = sorted(self._buckets, key=lambda k: self._buckets[k][1])
            for k in oldest[: max(1, self.max_keys // 10)]:
                del self._buckets[k]
