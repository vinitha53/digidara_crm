import hashlib
import hmac
import importlib.util
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class FakeResponse:
    status = 201
    content = True

    @staticmethod
    def read():
        return b'{"created":1,"updated":0}'


class FakeConnection:
    last = None

    def __init__(self, host, port=None, timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.request_args = None
        FakeConnection.last = self

    def request(self, method, path, body=None, headers=None):
        self.request_args = (method, path, body, headers)

    @staticmethod
    def getresponse():
        return FakeResponse()

    @staticmethod
    def close():
        return None


class WhatsAppBotCRMIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("OPENAI_API_KEY", "")
        sys.modules.setdefault("schedule", types.ModuleType("schedule"))
        bot_path = Path(__file__).resolve().parents[2] / "bot_updated.py"
        spec = importlib.util.spec_from_file_location("whatsapp_bot_for_test", bot_path)
        cls.bot = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.bot)

    def setUp(self):
        self.bot.CRM_API_URL = "https://crm.example.com/api/integrations/leads"
        self.bot.CRM_INTEGRATION_API_KEY = "test-api-key"
        self.bot.CRM_INTEGRATION_SIGNING_SECRET = "test-signing-secret"
        self.bot.CRM_PUSH_RETRY_COUNT = 1

    def test_signed_push_sends_summary_and_leaves_classification_to_crm(self):
        with patch.object(self.bot.http.client, "HTTPSConnection", FakeConnection):
            result = self.bot.push_lead_to_crm(
                phone="+91 98765 43210",
                name="Priya",
                text="Please call me today",
                notes="Main enquiry: GenAI course\nRequested action: Call today",
            )

        self.assertTrue(result)
        method, path, body, headers = FakeConnection.last.request_args
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/api/integrations/leads")
        self.assertEqual(payload["external_id"], "whatsapp:919876543210")
        self.assertEqual(payload["source_system"], "whatsapp")
        self.assertIn("GenAI course", payload["notes"])
        self.assertNotIn("tag", payload)
        self.assertNotIn("lead_score", payload)
        self.assertNotIn("status", payload)
        expected_signature = hmac.new(
            self.bot.CRM_INTEGRATION_SIGNING_SECRET.encode("utf-8"),
            headers["X-CRM-Timestamp"].encode("utf-8") + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(headers["X-CRM-Signature"], expected_signature)

    def test_crm_notes_use_llm_summary_and_include_latest_message(self):
        transcript = "[User 10:00] Share the fees\n[Bot 10:01] Our team can help\n[User 10:02] Call me today"
        generated = "Main enquiry: GenAI fees\nLatest customer message: Call me today"
        with patch.object(self.bot, "ask_llm_summary", return_value=generated) as summarize:
            notes = self.bot.crm_conversation_notes("Priya", transcript)

        self.assertEqual(notes, generated)
        self.assertEqual(self.bot.latest_customer_message(transcript), "Call me today")
        self.assertIn("Do not classify the lead", summarize.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
