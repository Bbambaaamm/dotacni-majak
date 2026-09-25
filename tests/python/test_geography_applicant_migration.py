import json
import sqlite3
import unittest
from pathlib import Path


class GeographyApplicantMigrationTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[2]
        self.migrations = sorted((self.root / "migrations").glob("*.sql"))
        self.target = self.root / "migrations" / "0023_geography_applicant_rules.sql"

    def migrate_all(self):
        connection = sqlite3.connect(":memory:")
        connection.execute("PRAGMA foreign_keys = ON")
        for path in self.migrations:
            connection.executescript(path.read_text(encoding="utf-8"))
        return connection

    def migrate_before_target(self):
        connection = sqlite3.connect(":memory:")
        connection.execute("PRAGMA foreign_keys = ON")
        for path in self.migrations:
            if path.name >= self.target.name:
                break
            connection.executescript(path.read_text(encoding="utf-8"))
        return connection

    def test_geography_and_grant_geography_constraints(self):
        connection = self.migrate_all()
        connection.execute(
            "INSERT INTO geographies(id,geography_type,name,country_code) "
            "VALUES ('cz','COUNTRY','Česko','CZ')"
        )
        connection.execute(
            "INSERT INTO geographies("
            "id,geography_type,name,parent_id,country_code,nuts_code"
            ") VALUES ('plk','REGION','Plzeňský kraj','cz','CZ','CZ032')"
        )

        connection.execute(
            "INSERT INTO providers(id,name,provider_type) "
            "VALUES ('p','Provider','REGIONAL')"
        )
        connection.execute(
            "INSERT INTO programmes(id,provider_id,name,funding_origin) "
            "VALUES ('pr','p','Program','CZ_REGION')"
        )
        connection.execute(
            "INSERT INTO grant_calls("
            "id,programme_id,canonical_slug,current_status,current_title,"
            "first_seen_at,created_at,updated_at"
            ") VALUES ("
            "'g','pr','g','OPEN','Grant',"
            "'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z',"
            "'2026-01-01T00:00:00Z'"
            ")"
        )
        connection.execute(
            "INSERT INTO grant_call_versions("
            "id,grant_call_id,version_number,captured_at,title,status,"
            "verification_status,created_at"
            ") VALUES ("
            "'v','g',1,'2026-01-01T00:00:00Z','Grant','OPEN',"
            "'VERIFIED','2026-01-01T00:00:00Z'"
            ")"
        )
        connection.execute(
            "INSERT INTO grant_geographies("
            "id,grant_call_version_id,geography_id,mode,applies_to"
            ") VALUES ('gg','v','plk','INCLUDE','PROJECT_LOCATION')"
        )

        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO grant_geographies("
                "id,grant_call_version_id,geography_id,mode,applies_to"
                ") VALUES ('bad','v','plk','MAYBE','PROJECT_LOCATION')"
            )

    def test_applicant_type_hierarchy_and_profile_references(self):
        connection = self.migrate_all()
        connection.execute(
            "INSERT INTO geographies(id,geography_type,name,country_code) "
            "VALUES ('cz','COUNTRY','Česko','CZ')"
        )
        connection.execute(
            "INSERT INTO applicant_types(id,code,name_cs,active) "
            "VALUES ('nonprofit','NONPROFIT','Nezisková organizace',1)"
        )
        connection.execute(
            "INSERT INTO applicant_types("
            "id,code,name_cs,parent_id,active"
            ") VALUES ("
            "'sports','SPORTS_CLUB','Sportovní klub','nonprofit',1"
            ")"
        )
        connection.execute(
            "INSERT INTO applicant_profiles("
            "id,applicant_type,applicant_type_id,seat_geography_id,"
            "created_at,updated_at"
            ") VALUES ("
            "'a','SPORTS_CLUB','sports','cz',"
            "'2026-09-25T00:00:00Z','2026-09-25T00:00:00Z'"
            ")"
        )
        row = connection.execute(
            "SELECT applicant_type, applicant_type_id, seat_geography_id "
            "FROM applicant_profiles WHERE id='a'"
        ).fetchone()
        self.assertEqual(row, ("SPORTS_CLUB", "sports", "cz"))

    def test_legacy_dynamic_attributes_are_preserved_and_enriched(self):
        connection = self.migrate_before_target()
        connection.execute(
            "INSERT INTO applicant_profiles("
            "id,applicant_type,created_at,updated_at"
            ") VALUES ("
            "'a','SPORTS_CLUB','2026-09-25T00:00:00Z',"
            "'2026-09-25T00:00:00Z'"
            ")"
        )
        connection.execute(
            "INSERT INTO attribute_definitions("
            "id,attribute_key,scope,label_cs,data_type,filterable,indexable"
            ") VALUES ("
            "'lease','applicant.lease_years','APPLICANT','Délka nájmu',"
            "'INTEGER',1,1"
            ")"
        )
        connection.execute(
            "INSERT INTO applicant_attribute_values("
            "id,applicant_profile_id,attribute_definition_id,value_json,"
            "source_kind,observed_at"
            ") VALUES ("
            "'av','a','lease','10','USER','2026-09-25T00:00:00Z'"
            ")"
        )

        connection.executescript(self.target.read_text(encoding="utf-8"))

        row = connection.execute(
            "SELECT value_type,value_json,source_kind,verification_status "
            "FROM applicant_attribute_values WHERE id='av'"
        ).fetchone()
        self.assertEqual(row, ("INTEGER", "10", "USER", "USER_DECLARED"))

        connection.execute(
            "INSERT INTO applicant_attribute_values("
            "id,applicant_profile_id,attribute_definition_id,value_type,"
            "value_json,source_kind,observed_at,verification_status"
            ") VALUES (?,?,?,?,?,?,?,?)",
            (
                "derived",
                "a",
                "attr-applicant-size",
                "ENUM",
                json.dumps("SMALL"),
                "DERIVED",
                "2026-09-25T01:00:00Z",
                "AUTO_EXTRACTED",
            ),
        )

    def test_expected_indexes_exist(self):
        connection = self.migrate_all()
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        for name in {
            "idx_geographies_parent",
            "idx_grant_geographies_version",
            "idx_applicant_types_parent",
            "idx_applicant_profiles_type_id",
            "idx_applicant_attribute_definition",
        }:
            self.assertIn(name, indexes)


if __name__ == "__main__":
    unittest.main()
