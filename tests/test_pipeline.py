from __future__ import annotations

import sqlite3
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from data.pipeline.client import ApiError, ApiResponse
from data.pipeline.database import fail_job, initialize, queue_counts, utcnow
from data.pipeline.derive import derive_all_periods
from data.pipeline.ingest import (
    ingest_club_players,
    ingest_player_profile,
    run_worker,
    seed_competition_seasons,
)
from data.pipeline.major import (
    current_season,
    load_config,
    reconcile_current_rosters,
    restrict_pending_player_jobs,
    resolve_discovered_seasons,
    selected_leagues,
)
from data.pipeline.maintenance import (
    _resolved_search_player,
    load_legend_candidates,
    repair_placeholder_flags,
    repair_roster_snapshots,
    sync_legends,
)
from data.pipeline.publish import pair_eligible_club, publish_game_db
from data.pipeline.quiz_pools import (
    _ranked_buckets,
    classify_career_status,
    recognition_score,
)
from data.pipeline.validation import validate_source
from backend.app.api.classic import _day_number, _select_secret
from backend.app.api.quiz import _load_quiz, _quiz_options


class FakeClient:
    def get(self, path, params=None):
        if path == "/competitions/GB1/clubs":
            return ApiResponse(
                url="http://test/competitions/GB1/clubs?season_id=2025",
                status=200,
                payload={
                    "id": "GB1",
                    "name": "Premier League",
                    "seasonId": "2025",
                    "clubs": [{"id": "11", "name": "Arsenal FC"}],
                },
            )
        raise AssertionError(path)


class FakeLegendClient:
    def get(self, path, params=None):
        self.path = path
        return ApiResponse(
            url=f"http://test{path}",
            status=200,
            payload={
                "results": [{
                    "id": "42",
                    "name": "Legend Player",
                    "club": {"id": "0", "name": "Retired"},
                }],
            },
        )


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "source.db"

    def tearDown(self):
        self.tmp.cleanup()

    def test_queue_is_idempotent_and_worker_stores_snapshot(self):
        conn = initialize(self.source)
        seed_competition_seasons(conn, ["GB1"], ["2025"])
        seed_competition_seasons(conn, ["GB1"], ["2025"])
        self.assertEqual(queue_counts(conn)["pending"], 1)
        conn.close()

        result = run_worker(self.source, FakeClient(), limit=1, concurrency=1)
        self.assertEqual(result, {"claimed": 1, "succeeded": 1, "failed": 0})
        conn = initialize(self.source)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM api_snapshots").fetchone()[0], 1)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM clubs").fetchone()[0], 1)
        self.assertEqual(queue_counts(conn)["pending"], 1)
        conn.close()

    def test_major_league_scope_and_split_year_season(self):
        config = load_config()
        self.assertEqual(len(selected_leagues(config, {1, 2}, "2026")), 12)
        self.assertEqual(current_season("split_year", date(2026, 6, 30)), "2025")
        self.assertEqual(current_season("split_year", date(2026, 7, 1)), "2026")
        self.assertEqual(current_season("calendar_year", date(2026, 7, 1)), "2026")

    def test_discovery_can_resolve_api_season_fallback(self):
        conn = initialize(self.source)
        now = utcnow()
        conn.execute(
            "INSERT INTO competitions(competition_id,name,created_at,updated_at) "
            "VALUES ('MLS1','MLS',?,?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO seasons(season_id,label,created_at,updated_at) "
            "VALUES ('2025','2025',?,?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO competition_seasons VALUES ('MLS1','2025',?)", (now,)
        )
        resolved = resolve_discovered_seasons(conn, [{
            "competition_id": "MLS1", "season_id": "2026"
        }])
        self.assertEqual(resolved[0]["season_id"], "2025")
        conn.close()

    def test_youth_clubs_are_excluded_from_matchmaking(self):
        self.assertFalse(pair_eligible_club("Chelsea FC U21"))
        self.assertFalse(pair_eligible_club("Man City Youth"))
        self.assertFalse(pair_eligible_club("Roma Academy"))
        self.assertFalse(pair_eligible_club("Inter Milan Primavera"))
        self.assertFalse(pair_eligible_club("Atlético Yth."))
        self.assertTrue(pair_eligible_club("BSC Young Boys"))

    def test_placeholder_repair_reverses_legacy_club_id_contamination(self):
        conn = initialize(self.source)
        now = utcnow()
        conn.execute(
            """
            INSERT INTO clubs(club_id,name,is_placeholder,created_at,updated_at)
            VALUES (1,'Real Madrid',1,?,?)
            """,
            (now, now),
        )
        result = repair_placeholder_flags(conn)
        self.assertEqual(result["clubs_changed"], 1)
        self.assertEqual(
            conn.execute("SELECT is_placeholder FROM clubs WHERE club_id=1").fetchone()[0],
            0,
        )
        conn.close()

    def test_permanent_http_error_is_not_retried(self):
        conn = initialize(self.source)
        seed_competition_seasons(conn, ["GB1"], ["2026"])
        row = dict(conn.execute("SELECT * FROM crawl_jobs").fetchone())
        row["attempts"] = 1
        fail_job(conn, row, ApiError("HTTP 404", status=404))
        failed = conn.execute(
            "SELECT status,attempts FROM crawl_jobs WHERE job_id=?", (row["job_id"],)
        ).fetchone()
        self.assertEqual(tuple(failed), ("dead", 0))
        conn.close()

    def test_api_client_preserves_http_status(self):
        from unittest.mock import patch
        from urllib.error import HTTPError

        from data.pipeline.client import ApiClient

        error = HTTPError("http://example.test", 404, "Not Found", None, None)
        with patch("data.pipeline.client.urlopen", side_effect=error):
            with self.assertRaises(ApiError) as raised:
                ApiClient("http://example.test", retries=0).get("/missing")
        self.assertEqual(raised.exception.status, 404)

    def test_transfer_period_derivation_handles_return_to_club(self):
        conn = initialize(self.source)
        now = utcnow()
        conn.execute(
            "INSERT INTO players(player_id,name,profile_loaded,created_at,updated_at) VALUES (1,'Player',1,?,?)",
            (now, now),
        )
        conn.executemany(
            "INSERT INTO clubs(club_id,name,created_at,updated_at) VALUES (?,?,?,?)",
            [(10, "A", now, now), (20, "B", now, now)],
        )
        conn.executemany(
            """
            INSERT INTO transfers(
                transfer_id,player_id,from_club_id,to_club_id,transfer_date,is_upcoming,fetched_at
            ) VALUES (?,?,?,?,?,0,?)
            """,
            [("t1", 1, 10, 20, "2020-07-01", now), ("t2", 1, 20, 10, "2022-07-01", now)],
        )
        conn.commit()
        result = derive_all_periods(conn)
        self.assertEqual(result["periods"], 3)
        periods = conn.execute(
            "SELECT club_id,date_from,date_to FROM player_club_periods ORDER BY period_id"
        ).fetchall()
        self.assertEqual(tuple(periods[1]), (20, "2020-07-01", "2022-07-01"))
        self.assertEqual(tuple(periods[2]), (10, "2022-07-01", None))
        conn.close()

    def test_current_roster_resolves_multiple_open_transfer_periods(self):
        conn = initialize(self.source)
        now = utcnow()
        conn.executemany(
            "INSERT INTO clubs(club_id,name,created_at,updated_at) VALUES (?,?,?,?)",
            [
                (10, "Parent Club", now, now),
                (20, "Loan Club", now, now),
                (30, "Current Club", now, now),
            ],
        )
        conn.execute(
            """
            INSERT INTO players(
                player_id,name,current_club_id,profile_loaded,created_at,updated_at
            ) VALUES (1,'Player',30,1,?,?)
            """,
            (now, now),
        )
        conn.execute(
            "INSERT INTO seasons(season_id,label,created_at,updated_at) VALUES ('2026','2026',?,?)",
            (now, now),
        )
        conn.executemany(
            """
            INSERT INTO transfers(
                transfer_id,player_id,from_club_id,to_club_id,transfer_date,is_upcoming,fetched_at
            ) VALUES (?,?,?,?,?,0,?)
            """,
            [
                ("t1", 1, 10, 20, "2022-07-01", now),
                ("t2", 1, 20, 10, "2023-06-30", now),
                ("t3", 1, 10, 30, "2024-07-01", now),
                ("t4", 1, 10, 30, "2024-07-01", now),
            ],
        )
        conn.execute(
            """
            INSERT INTO club_rosters(
                club_id,season_id,player_id,joined_on,discovered_at
            ) VALUES (30,'2026',1,'2021-07-01',?)
            """,
            (now,),
        )
        conn.commit()

        derive_all_periods(conn)
        open_periods = conn.execute(
            """
            SELECT club_id,date_from,source
            FROM player_club_periods
            WHERE player_id=1 AND date_to IS NULL
            """
        ).fetchall()
        self.assertEqual(
            [tuple(row) for row in open_periods],
            [(30, "2024-07-01", "roster")],
        )
        self.assertEqual(validate_source(conn)["errors"], [])
        conn.close()

    def test_current_roster_reconciles_club_and_closes_previous_period(self):
        conn = initialize(self.source)
        now = utcnow()
        conn.execute(
            "INSERT INTO competitions(competition_id,name,created_at,updated_at) "
            "VALUES ('GB1','Premier League',?,?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO seasons(season_id,label,created_at,updated_at) "
            "VALUES ('2026','2026',?,?)",
            (now, now),
        )
        conn.executemany(
            "INSERT INTO clubs(club_id,name,created_at,updated_at) VALUES (?,?,?,?)",
            [(10, "Old Club", now, now), (20, "New Club", now, now)],
        )
        conn.execute("INSERT INTO competition_seasons VALUES ('GB1','2026',?)", (now,))
        conn.execute("INSERT INTO competition_clubs VALUES ('GB1','2026',20,?)", (now,))
        conn.execute(
            """
            INSERT INTO players(
                player_id,name,current_club_id,profile_loaded,created_at,updated_at
            ) VALUES (1,'Player',10,1,?,?)
            """,
            (now, now),
        )
        conn.execute(
            """
            INSERT INTO transfers(
                transfer_id,player_id,from_club_id,to_club_id,transfer_date,
                is_upcoming,fetched_at
            ) VALUES ('t1',1,NULL,10,'2020-07-01',0,?)
            """,
            (now,),
        )
        conn.execute(
            """
            INSERT INTO club_rosters(
                club_id,season_id,player_id,joined_on,discovered_at
            ) VALUES (20,'2026',1,'2026-07-01',?)
            """,
            (now,),
        )
        conn.commit()

        result = reconcile_current_rosters(conn, [{
            "competition_id": "GB1", "season_id": "2026"
        }])
        derive_all_periods(conn)

        self.assertEqual(result["changed_player_ids"], [1])
        self.assertEqual(
            conn.execute("SELECT current_club_id FROM players WHERE player_id=1").fetchone()[0],
            20,
        )
        periods = conn.execute(
            "SELECT club_id,date_from,date_to FROM player_club_periods "
            "WHERE player_id=1 ORDER BY date_from"
        ).fetchall()
        self.assertEqual(
            [tuple(row) for row in periods],
            [(10, "2020-07-01", "2026-07-01"), (20, "2026-07-01", None)],
        )
        conn.close()

    def test_roster_refresh_updates_current_market_value(self):
        conn = initialize(self.source)
        now = utcnow()
        conn.execute(
            "INSERT INTO clubs(club_id,name,created_at,updated_at) VALUES (10,'Club',?,?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO players(player_id,name,current_market_value,created_at,updated_at) "
            "VALUES (1,'Player',1000000,?,?)",
            (now, now),
        )
        ingest_club_players(
            conn,
            {"entity_id": "10", "params": {"season_id": "2026"}},
            {"id": 10, "players": [{
                "id": 1,
                "name": "Player",
                "marketValue": 2500000,
                "position": "Attack",
            }]},
        )
        self.assertEqual(
            conn.execute(
                "SELECT current_market_value FROM players WHERE player_id=1"
            ).fetchone()[0],
            2500000,
        )
        conn.close()

    def test_incremental_update_defers_unselected_roster_jobs(self):
        conn = initialize(self.source)
        now = utcnow()
        for player_id in (1, 2):
            conn.execute(
                "INSERT INTO players(player_id,name,created_at,updated_at) VALUES (?,?,?,?)",
                (player_id, f"Player {player_id}", now, now),
            )
        conn.commit()
        from data.pipeline.ingest import seed_players

        seed_players(conn, [1, 2])
        deferred = restrict_pending_player_jobs(conn, {
            "player_profile": [1],
            "player_transfers": [2],
            "player_market_value": [],
        })
        pending = {
            (row["endpoint"], int(row["entity_id"]))
            for row in conn.execute(
                "SELECT endpoint,entity_id FROM crawl_jobs WHERE status='pending'"
            )
        }
        self.assertEqual(pending, {("player_profile", 1), ("player_transfers", 2)})
        self.assertEqual(deferred["player_market_value"], 2)
        conn.close()

    def test_publish_creates_legacy_compatible_database(self):
        conn = initialize(self.source)
        now = utcnow()
        conn.execute(
            "INSERT INTO competitions(competition_id,name,created_at,updated_at) VALUES ('GB1','Premier League',?,?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO seasons(season_id,label,created_at,updated_at) VALUES ('2026','2026',?,?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO competition_seasons VALUES ('GB1','2026',?)",
            (now,),
        )
        conn.executemany(
            "INSERT INTO clubs(club_id,name,current_competition_id,created_at,updated_at) VALUES (?,?, 'GB1',?,?)",
            [(10, "Club A", now, now), (20, "Club B", now, now)],
        )
        conn.execute(
            "INSERT INTO competition_clubs VALUES ('GB1','2026',20,?)",
            (now,),
        )
        values = [
            100_000_000, 90_000_000, 80_000_000, 70_000_000, 60_000_000,
            50_000_000, 40_000_000, 30_000_000, 20_000_000, 10_000_000,
        ]
        for player_id, value in enumerate(values, 1):
            conn.execute(
                """
                INSERT INTO players(
                    player_id,name,position,current_club_id,current_market_value,highest_market_value,
                    profile_loaded,created_at,updated_at
                ) VALUES (?,?, 'Centre-Forward',20,?,?,1,?,?)
                """,
                (player_id, f"Player {player_id}", value, value, now, now),
            )
            conn.execute(
                "INSERT INTO player_nationalities VALUES (?, 'England', 0)", (player_id,)
            )
            conn.execute(
                """
                INSERT INTO club_rosters(
                    club_id,season_id,player_id,position,market_value,discovered_at
                ) VALUES (20,'2026',?,'Centre-Forward',?,?)
                """,
                (player_id, value, now),
            )
            conn.executemany(
                """
                INSERT INTO player_club_periods(
                    player_id,club_id,date_from,date_to,source,confidence,created_at
                ) VALUES (?,?,?,?,'manual','exact',?)
                """,
                [(player_id, 10, "2020-01-01", "2021-01-01", now),
                 (player_id, 20, "2021-01-01", None, now)],
            )
        conn.commit()
        conn.close()

        output = self.root / "game.db"
        result = publish_game_db(self.source, output, strict=False)
        self.assertTrue(result["validation"]["ok"])
        game = sqlite3.connect(output)
        game.row_factory = sqlite3.Row
        self.assertEqual(game.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(game.execute("SELECT COUNT(*) FROM players").fetchone()[0], 10)
        self.assertEqual(
            game.execute(
                "SELECT COUNT(*) FROM players WHERE career_status='regular'"
            ).fetchone()[0],
            10,
        )
        self.assertEqual(game.execute("SELECT COUNT(*) FROM quiz_pool").fetchone()[0], 10)
        self.assertEqual(
            game.execute("SELECT COUNT(*) FROM global_quiz_pool").fetchone()[0],
            10,
        )
        self.assertEqual(_day_number(date(2026, 7, 1)), 1)
        first_daily = game.execute(
            """
            SELECT challenge_date,day_number,player_id
            FROM daily_challenges
            ORDER BY challenge_date
            LIMIT 1
            """
        ).fetchone()
        future_daily = game.execute(
            "SELECT challenge_date,player_id FROM daily_challenges "
            "ORDER BY challenge_date DESC LIMIT 1"
        ).fetchone()
        self.assertEqual(tuple(first_daily[:2]), ("2026-07-01", 1))
        self.assertEqual(
            game.execute(
                """
                SELECT COUNT(*) FROM daily_challenges d
                LEFT JOIN global_quiz_pool g
                  ON g.player_id=d.player_id AND g.recognition='known'
                WHERE g.player_id IS NULL
                """
            ).fetchone()[0],
            0,
        )
        self.assertEqual(game.execute("SELECT COUNT(*) FROM competitions").fetchone()[0], 1)
        self.assertEqual(
            game.execute(
                "SELECT COUNT(*) FROM quiz_pool WHERE competition_id='GB1'"
            ).fetchone()[0],
            10,
        )
        self.assertEqual(
            game.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT player_id FROM quiz_pool
                    GROUP BY player_id HAVING COUNT(DISTINCT recognition) != 1
                )
                """
            ).fetchone()[0],
            0,
        )
        secret = _select_secret(game, "2026-07-01")
        self.assertIsNotNone(secret)
        self.assertEqual(secret["player_id"], first_daily["player_id"])
        self.assertEqual(secret["day_number"], 1)
        options = _quiz_options(game)
        self.assertEqual(options["leagues"][1]["id"], "GB1")
        self.assertEqual(options["leagues"][0]["counts"], {
            "known": 3,
            "less_known": 3,
            "obscure": 4,
        })
        self.assertEqual(options["leagues"][1]["counts"], {
            "known": 3,
            "less_known": 3,
            "obscure": 4,
        })
        game.execute(
            "INSERT INTO competitions VALUES ('LEGENDS','Career Legends','International',NULL,99,1)"
        )
        game.execute(
            """
            INSERT INTO players(
                player_id,name,search_name,country_of_citizenship,position,is_legend,
                career_status
            ) VALUES (
                99,'Legend Player','legend player','Italy','Midfield',1,
                'retired_legend'
            )
            """
        )
        game.execute(
            "INSERT INTO quiz_pool VALUES ('LEGENDS','obscure','hard',99,100,1)"
        )
        game.execute("INSERT INTO world_xi_legend_pool VALUES (99,100,1)")
        game.commit()
        options = _quiz_options(game)
        world = options["leagues"][0]
        legends = next(item for item in options["leagues"] if item["id"] == "LEGENDS")
        self.assertEqual(world["name"], "World XI")
        self.assertEqual(world["counts"], {
            "known": 4,
            "less_known": 3,
            "obscure": 4,
        })
        self.assertTrue(world["uses_recognition"])
        self.assertFalse(legends["uses_recognition"])
        self.assertEqual(legends["total_count"], 1)
        legend_question = _load_quiz(game, "LEGENDS", "known", [])
        self.assertEqual(legend_question["player_id"], 99)
        active_world_known_ids = [
            row[0] for row in game.execute(
                """
                SELECT player_id FROM global_quiz_pool WHERE recognition='known'
                UNION
                SELECT player_id FROM quiz_pool
                WHERE competition_id!='LEGENDS' AND recognition='known'
                """
            )
        ]
        world_legend = _load_quiz(
            game,
            "ALL",
            "known",
            active_world_known_ids,
        )
        self.assertEqual(world_legend["player_id"], 99)
        global_question = _load_quiz(game, "ALL", "known", [])
        self.assertIsNotNone(global_question)
        self.assertEqual(global_question["league"], "ALL")
        question = _load_quiz(game, "GB1", "known", [])
        self.assertIsNotNone(question)
        self.assertEqual(question["league"], "GB1")
        self.assertEqual(question["recognition"], "known")
        self.assertEqual(game.execute("SELECT COUNT(*) FROM club_pair_stats").fetchone()[0], 1)
        self.assertEqual(game.execute("SELECT COUNT(*) FROM pragma_foreign_key_check").fetchone()[0], 0)
        scheduled_player = int(first_daily["player_id"])
        game.close()

        source = initialize(self.source)
        source.execute(
            "UPDATE players SET highest_market_value=1,current_market_value=1 WHERE player_id=?",
            (scheduled_player,),
        )
        replacement = 10 if scheduled_player != 10 else 9
        source.execute(
            """
            UPDATE players
            SET highest_market_value=200000000,current_market_value=200000000
            WHERE player_id=?
            """,
            (replacement,),
        )
        source.commit()
        source.close()
        publish_game_db(self.source, output, strict=False)
        rebuilt = sqlite3.connect(output)
        self.assertEqual(
            rebuilt.execute(
                "SELECT player_id FROM daily_challenges WHERE challenge_date='2026-07-01'"
            ).fetchone()[0],
            scheduled_player,
        )
        self.assertNotEqual(
            rebuilt.execute(
                "SELECT player_id FROM daily_challenges WHERE challenge_date=?",
                (future_daily["challenge_date"],),
            ).fetchone()[0],
            future_daily["player_id"],
        )
        rebuilt.close()

    def test_recognition_score_rewards_prominence(self):
        unknown = recognition_score(1_000_000, 0, 2, False)
        established = recognition_score(25_000_000, 8, 5, False)
        legend = recognition_score(25_000_000, 8, 5, True)
        breakout = recognition_score(
            80_000_000,
            50,
            3,
            False,
            current_market_value=80_000_000,
            elite_club_years=0.5,
            career_years=2,
        )
        veteran = recognition_score(
            60_000_000,
            50,
            5,
            False,
            current_market_value=15_000_000,
            elite_club_years=8,
            career_years=12,
        )
        self.assertLess(unknown, established)
        self.assertLess(established, legend)
        self.assertLess(breakout, veteran)

    def test_career_status_separates_active_and_retired_legends(self):
        base = {
            "is_legend": False,
            "date_of_birth": "1990-01-01",
            "career_years": 15,
            "elite_club_years": 10,
            "highest_market_value": 100_000_000,
            "score": 80,
        }
        today = date(2026, 9, 5)
        self.assertEqual(
            classify_career_status(base, is_active=True, today=today),
            "active_legend",
        )
        self.assertEqual(
            classify_career_status(
                {**base, "date_of_birth": "1998-01-01"},
                is_active=True,
                today=today,
            ),
            "active_star",
        )
        self.assertEqual(
            classify_career_status(
                {**base, "career_years": 3},
                is_active=True,
                today=today,
            ),
            "active_star",
        )
        self.assertEqual(
            classify_career_status(
                {**base, "is_legend": True},
                is_active=False,
                today=today,
            ),
            "retired_legend",
        )
        self.assertEqual(
            classify_career_status(
                {**base, "score": 40},
                is_active=False,
                today=today,
            ),
            "regular",
        )

    def test_known_bucket_respects_score_floor_and_minimum(self):
        players = [
            {
                "player_id": index,
                "name": f"Player {index:03}",
                "score": 80 if index < 2 else 40,
                "highest_market_value": 100_000_000 - index,
            }
            for index in range(100)
        ]
        buckets = _ranked_buckets(
            players,
            known_min_score=65,
            known_min_count=5,
        )
        self.assertEqual(len(buckets["known"]), 6)
        self.assertEqual(len(buckets["less_known"]), 30)
        self.assertEqual(len(buckets["obscure"]), 64)

        league_relative = _ranked_buckets(
            players,
            ratios=(0.18, 0.30),
            known_min_score=65,
            known_min_count=5,
        )
        self.assertEqual(len(league_relative["known"]), 18)
        self.assertEqual(len(league_relative["less_known"]), 30)
        self.assertEqual(len(league_relative["obscure"]), 52)

    def test_roster_repair_restores_birth_date(self):
        conn = initialize(self.source)
        now = utcnow()
        conn.execute(
            "INSERT INTO players(player_id,name,profile_loaded,created_at,updated_at) "
            "VALUES (1,'Player',1,?,?)",
            (now, now),
        )
        payload = {"players": [{
            "id": 1, "name": "Player", "dateOfBirth": "2000-01-02",
            "position": "Attack", "nationality": ["England"],
        }]}
        conn.execute(
            """
            INSERT INTO api_snapshots(
                request_key,endpoint,entity_type,entity_id,request_url,http_status,
                response_json,content_hash,parser_version,fetched_at
            ) VALUES ('roster','club_players','club','10','http://test',200,?,'hash',1,?)
            """,
            (json.dumps(payload), now),
        )
        conn.commit()
        result = repair_roster_snapshots(conn)
        row = conn.execute(
            "SELECT date_of_birth,position FROM players WHERE player_id=1"
        ).fetchone()
        self.assertEqual(result["birth_dates_restored"], 1)
        self.assertEqual(tuple(row), ("2000-01-02", "Attack"))
        self.assertEqual(
            conn.execute("SELECT nationality FROM player_nationalities").fetchone()[0],
            "England",
        )
        conn.close()

    def test_sparse_profile_does_not_erase_roster_fields(self):
        conn = initialize(self.source)
        now = utcnow()
        conn.execute(
            """
            INSERT INTO players(
                player_id,name,date_of_birth,position,profile_loaded,created_at,updated_at
            ) VALUES (1,'Player','2000-01-02','Attack',0,?,?)
            """,
            (now, now),
        )
        conn.execute("INSERT INTO player_nationalities VALUES (1,'England',0)")
        ingest_player_profile(conn, {"entity_id": "1"}, {"id": 1, "name": "Player"})
        row = conn.execute(
            "SELECT date_of_birth,position,profile_loaded FROM players WHERE player_id=1"
        ).fetchone()
        self.assertEqual(tuple(row), ("2000-01-02", "Attack", 1))
        self.assertEqual(
            conn.execute("SELECT nationality FROM player_nationalities").fetchone()[0],
            "England",
        )
        conn.close()

    def test_legend_sync_resolves_real_id_and_removes_legacy_player(self):
        conn = initialize(self.source)
        now = utcnow()
        conn.execute(
            """
            INSERT INTO players(player_id,name,is_legend,created_at,updated_at)
            VALUES (9000001,'Old Manual Legend',1,?,?)
            """,
            (now, now),
        )
        source = self.root / "legend_candidates.txt"
        source.write_text("# identities only\nLegend Player\n", encoding="utf-8")
        client = FakeLegendClient()
        result = sync_legends(conn, client, source)
        self.assertEqual(result["resolved"], 1)
        self.assertEqual(result["legacy_removed"], 1)
        self.assertIn("Legend%20Player", client.path)
        self.assertEqual(
            conn.execute("SELECT player_id FROM players WHERE is_legend=1").fetchone()[0],
            42,
        )
        self.assertEqual(conn.execute(
            "SELECT COUNT(*) FROM player_club_periods WHERE source='manual'"
        ).fetchone()[0], 0)
        self.assertEqual(queue_counts(conn)["pending"], 3)
        conn.close()

    def test_ambiguous_legend_requires_pinned_transfermarkt_id(self):
        results = [
            {"id": "10", "name": "Adriano", "position": "LB"},
            {"id": "20", "name": "Adriano", "position": "CF"},
        ]
        self.assertIsNone(_resolved_search_player("Adriano", results))
        match = _resolved_search_player("Adriano", results, expected_player_id=20)
        self.assertIsNotNone(match)
        self.assertEqual(match[0], 20)

        source = self.root / "legend_candidates.txt"
        source.write_text("Adriano|20\n", encoding="utf-8")
        candidates = load_legend_candidates(source)
        self.assertEqual(candidates[0].name, "Adriano")
        self.assertEqual(candidates[0].player_id, 20)

    def test_pinned_legend_never_falls_back_to_wrong_cached_id(self):
        class FailingClient:
            def get(self, path, params=None):
                raise ApiError("search unavailable")

        conn = initialize(self.source)
        now = utcnow()
        conn.execute(
            """
            INSERT INTO players(player_id,name,created_at,updated_at)
            VALUES (10,'Wrong Adriano',?,?)
            """,
            (now, now),
        )
        conn.execute(
            """
            INSERT INTO legend_registry(
                candidate_name,player_id,resolved_name,status,last_checked_at
            ) VALUES ('Adriano',10,'Adriano','resolved',?)
            """,
            (now,),
        )
        conn.commit()
        source = self.root / "legend_candidates.txt"
        source.write_text("Adriano|20\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "resolved 0/1"):
            sync_legends(conn, FailingClient(), source)
        conn.close()

    def test_corrected_legend_identity_removes_orphaned_wrong_career(self):
        class CorrectedClient:
            def get(self, path, params=None):
                return ApiResponse(
                    url=f"http://test{path}",
                    status=200,
                    payload={"results": [{"id": "20", "name": "Adriano"}]},
                )

        conn = initialize(self.source)
        now = utcnow()
        conn.execute(
            "INSERT INTO clubs(club_id,name,created_at,updated_at) VALUES (1,'Club',?,?)",
            (now, now),
        )
        conn.execute(
            """
            INSERT INTO players(player_id,name,is_legend,created_at,updated_at)
            VALUES (10,'Adriano',1,?,?)
            """,
            (now, now),
        )
        conn.execute(
            """
            INSERT INTO transfers(
                transfer_id,player_id,to_club_id,transfer_date,is_upcoming,fetched_at
            ) VALUES ('wrong-career',10,1,'2000-07-01',0,?)
            """,
            (now,),
        )
        conn.execute(
            """
            INSERT INTO legend_registry(
                candidate_name,player_id,resolved_name,status,last_checked_at
            ) VALUES ('Adriano',10,'Adriano','resolved',?)
            """,
            (now,),
        )
        conn.commit()
        source = self.root / "legend_candidates.txt"
        source.write_text("Adriano|20\n", encoding="utf-8")

        result = sync_legends(
            conn,
            CorrectedClient(),
            source,
            refresh=True,
            enqueue_details=False,
        )

        self.assertEqual(result["legacy_removed"], 1)
        self.assertIsNone(
            conn.execute("SELECT 1 FROM players WHERE player_id=10").fetchone()
        )
        self.assertIsNone(
            conn.execute("SELECT 1 FROM transfers WHERE player_id=10").fetchone()
        )
        self.assertEqual(
            conn.execute(
                "SELECT player_id FROM legend_registry WHERE candidate_name='Adriano'"
            ).fetchone()[0],
            20,
        )
        conn.close()


if __name__ == "__main__":
    unittest.main()
