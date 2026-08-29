from pathlib import Path
import re
import unittest

from extensions import db
import models  # noqa: F401 - registers every SQLAlchemy table in db.metadata
from permissions import PERMISSION_PAGES, default_allowed


class SchemaContractTestCase(unittest.TestCase):
    def test_recent_feature_schema_is_complete(self):
        schema = (Path(__file__).resolve().parents[1] / "schema.sql").read_text(encoding="utf-8")
        expected_fragments = [
            "CREATE TABLE IF NOT EXISTS login_otp_challenges",
            "send_attempts SMALLINT UNSIGNED NOT NULL DEFAULT 0",
            "delivery_status VARCHAR(20) NOT NULL DEFAULT 'pending'",
            "meta_message_id VARCHAR(190) NULL",
            "KEY idx_login_otp_delivery (delivery_status, created_at)",
            "otp_enabled     TINYINT(1) NOT NULL DEFAULT 1",
            "SET phone = '+916369979579', otp_enabled = 1",
            "CREATE TABLE IF NOT EXISTS integrations",
            "UNIQUE KEY uq_integrations_agency_type (agency_id, type)",
            "'login_otp_template', 'staff_login_otp'",
            "'sender_number', '957554507448611'",
            "conversation_id VARCHAR(64) NULL",
            "conversation_title VARCHAR(160) NULL",
            "KEY idx_ai_interactions_conversation (user_id, conversation_id, created_at)",
            "SET conversation_id = CONCAT('legacy-', id)",
            "CALL add_column_if_missing('ai_interactions', 'model', 'VARCHAR(100) NULL')",
            "CALL add_column_if_missing('ai_interactions', 'status', 'VARCHAR(30) NOT NULL DEFAULT ''success''')",
            "CALL add_column_if_missing('ai_interactions', 'sources', 'VARCHAR(255) NULL')",
        ]
        for fragment in expected_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, schema)

    def test_schema_rerun_does_not_replace_legacy_integration_secrets(self):
        schema = (Path(__file__).resolve().parents[1] / "schema.sql").read_text(encoding="utf-8")
        company_seed = schema.split("INSERT INTO company_settings", 1)[1]
        duplicate_update = company_seed.split("ON DUPLICATE KEY UPDATE", 1)[1].split(";", 1)[0]
        for secret_field in (
            "google_review_api_key",
            "whatsapp_api_token",
            "whatsapp_phone_number_id",
            "gmail_app_password",
        ):
            with self.subTest(secret_field=secret_field):
                self.assertNotIn(f"{secret_field} = VALUES({secret_field})", duplicate_update)

    def test_every_model_table_and_column_exists_in_schema(self):
        schema = (Path(__file__).resolve().parents[1] / "schema.sql").read_text(encoding="utf-8")
        definitions = {
            match.group(1): match.group(2)
            for match in re.finditer(
                r"^CREATE TABLE IF NOT EXISTS\s+`?([a-z_]+)`?\s*\((.*?)^\) ENGINE=",
                schema,
                re.MULTILINE | re.DOTALL,
            )
        }

        for table in db.metadata.sorted_tables:
            with self.subTest(table=table.name):
                self.assertIn(table.name, definitions)
                schema_columns = {
                    match.group(1)
                    for line in definitions[table.name].splitlines()
                    if (match := re.match(r"\s*`?([a-z_][a-z0-9_]*)`?\s+[A-Z]", line))
                }
                self.assertEqual(set(table.columns.keys()) - schema_columns, set())

    def test_permission_seed_matches_current_permission_matrix(self):
        schema = (Path(__file__).resolve().parents[1] / "schema.sql").read_text(encoding="utf-8")
        seed = schema.split("INSERT IGNORE INTO role_permissions (role, page_key, action, allowed)", 1)[1].split(";", 1)[0]
        actual = {
            (role, page, action): value == "1"
            for role, page, action, value in re.findall(
                r"\('(admin|staff)',\s*'([^']+)',\s*'([^']+)',\s*([01])\)",
                seed,
            )
        }
        expected = {
            (role, page["key"], action): default_allowed(role, page["key"], action)
            for role in ("admin", "staff")
            for page in PERMISSION_PAGES
            for action in page["actions"]
        }

        self.assertEqual(actual, expected)
        self.assertNotIn("'support'", seed)


if __name__ == "__main__":
    unittest.main()
