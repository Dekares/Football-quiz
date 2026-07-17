"""Command line entrypoint for the Transfermarkt data pipeline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .client import ApiClient
from .database import initialize, queue_counts
from .derive import derive_all_periods
from .ingest import run_worker, seed_competition_seasons, seed_players
from .major import DEFAULT_CONFIG, update_major_leagues
from .maintenance import repair_snapshots, sync_legends
from .publish import publish_game_db
from .validation import validate_source

DEFAULT_SOURCE = Path("data/transfermarkt_source.db")
DEFAULT_OUTPUT = Path("data/football_quiz_v2.db")


def _csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Transfermarkt API to Careerdle database pipeline")
    parser.add_argument("--db", type=Path, default=DEFAULT_SOURCE, help="canonical source database")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create or migrate the canonical database")

    seed = sub.add_parser("seed", help="enqueue competition/season discovery jobs")
    seed.add_argument("--competitions", required=True, help="comma-separated IDs, e.g. GB1,ES1")
    seed.add_argument("--seasons", required=True, help="comma-separated season IDs, e.g. 2025,2024")
    seed.add_argument("--refresh", action="store_true", help="requeue completed matching jobs")

    seed_player = sub.add_parser("seed-player", help="enqueue direct player enrichment jobs")
    seed_player.add_argument("--players", required=True, help="comma-separated Transfermarkt IDs")
    seed_player.add_argument("--refresh", action="store_true")

    work = sub.add_parser("work", help="process queued API jobs")
    work.add_argument("--base-url", default="http://localhost:8000")
    work.add_argument("--limit", type=int, default=None)
    work.add_argument("--concurrency", type=int, default=2)
    work.add_argument("--timeout", type=float, default=30.0)
    work.add_argument("--retries", type=int, default=2)

    crawl = sub.add_parser("crawl", help="seed and process jobs in one command")
    crawl.add_argument("--competitions", required=True)
    crawl.add_argument("--seasons", required=True)
    crawl.add_argument("--refresh", action="store_true")
    crawl.add_argument("--base-url", default="http://localhost:8000")
    crawl.add_argument("--limit", type=int, default=None)
    crawl.add_argument("--concurrency", type=int, default=2)
    crawl.add_argument("--timeout", type=float, default=30.0)

    sub.add_parser("derive", help="derive player club periods from transfer facts")
    sub.add_parser("repair", help="restore fields from stored roster snapshots")
    legends = sub.add_parser("legend-update", help="resolve legends through the API and enqueue enrichment")
    legends.add_argument(
        "--source", type=Path, default=Path("data/sources/legend_candidates.txt")
    )
    legends.add_argument("--base-url", default="http://localhost:8000")
    legends.add_argument("--timeout", type=float, default=30.0)
    legends.add_argument("--refresh", action="store_true")
    legends.add_argument("--refresh-details", action="store_true")
    sub.add_parser("validate", help="run canonical database quality gates")
    sub.add_parser("status", help="show queue and entity counts")

    publish = sub.add_parser("publish", help="build and atomically publish the game database")
    publish.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    publish.add_argument("--min-players", type=int, default=1)
    publish.add_argument("--min-periods", type=int, default=1)
    publish.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="allow empty quiz difficulty or club-pair pools (pilot builds only)",
    )

    major = sub.add_parser("major-update", help="refresh configured major leagues and publish V2")
    major.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    major.add_argument("--tiers", default="1,2", help="comma-separated config tiers")
    major.add_argument("--season", default=None, help="override automatic season for every league")
    major.add_argument("--base-url", default="http://localhost:8000")
    major.add_argument("--concurrency", type=int, default=2)
    major.add_argument("--timeout", type=float, default=60.0)
    major.add_argument("--force", action="store_true")
    major.add_argument("--with-market-values", action="store_true")
    major.add_argument("--discovery-only", action="store_true")
    major.add_argument("--no-publish", action="store_true")
    major.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    major.add_argument("--min-players", type=int, default=1)
    major.add_argument("--min-periods", type=int, default=1)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    conn = initialize(args.db)
    try:
        if args.command == "init":
            _print({"database": str(args.db), "status": "initialized"})
        elif args.command == "seed":
            seeded = seed_competition_seasons(
                conn, _csv(args.competitions), _csv(args.seasons), args.refresh
            )
            _print({"seeded": seeded, "queue": queue_counts(conn)})
        elif args.command == "seed-player":
            player_ids = [int(value) for value in _csv(args.players)]
            seeded = seed_players(conn, player_ids, args.refresh)
            _print({"seeded": seeded, "queue": queue_counts(conn)})
        elif args.command in {"work", "crawl"}:
            if args.command == "crawl":
                seed_competition_seasons(
                    conn, _csv(args.competitions), _csv(args.seasons), args.refresh
                )
            conn.close()
            conn = None
            client = ApiClient(args.base_url, timeout=args.timeout, retries=getattr(args, "retries", 2))
            result = run_worker(args.db, client, args.limit, args.concurrency)
            check = initialize(args.db)
            try:
                result["queue"] = queue_counts(check)
            finally:
                check.close()
            _print(result)
        elif args.command == "derive":
            _print(derive_all_periods(conn))
        elif args.command == "repair":
            _print(repair_snapshots(conn))
        elif args.command == "legend-update":
            _print(sync_legends(
                conn,
                ApiClient(args.base_url, timeout=args.timeout),
                args.source,
                refresh=args.refresh,
                refresh_details=args.refresh_details,
            ))
        elif args.command in {"validate", "status"}:
            _print(validate_source(conn))
        elif args.command == "publish":
            conn.close()
            conn = None
            _print(
                publish_game_db(
                    args.db,
                    args.output,
                    min_players=args.min_players,
                    min_periods=args.min_periods,
                    strict=not args.allow_incomplete,
                )
            )
        elif args.command == "major-update":
            conn.close()
            conn = None
            client = ApiClient(args.base_url, timeout=args.timeout)
            _print(update_major_leagues(
                args.db,
                client,
                args.config,
                {int(value) for value in _csv(args.tiers)},
                args.season,
                args.concurrency,
                args.force,
                args.with_market_values,
                args.discovery_only,
                None if args.no_publish or args.discovery_only else args.output,
                args.min_players,
                args.min_periods,
            ))
    finally:
        if conn is not None:
            conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
