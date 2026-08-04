from pathlib import Path
import unittest


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


if __name__ == "__main__":
    unittest.main()
