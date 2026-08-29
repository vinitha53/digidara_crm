import hashlib
import hmac
import json
import os
import time
import unittest
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["DIGIDARA_SKIP_AUTO_APP"] = "1"
os.environ["SECRET_KEY"] = "test-google-form-secret-key-over-32-bytes"
os.environ["JWT_SECRET_KEY"] = "test-google-form-jwt-key-over-32-bytes"

from app import create_app
from extensions import db
from models import Lead


class GoogleFormLeadIntegrationTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(
            TESTING=True,
            CRM_INTEGRATION_API_KEY="form-api-key",
            CRM_INTEGRATION_SIGNING_SECRET="form-signing-secret",
            INTEGRATION_ALLOWED_SOURCES=["google_form", "website", "chatbot", "whatsapp"],
            GROQ_API_KEY="",
        )
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def signed_headers(self, body):
        timestamp = str(int(time.time()))
        signature = hmac.new(
            self.app.config["CRM_INTEGRATION_SIGNING_SECRET"].encode(),
            timestamp.encode() + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        return {
            "Content-Type": "application/json",
            "X-CRM-API-Key": self.app.config["CRM_INTEGRATION_API_KEY"],
            "X-CRM-Timestamp": timestamp,
            "X-CRM-Signature": signature,
        }

    def post(self, payload):
        body = json.dumps(payload, separators=(",", ":")).encode()
        return self.client.post(
            "/api/integrations/leads",
            data=body,
            headers=self.signed_headers(body),
        )

    @patch("routes.integrations.send_lead_acknowledgement")
    def test_google_form_submission_creates_a_website_lead(self, acknowledgement):
        response = self.post({
            "source_system": "google_form",
            "source": "website",
            "external_id": "google-form:sheet-1:row-2",
            "external_created_at": "2026-08-25T10:30:00Z",
            "name": "Priya",
            "phone": "9876543210",
            "email": "priya@example.com",
            "lead_category": "course",
            "course_name": "GenAI Course",
            "qualification": "BSc",
            "city": "Trichy",
            "notes": "Requested weekend batch details",
        })

        self.assertEqual(response.status_code, 201)
        lead = Lead.query.one()
        self.assertEqual(lead.source_system, "google_form")
        self.assertEqual(lead.source, "website")
        self.assertEqual(lead.external_id, "google-form:sheet-1:row-2")
        self.assertEqual(lead.course_name, "GenAI Course")
        self.assertEqual(lead.notes, "Requested weekend batch details")
        self.assertEqual(lead.tag, "warm")
        self.assertIsNotNone(lead.ai_scored_at)
        acknowledgement.assert_called_once()

    @patch("services.lead_scoring_service.classify_lead")
    @patch("routes.integrations.send_lead_acknowledgement")
    def test_chatbot_notes_are_classified_and_stored(self, acknowledgement, classify):
        classify.return_value = {
            "tag": "hot",
            "score": 91,
            "reason": "The visitor requested an immediate callback.",
            "factors": ["Urgent callback request", "Pricing intent"],
            "next_best_action": "Call now and confirm the preferred batch.",
        }

        response = self.post({
            "source_system": "chatbot",
            "external_id": "chat-session-42",
            "name": "Anita",
            "phone": "9888877777",
            "message": "I want to join this week. Please call me now with the fee details.",
        })

        self.assertEqual(response.status_code, 201)
        lead = Lead.query.one()
        self.assertEqual(lead.source, "chatbot")
        self.assertEqual(lead.tag, "hot")
        self.assertEqual(lead.ai_score, 91)
        self.assertIn("Pricing intent", lead.ai_score_factors)
        self.assertEqual(lead.notes, "I want to join this week. Please call me now with the fee details.")
        self.assertEqual(classify.call_args.args[0].notes, lead.notes)
        acknowledgement.assert_called_once()

    @patch("routes.integrations.send_lead_acknowledgement")
    def test_retry_updates_same_lead_without_duplicate_or_second_acknowledgement(self, acknowledgement):
        payload = {
            "source_system": "google_form",
            "source": "website",
            "external_id": "google-form:sheet-1:row-2",
            "name": "Priya",
            "phone": "9876543210",
            "service": "Registration Enquiry",
            "notes": "Initial note",
        }
        first = self.post(payload)
        payload["notes"] = "Updated note"
        second = self.post(payload)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(Lead.query.count(), 1)
        lead = Lead.query.one()
        self.assertEqual(lead.notes, "Updated note")
        self.assertIn(lead.tag, {"hot", "warm", "cold"})
        acknowledgement.assert_called_once()

    def test_unsigned_google_form_submission_is_rejected(self):
        response = self.client.post(
            "/api/integrations/leads",
            json={"source_system": "google_form", "name": "Priya", "phone": "9876543210"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(Lead.query.count(), 0)


if __name__ == "__main__":
    unittest.main()
