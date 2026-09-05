"""Quality gates for canonical and published databases."""
from __future__ import annotations

import sqlite3
from typing import Any

from backend.app.daily import DAILY_START_DATE, daily_today

from .database import queue_counts
from .daily import DAILY_KNOWN_POOL_SIZE, RECENT_PLAYER_WINDOW


def validate_source(conn: sqlite3.Connection) -> dict[str, Any]:
    scalar = lambda sql, params=(): int(conn.execute(sql, params).fetchone()[0])
    counts = {
        "competitions": scalar("SELECT COUNT(*) FROM competitions"),
        "clubs": scalar("SELECT COUNT(*) FROM clubs"),
        "players": scalar("SELECT COUNT(*) FROM players"),
        "profiled_players": scalar("SELECT COUNT(*) FROM players WHERE profile_loaded = 1"),
        "transfers": scalar("SELECT COUNT(*) FROM transfers"),
        "market_values": scalar("SELECT COUNT(*) FROM player_market_values"),
        "periods": scalar("SELECT COUNT(*) FROM player_club_periods"),
        "daily_challenges": scalar("SELECT COUNT(*) FROM daily_challenges"),
        "snapshots": scalar("SELECT COUNT(*) FROM api_snapshots"),
        "dead_jobs": scalar("SELECT COUNT(*) FROM crawl_jobs WHERE status = 'dead'"),
        "open_errors": scalar(
            "SELECT COUNT(*) FROM data_issues WHERE severity = 'error' AND resolved_at IS NULL"
        ),
    }
    fk_violations = len(conn.execute("PRAGMA foreign_key_check").fetchall())
    inverted_periods = scalar(
        """
        SELECT COUNT(*) FROM player_club_periods
        WHERE date_from IS NOT NULL AND date_to IS NOT NULL AND date_from > date_to
        """
    )
    transfer_missing_club = scalar(
        """
        SELECT COUNT(*) FROM transfers
        WHERE from_club_id IS NULL AND to_club_id IS NULL
        """
    )
    invalid_daily_numbers = scalar(
        """
        SELECT COUNT(*) FROM daily_challenges
        WHERE day_number != CAST(
            julianday(challenge_date) - julianday(?) AS INTEGER
        ) + 1
        """,
        (DAILY_START_DATE.isoformat(),),
    )
    players_with_multiple_open_periods = scalar(
        """
        SELECT COUNT(*) FROM (
            SELECT pcp.player_id
            FROM player_club_periods pcp
            JOIN clubs c ON c.club_id = pcp.club_id
            WHERE pcp.date_to IS NULL AND c.is_placeholder = 0
            GROUP BY pcp.player_id
            HAVING COUNT(*) > 1
        )
        """
    )
    warnings: list[str] = []
    errors: list[str] = []
    if fk_violations:
        errors.append(f"foreign_key_violations={fk_violations}")
    if inverted_periods:
        errors.append(f"inverted_periods={inverted_periods}")
    if counts["open_errors"]:
        errors.append(f"open_data_errors={counts['open_errors']}")
    if players_with_multiple_open_periods:
        errors.append(
            f"players_with_multiple_open_periods={players_with_multiple_open_periods}"
        )
    if invalid_daily_numbers:
        errors.append(f"invalid_daily_challenge_numbers={invalid_daily_numbers}")
    if transfer_missing_club:
        warnings.append(f"transfers_without_any_club={transfer_missing_club}")
    if counts["dead_jobs"]:
        warnings.append(f"dead_jobs={counts['dead_jobs']}")
    stub_players = counts["players"] - counts["profiled_players"]
    if stub_players:
        warnings.append(f"players_waiting_for_profile={stub_players}")
    return {
        "ok": not errors,
        "counts": counts,
        "queue": queue_counts(conn),
        "errors": errors,
        "warnings": warnings,
    }


def validate_game_db(
    conn: sqlite3.Connection,
    min_players: int = 1,
    min_periods: int = 1,
    strict: bool = True,
) -> dict[str, Any]:
    scalar = lambda sql, params=(): int(conn.execute(sql, params).fetchone()[0])
    counts = {
        "players": scalar("SELECT COUNT(*) FROM players"),
        "clubs": scalar("SELECT COUNT(*) FROM clubs"),
        "periods": scalar("SELECT COUNT(*) FROM player_clubs"),
        "pairs": scalar("SELECT COUNT(*) FROM club_pair_stats"),
        "pair_easy": scalar(
            "SELECT COUNT(*) FROM club_pair_stats WHERE min_prestige >= 20 AND common_count >= 5"
        ),
        "pair_medium": scalar(
            "SELECT COUNT(*) FROM club_pair_stats "
            "WHERE min_prestige BETWEEN 8 AND 25 AND common_count BETWEEN 3 AND 8"
        ),
        "pair_hard": scalar(
            "SELECT COUNT(*) FROM club_pair_stats "
            "WHERE min_prestige BETWEEN 3 AND 10 AND common_count BETWEEN 2 AND 4"
        ),
        "pool_easy": scalar("SELECT COUNT(*) FROM quiz_pool WHERE difficulty = 'easy'"),
        "pool_medium": scalar("SELECT COUNT(*) FROM quiz_pool WHERE difficulty = 'medium'"),
        "pool_hard": scalar("SELECT COUNT(*) FROM quiz_pool WHERE difficulty = 'hard'"),
        "pool_known": scalar("SELECT COUNT(*) FROM quiz_pool WHERE recognition = 'known'"),
        "pool_less_known": scalar(
            "SELECT COUNT(*) FROM quiz_pool WHERE recognition = 'less_known'"
        ),
        "pool_obscure": scalar("SELECT COUNT(*) FROM quiz_pool WHERE recognition = 'obscure'"),
        "global_pool_known": scalar(
            "SELECT COUNT(*) FROM global_quiz_pool WHERE recognition = 'known'"
        ),
        "global_pool_less_known": scalar(
            "SELECT COUNT(*) FROM global_quiz_pool WHERE recognition = 'less_known'"
        ),
        "global_pool_obscure": scalar(
            "SELECT COUNT(*) FROM global_quiz_pool WHERE recognition = 'obscure'"
        ),
        "daily_challenges": scalar("SELECT COUNT(*) FROM daily_challenges"),
        "competitions": scalar("SELECT COUNT(*) FROM competitions"),
        "active_stars": scalar(
            "SELECT COUNT(*) FROM players WHERE career_status = 'active_star'"
        ),
        "active_legends": scalar(
            "SELECT COUNT(*) FROM players WHERE career_status = 'active_legend'"
        ),
        "retired_legends": scalar(
            "SELECT COUNT(*) FROM players WHERE career_status = 'retired_legend'"
        ),
        "world_xi_legends": scalar("SELECT COUNT(*) FROM world_xi_legend_pool"),
    }
    errors: list[str] = []
    warnings: list[str] = []
    fk_violations = len(conn.execute("PRAGMA foreign_key_check").fetchall())
    if fk_violations:
        errors.append(f"foreign_key_violations={fk_violations}")
    if counts["players"] < min_players:
        errors.append(f"players={counts['players']} < min_players={min_players}")
    if counts["periods"] < min_periods:
        errors.append(f"periods={counts['periods']} < min_periods={min_periods}")
    if counts["daily_challenges"] == 0:
        errors.append("daily_challenges=0")
    for key in (
        "active_stars", "active_legends", "retired_legends", "world_xi_legends"
    ):
        if counts[key] == 0:
            message = f"{key}=0"
            (errors if strict else warnings).append(message)
    for key in (
        "pool_known", "pool_less_known", "pool_obscure",
        "global_pool_known", "global_pool_less_known", "global_pool_obscure",
        "pair_easy", "pair_medium", "pair_hard",
    ):
        if counts[key] == 0:
            message = f"{key}=0"
            (errors if strict else warnings).append(message)
    orphan_players = scalar(
        """
        SELECT COUNT(*) FROM player_clubs pc
        LEFT JOIN players p ON p.player_id = pc.player_id
        WHERE p.player_id IS NULL
        """
    )
    orphan_clubs = scalar(
        """
        SELECT COUNT(*) FROM player_clubs pc
        LEFT JOIN clubs c ON c.club_id = pc.club_id
        WHERE c.club_id IS NULL
        """
    )
    if orphan_players:
        errors.append(f"orphan_player_periods={orphan_players}")
    if orphan_clubs:
        errors.append(f"orphan_club_periods={orphan_clubs}")
    players_with_multiple_open_periods = scalar(
        """
        SELECT COUNT(*) FROM (
            SELECT pc.player_id
            FROM player_clubs pc
            JOIN clubs c ON c.club_id = pc.club_id
            WHERE pc.date_to IS NULL
              AND c.name NOT IN ('Retired', 'Without Club', 'Career break')
            GROUP BY pc.player_id
            HAVING COUNT(*) > 1
        )
        """
    )
    if players_with_multiple_open_periods:
        errors.append(
            f"players_with_multiple_open_periods={players_with_multiple_open_periods}"
        )
    invalid_pair_types = scalar(
        """
        SELECT COUNT(*) FROM club_pair_stats
        WHERE typeof(common_count) != 'integer' OR typeof(min_prestige) != 'integer'
        """
    )
    if invalid_pair_types:
        errors.append(f"invalid_pair_value_types={invalid_pair_types}")
    overlapping_pool_players = scalar(
        """
        SELECT COUNT(*) FROM (
            SELECT competition_id, player_id
            FROM quiz_pool
            GROUP BY competition_id, player_id
            HAVING COUNT(DISTINCT recognition) != 1
        )
        """
    )
    if overlapping_pool_players:
        errors.append(f"overlapping_quiz_pool_players={overlapping_pool_players}")
    overlapping_global_pool_players = scalar(
        """
        SELECT COUNT(*) FROM (
            SELECT player_id
            FROM global_quiz_pool
            GROUP BY player_id
            HAVING COUNT(DISTINCT recognition) != 1
        )
        """
    )
    if overlapping_global_pool_players:
        errors.append(
            f"overlapping_global_pool_players={overlapping_global_pool_players}"
        )
    missing_global_pool_players = scalar(
        """
        SELECT COUNT(*) FROM (
            SELECT DISTINCT player_id
            FROM quiz_pool
            WHERE competition_id != 'LEGENDS'
            EXCEPT
            SELECT player_id FROM global_quiz_pool
        )
        """
    )
    if missing_global_pool_players:
        errors.append(f"missing_global_pool_players={missing_global_pool_players}")
    invalid_retired_legend_status = scalar(
        """
        SELECT COUNT(*)
        FROM quiz_pool q JOIN players p ON p.player_id = q.player_id
        WHERE q.competition_id = 'LEGENDS'
          AND p.career_status != 'retired_legend'
        """
    )
    if invalid_retired_legend_status:
        errors.append(
            f"invalid_retired_legend_status={invalid_retired_legend_status}"
        )
    retired_in_active_pool = scalar(
        """
        SELECT COUNT(*)
        FROM global_quiz_pool g JOIN players p ON p.player_id = g.player_id
        WHERE p.career_status = 'retired_legend'
        """
    )
    if retired_in_active_pool:
        errors.append(f"retired_legends_in_active_pool={retired_in_active_pool}")
    invalid_world_xi_legends = scalar(
        """
        SELECT COUNT(*)
        FROM world_xi_legend_pool w JOIN players p ON p.player_id = w.player_id
        WHERE p.career_status != 'retired_legend'
        """
    )
    if invalid_world_xi_legends:
        errors.append(f"invalid_world_xi_legends={invalid_world_xi_legends}")
    invalid_daily_numbers = scalar(
        """
        SELECT COUNT(*) FROM daily_challenges
        WHERE day_number != CAST(
            julianday(challenge_date) - julianday(?) AS INTEGER
        ) + 1
        """,
        (DAILY_START_DATE.isoformat(),),
    )
    if invalid_daily_numbers:
        errors.append(f"invalid_daily_challenge_numbers={invalid_daily_numbers}")
    first_daily = conn.execute(
        """
        SELECT challenge_date, day_number
        FROM daily_challenges
        ORDER BY challenge_date
        LIMIT 1
        """
    ).fetchone()
    if (
        first_daily is None
        or first_daily["challenge_date"] != DAILY_START_DATE.isoformat()
        or int(first_daily["day_number"]) != 1
    ):
        errors.append("invalid_daily_challenge_start")
    today = daily_today()
    required_end = today.isoformat()
    invalid_future_daily = scalar(
        """
        SELECT COUNT(*)
        FROM daily_challenges d
        LEFT JOIN global_quiz_pool g
          ON g.player_id = d.player_id
         AND g.recognition = 'known'
         AND g.rank_global <= ?
        WHERE d.challenge_date > ? AND g.player_id IS NULL
        """,
        (DAILY_KNOWN_POOL_SIZE, required_end),
    )
    if invalid_future_daily:
        errors.append(f"invalid_future_daily={invalid_future_daily}")
    repeated_future_daily = scalar(
        """
        SELECT COUNT(*)
        FROM daily_challenges earlier
        JOIN daily_challenges later
          ON later.player_id = earlier.player_id
         AND later.challenge_date > earlier.challenge_date
         AND later.challenge_date <= date(earlier.challenge_date, ?)
        WHERE later.challenge_date > ?
        """,
        (f"+{RECENT_PLAYER_WINDOW} days", required_end),
    )
    if repeated_future_daily:
        message = f"repeated_future_daily={repeated_future_daily}"
        (errors if strict else warnings).append(message)
    future_end = f"+30 days"
    scheduled_next_30 = scalar(
        """
        SELECT COUNT(*) FROM daily_challenges
        WHERE challenge_date BETWEEN ? AND date(?, ?)
        """,
        (required_end, required_end, future_end),
    )
    if scheduled_next_30 != 31:
        errors.append(f"daily_challenge_30_day_coverage={scheduled_next_30}")
    empty_competition_buckets = scalar(
        """
        SELECT COUNT(*) FROM competitions c
        CROSS JOIN (
            SELECT 'known' recognition
            UNION ALL SELECT 'less_known'
            UNION ALL SELECT 'obscure'
        ) r
        WHERE c.is_special = 0 AND NOT EXISTS (
            SELECT 1 FROM quiz_pool q
            WHERE q.competition_id = c.competition_id
              AND q.recognition = r.recognition
        )
        """
    )
    if empty_competition_buckets:
        message = f"empty_competition_buckets={empty_competition_buckets}"
        (errors if strict else warnings).append(message)
    return {"ok": not errors, "counts": counts, "errors": errors, "warnings": warnings}
