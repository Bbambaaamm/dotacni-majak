import json
import sqlite3
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class EligibilityDslSchemaTest(unittest.TestCase):
    def test_safe_operator_set_has_no_eval_operator(self):
        payload = json.loads(
            (ROOT / "schemas" / "v1" / "rule-condition.schema.json")
            .read_text(encoding="utf-8")
        )
        operators = set(payload["properties"]["operator"]["enum"])
        self.assertIn("LTE", operators)
        self.assertIn("GEO_WITHIN", operators)
        self.assertNotIn("EVAL", operators)
        self.assertNotIn("SCRIPT", operators)

    def test_unknown_policy_cannot_turn_missing_data_into_fail(self):
        payload = json.loads(
            (ROOT / "schemas" / "v1" / "rule-condition.schema.json")
            .read_text(encoding="utf-8")
        )
        policies = set(payload["properties"]["unknownPolicy"]["enum"])
        self.assertEqual(policies, {"PROPAGATE", "NOT_APPLICABLE"})


class EligibilityDslMigrationTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.execute("PRAGMA foreign_keys = ON")
        for path in sorted((ROOT / "migrations").glob("*.sql")):
            self.connection.executescript(path.read_text(encoding="utf-8"))

        self.connection.execute(
            "INSERT INTO providers(id,name,provider_type) "
            "VALUES ('p','Provider','NATIONAL')"
        )
        self.connection.execute(
            "INSERT INTO programmes(id,provider_id,name,funding_origin) "
            "VALUES ('pr','p','Programme','CZ_NATIONAL')"
        )
        self.connection.execute(
            "INSERT INTO grant_calls("
            "id,programme_id,canonical_slug,current_status,current_title,"
            "first_seen_at,created_at,updated_at"
            ") VALUES ("
            "'g','pr','grant','OPEN','Grant',"
            "'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z',"
            "'2026-01-01T00:00:00Z'"
            ")"
        )
        self.connection.execute(
            "INSERT INTO grant_call_versions("
            "id,grant_call_id,version_number,captured_at,title,status,"
            "verification_status,created_at"
            ") VALUES ("
            "'v','g',1,'2026-01-01T00:00:00Z','Grant','OPEN',"
            "'VERIFIED','2026-01-01T00:00:00Z'"
            ")"
        )

    def tearDown(self):
        self.connection.close()

    def test_only_one_root_group_per_rule_set(self):
        self.connection.execute(
            "INSERT INTO eligibility_rule_sets("
            "id,grant_call_version_id,name,completeness_status,verification_status"
            ") VALUES ('rs','v','Eligibility','COMPLETE','VERIFIED')"
        )
        self.connection.execute(
            "INSERT INTO rule_groups(id,rule_set_id,group_operator) "
            "VALUES ('root1','rs','AND')"
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                "INSERT INTO rule_groups(id,rule_set_id,group_operator) "
                "VALUES ('root2','rs','OR')"
            )

    def test_attribute_scope_must_match_key_prefix(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                "INSERT INTO attribute_definitions("
                "id,attribute_key,scope,label_cs,data_type"
                ") VALUES ("
                "'a','project.total_budget','APPLICANT','Rozpočet','MONEY_MINOR'"
                ")"
            )

    def test_unknown_fail_policy_is_rejected_by_database(self):
        self.connection.execute(
            "INSERT INTO attribute_definitions("
            "id,attribute_key,scope,label_cs,data_type"
            ") VALUES ("
            "'a','applicant.population','APPLICANT','Počet obyvatel','INTEGER'"
            ")"
        )
        self.connection.execute(
            "INSERT INTO eligibility_rule_sets("
            "id,grant_call_version_id,name,completeness_status,verification_status"
            ") VALUES ('rs','v','Eligibility','COMPLETE','VERIFIED')"
        )
        self.connection.execute(
            "INSERT INTO rule_groups(id,rule_set_id,group_operator) "
            "VALUES ('root','rs','AND')"
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                "INSERT INTO rule_conditions("
                "id,rule_group_id,attribute_definition_id,condition_operator,"
                "expected_value_json,unknown_policy,verification_status"
                ") VALUES ("
                "'c','root','a','LTE','5000','FAIL','VERIFIED'"
                ")"
            )


if __name__ == "__main__":
    unittest.main()
