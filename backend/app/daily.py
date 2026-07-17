"""Shared rules for the daily football challenge."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


DAILY_START_DATE = date(2026, 7, 1)
DAILY_TIMEZONE = timezone(timedelta(hours=3))
DAILY_SELECTION_VERSION = "global-known-v1"


def daily_today() -> date:
    return datetime.now(DAILY_TIMEZONE).date()


def daily_number(challenge_date: date) -> int:
    return (challenge_date - DAILY_START_DATE).days + 1
