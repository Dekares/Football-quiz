from __future__ import annotations

import sqlite3
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from data.pipeline.client import ApiResponse
from data.pipeline.database import initialize, queue_counts, utcnow
from data.pipeline.derive import derive_all_periods
from data.pipeline.ingest import ingest_player_profile, run_worker, seed_competition_seasons
from data.pipeline.major import (
    current_season,
    load_config,
    resolve_discovered_seasons,
    selected_leagues,
)
from data.pipeline.maintenance import import_legends, repair_roster_snapshots
from data.pipeline.publish import pair_eligible_club, publish_game_db
from data.pipeline.quiz_pools import recognition_score
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
            "known": 1,
            "less_known": 3,
            "obscure": 6,
        })
        self.assertEqual(options["leagues"][1]["counts"], {
            "known": 2,
            "less_known": 3,
            "obscure": 5,
        })
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
        rebuilt.close()

    def test_recognition_score_rewards_prominence(self):
        unknown = recognition_score(1_000_000, 0, 2, False)
        established = recognition_score(25_000_000, 8, 5, False)
        legend = recognition_score(25_000_000, 8, 5, True)
        self.assertLess(unknown, established)
        self.assertLess(established, legend)

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

    def test_legend_import_creates_manual_periods(self):
        conn = initialize(self.source)
        source = self.root / "legends.json"
        source.write_text(json.dumps([{
            "name": "Legend Player", "first_name": "Legend", "last_name": "Player",
            "country": "Italy", "position": "Midfield", "date_of_birth": "1970-01-01",
            "highest_market_value": 50_000_000, "image_url": "https://example.test/player.jpg",
            "clubs": [{
                "club_id": 10, "name": "Club A", "from": "1990-01-01", "to": "1995-01-01"
            }],
        }]), encoding="utf-8")
        result = import_legends(conn, source)
        self.assertEqual(result["legends"], 1)
        self.assertEqual(conn.execute(
            "SELECT COUNT(*) FROM players WHERE is_legend=1"
        ).fetchone()[0], 1)
        self.assertEqual(conn.execute(
            "SELECT COUNT(*) FROM player_club_periods WHERE source='manual'"
        ).fetchone()[0], 1)
        conn.close()


if __name__ == "__main__":
    unittest.main()
