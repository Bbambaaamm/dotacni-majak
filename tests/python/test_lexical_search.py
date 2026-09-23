import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "search" / "src"))

from dotacni_majak_search import SqliteLexicalSearch, build_fts_query


class LexicalSearchTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.execute("PRAGMA foreign_keys = ON")
        for path in sorted((ROOT / "migrations").glob("*.sql")):
            self.connection.executescript(path.read_text(encoding="utf-8"))

        self.connection.execute(
            "INSERT INTO providers(id,name,provider_type) VALUES ('p','NSA','NATIONAL')"
        )
        self.connection.execute(
            "INSERT INTO programmes(id,provider_id,name,funding_origin) "
            "VALUES ('pr','p','Sport','CZ_NATIONAL')"
        )

        calls = [
            ("g1","v1","regiony-2027","Regionální sportovní infrastruktura",
             "OPEN","Podpora modernizace sportovních zařízení.",
             "rekonstrukce technické zhodnocení venkovní sportoviště",
             "stavba povrch osvětlení","sport tenis"),
            ("g2","v2","digital-2027","Digitalizace podniků",
             "OPEN","Podpora zavádění digitálních technologií ve firmách.",
             "software automatizace digitalizace","software hardware","podnikání"),
            ("g3","v3","old-sport","Ukončené sportoviště",
             "CLOSED","Historická výzva na sportovní zařízení.",
             "rekonstrukce sportoviště","stavba","sport")
        ]

        for g,v,slug,title,status,summary,activities,costs,keywords in calls:
            self.connection.execute(
                "INSERT INTO grant_calls("
                "id,programme_id,canonical_slug,current_status,current_title,"
                "first_seen_at,created_at,updated_at"
                ") VALUES (?,?,?,?,?,?,?,?)",
                (
                    g,"pr",slug,status,title,
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T00:00:00Z",
                ),
            )
            self.connection.execute(
                "INSERT INTO grant_call_versions("
                "id,grant_call_id,version_number,captured_at,title,status,"
                "verification_status,created_at"
                ") VALUES (?,?,?,?,?,?,?,?)",
                (
                    v,g,1,"2026-01-01T00:00:00Z",title,status,
                    "VERIFIED","2026-01-01T00:00:00Z",
                ),
            )
            self.connection.execute(
                "INSERT INTO grant_search_documents("
                "grant_call_version_id,title,summary,supported_activities,"
                "eligible_costs,keywords,status,updated_at"
                ") VALUES (?,?,?,?,?,?,?,?)",
                (
                    v,title,summary,activities,costs,keywords,status,
                    "2026-01-01T00:00:00Z",
                ),
            )

    def tearDown(self):
        self.connection.close()

    def test_public_query_cannot_inject_fts_operators(self):
        query = build_fts_query('tenis OR "digitalizace" NEAR(boom)')
        self.assertNotIn(" OR ", query)
        self.assertNotIn("NEAR(", query)
        self.assertEqual(
            query,
            '"tenis" "or" "digitalizace" "near" "boom"',
        )

    def test_diacritic_insensitive_search(self):
        hits = SqliteLexicalSearch(self.connection).search(
            "technicke zhodnoceni sportoviste"
        )
        self.assertEqual([hit.grant_call_version_id for hit in hits], ["v1"])

    def test_closed_calls_are_excluded_by_default(self):
        hits = SqliteLexicalSearch(self.connection).search("sportoviste")
        self.assertEqual([hit.grant_call_version_id for hit in hits], ["v1"])

    def test_title_and_activity_weight_return_sport_call(self):
        hits = SqliteLexicalSearch(self.connection).search(
            "regionalni sportovni infrastruktura"
        )
        self.assertTrue(hits)
        self.assertEqual(hits[0].grant_call_version_id, "v1")

    def test_update_trigger_replaces_indexed_text(self):
        self.connection.execute(
            "UPDATE grant_search_documents "
            "SET supported_activities='plavání bazén' "
            "WHERE grant_call_version_id='v1'"
        )
        old = SqliteLexicalSearch(self.connection).search("rekonstrukce")
        new = SqliteLexicalSearch(self.connection).search("plavani bazen")
        self.assertEqual(old, [])
        self.assertEqual([hit.grant_call_version_id for hit in new], ["v1"])

    def test_delete_trigger_removes_fts_row(self):
        self.connection.execute(
            "DELETE FROM grant_search_documents WHERE grant_call_version_id='v1'"
        )
        hits = self.connection.execute(
            "SELECT count(*) FROM grant_search_fts "
            "WHERE grant_search_fts MATCH 'tenis'"
        ).fetchone()[0]
        self.assertEqual(hits, 0)


if __name__ == "__main__":
    unittest.main()
