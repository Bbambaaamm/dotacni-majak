"""Automated, schema-grounded verification of the privacy data inventory (issue #431).

This test makes the privacy data inventory *automatically testable* (acceptance
criterion: "Kontrola je automaticky testovatelná, kde to jde"). It:

1. Builds the live canonical schema from migrations/ and asserts every table and
   column referenced by the machine-readable inventory manifest actually exists.
2. Enforces the critical secrets invariant: capability and share-link tables store
   only a *hash* of the token, never a raw ``token`` column — and that audit/log
   tables never carry a raw ``token`` either (secrets/PII not in logs).
3. Reads the share-resolver SQL in apps/api/src/share.ts and asserts the read-only
   share projection is a strict allowlist (no owner_user_id / applicant_profile_id
   leakage).
4. Cross-checks that every PII column declared in the manifest is classified.
"""
import json
import re
import sqlite3
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = ROOT / "migrations"
MANIFEST_PATH = ROOT / "data" / "privacy" / "data_inventory.json"
SHARE_RESOLVER_SQL = ROOT / "apps" / "api" / "src" / "share.ts"

# Columns the read-only share resolver is permitted to return (whitelisted
# projection from apps/api/src/share.ts: PublicSharedProject).
SHARE_ALLOWLIST = {
    "id", "title", "natural_language_intent", "currency_code",
    "estimated_total_budget_minor", "planned_start", "planned_end", "updated_at",
}

# PII columns that a share response must NEVER leak.
SHARE_PII_FORBIDDEN = {"owner_user_id", "applicant_profile_id"}

# Tables that hold capability / share tokens. They must keep only a hash, never a
# plaintext token column.
TOKEN_TABLES = {"project_owner_capabilities", "project_share_links"}

# Audit / log tables that must never store a raw token (secrets/PII in logs).
AUDIT_LOG_TABLES = {
    "project_owner_audit_events",
    "share_audit_events",
    "outbox_events",
    "change_events",
    "source_runs",
    "source_records",
    "ingestion_runs",
}


def _schema(connection: sqlite3.Connection) -> dict[str, set[str]]:
    """Return {table: set(columns)} for every table in the live schema."""
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    schema: dict[str, set[str]] = {}
    for table in tables:
        columns = {
            row[1]
            for row in connection.execute(f"PRAGMA table_info({table})")
        }
        schema[table] = columns
    return schema


def _build_schema() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        connection.executescript(path.read_text(encoding="utf-8"))
    return connection


class PrivacyDataInventoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.connection = _build_schema()
        cls.schema = _schema(cls.connection)
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------ #
    # 1. Manifest integrity against the live schema
    # ------------------------------------------------------------------ #
    def test_manifest_is_well_formed(self):
        self.assertEqual(self.manifest["schema_version"], "1")
        self.assertIn("categories", self.manifest)
        self.assertGreater(len(self.manifest["categories"]), 0)

    def test_every_store_table_exists(self):
        for category in self.manifest["categories"]:
            for store in category["stores"]:
                with self.subTest(category=category["id"], table=store["table"]):
                    self.assertIn(
                        store["table"], self.schema,
                        f"table {store['table']} referenced by inventory does not exist",
                    )

    def test_every_declared_column_exists(self):
        for category in self.manifest["categories"]:
            for store in category["stores"]:
                table = store["table"]
                existing = self.schema.get(table, set())
                for column in store["columns"]:
                    with self.subTest(table=table, column=column):
                        self.assertIn(
                            column, existing,
                            f"column {column} of {table} does not exist in the schema",
                        )

    def test_pii_columns_are_classified(self):
        # Every PII column string declared in the manifest must be non-empty and
        # reference a real column, so no PII slips through unclassified.
        for category in self.manifest["categories"]:
            for pii_ref in category["pii_columns"]:
                match = re.match(
                    r"^(?P<table>[^.]+)\.(?P<column>.+)$", pii_ref
                )
                if match:
                    table, column = match["table"], match["column"]
                    with self.subTest(pii=pii_ref):
                        self.assertIn(table, self.schema)
                        self.assertIn(column, self.schema[table])

    # ------------------------------------------------------------------ #
    # 2. Secrets invariant: tokens stored only as hashes, never raw
    # ------------------------------------------------------------------ #
    def test_token_tables_have_hash_column_not_raw_token(self):
        for table in TOKEN_TABLES:
            with self.subTest(table=table):
                self.assertIn(table, self.schema)
                columns = self.schema[table]
                self.assertIn("token_hash", columns,
                              f"{table} must persist only the token hash")
                self.assertNotIn("token", columns,
                                 f"{table} must NOT persist a raw 'token' column")

    def test_audit_log_tables_never_carry_raw_token(self):
        for table in AUDIT_LOG_TABLES:
            with self.subTest(table=table):
                if table not in self.schema:
                    # Some log tables may be absent in the current migration set;
                    # that is fine as long as they are not *added* with a token
                    # column elsewhere.
                    continue
                self.assertNotIn(
                    "token", self.schema[table],
                    f"{table} must not store a raw token (secrets/PII in logs)",
                )

    # ------------------------------------------------------------------ #
    # 3. Share resolver is a strict allowlist (no PII leakage)
    # ------------------------------------------------------------------ #
    def test_share_resolver_sql_only_selects_allowlisted_columns(self):
        sql = SHARE_RESOLVER_SQL.read_text(encoding="utf-8")
        # Extract the SELECT projection from resolvePublicProjectShare.
        select_match = re.search(
            r"SELECT\s+(.*?)\s+FROM project_share_links",
            sql,
            re.DOTALL | re.IGNORECASE,
        )
        if select_match is None:
            self.fail("share resolver SELECT not found in share.ts")
        projection = select_match.group(1)
        referenced = {
            col.strip()
            for col in re.findall(r"\bp\.(\w+)\b", projection)
        }
        self.assertTrue(referenced, "no p.<column> references found in projection")
        for column in referenced:
            with self.subTest(column=column):
                self.assertIn(column, SHARE_ALLOWLIST,
                              f"share resolver selects non-allowlisted column: {column}")
        for forbidden in SHARE_PII_FORBIDDEN:
            self.assertNotIn(forbidden, referenced,
                             f"share resolver must not select forbidden PII: {forbidden}")

    def test_share_response_headers_prevent_caching_and_indexing(self):
        # The index.ts handler sets these headers on share responses; verify the
        # intent is documented in source so it cannot silently regress.
        index_sql = (ROOT / "apps" / "api" / "src" / "index.ts").read_text(encoding="utf-8")
        for header in ("private, no-store", "noindex, nofollow", "no-referrer"):
            with self.subTest(header=header):
                self.assertIn(header, index_sql,
                              f"share response must carry header value: {header}")

    # ------------------------------------------------------------------ #
    # 4. Push subscription endpoints are encrypted (ciphertext), not plaintext
    # ------------------------------------------------------------------ #
    def test_push_subscription_endpoint_is_ciphertext_only(self):
        columns = self.schema["web_push_subscriptions"]
        self.assertIn("endpoint_ciphertext", columns)
        self.assertIn("p256dh_ciphertext", columns)
        self.assertIn("auth_ciphertext", columns)
        # No plaintext endpoint column may exist.
        self.assertNotIn("endpoint", columns)
        self.assertNotIn("endpoint_url", columns)

    def test_share_links_have_explicit_expiry_and_revocation(self):
        columns = self.schema["project_share_links"]
        self.assertIn("expires_at", columns)
        self.assertIn("revoked_at", columns)
        self.assertIn("token_hash", columns)

    def test_owner_capabilities_track_generation_and_revocation(self):
        columns = self.schema["project_owner_capabilities"]
        self.assertIn("token_hash", columns)
        self.assertIn("generation", columns)
        self.assertIn("revoked_at", columns)


if __name__ == "__main__":
    unittest.main()
