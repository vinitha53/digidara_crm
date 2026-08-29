import os
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["DIGIDARA_SKIP_AUTO_APP"] = "1"
os.environ["SECRET_KEY"] = "test-source-ingestion-secret-over-32-bytes"
os.environ["JWT_SECRET_KEY"] = "test-source-ingestion-jwt-over-32-bytes"

from app import create_app
from extensions import db
from models import Lead
from routes.communication import upsert_whatsapp_lead


class LeadSourceIngestionTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(
            TESTING=True,
            GROQ_API_KEY="",
            AI_FOLLOWUP_TEST_MODE=True,
            AI_FOLLOWUP_TEST_HOT_MINUTES=3,
            AI_FOLLOWUP_TEST_WARM_MINUTES=5,
            AI_FOLLOWUP_TEST_COLD_MINUTES=7,
        )
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    @patch("services.lead_scoring_service.classify_lead")
    def test_whatsapp_sync_refreshes_latest_notes_rescores_and_deduplicates(self, classify):
        classify.side_effect = [
            {
                "tag": "warm", "score": 61, "reason": "Asked for course details.",
                "factors": "Course interest", "next_best_action": "Send course details.",
            },
            {
                "tag": "hot", "score": 94, "reason": "Requested an immediate call.",
                "factors": "Immediate callback", "next_best_action": "Call now.",
            },
        ]
        first_row = {
            "phone": "+91 98765 43210",
            "name": "Priya",
            "chat_date": date(2026, 8, 28),
            "conversation": "[User 10:00] Please share the AI course details\n[Bot 10:01] Certainly",
            "created_at": datetime(2026, 8, 28, 10, 0),
        }
        second_row = {
            **first_row,
            "conversation": "[User 10:00] Please share the AI course details\n[User 10:05] I will join today. Call me immediately with the price",
            "updated_at": datetime(2026, 8, 28, 10, 5),
        }

        first, first_result = upsert_whatsapp_lead(first_row, actor_id=None)
        db.session.commit()
        second, second_result = upsert_whatsapp_lead(second_row, actor_id=None)
        db.session.commit()

        self.assertEqual(first_result, "created")
        self.assertEqual(second_result, "updated")
        self.assertEqual(first.id, second.id)
        self.assertEqual(Lead.query.count(), 1)
        self.assertEqual(second.tag, "hot")
        self.assertEqual(second.ai_score, 94)
        self.assertEqual(second.notes, "Latest WhatsApp message: I will join today. Call me immediately with the price")
        expected = datetime.utcnow() + timedelta(minutes=3)
        self.assertLess(abs((second.ai_next_followup_at - expected).total_seconds()), 5)
        self.assertEqual(classify.call_count, 2)
        self.assertEqual(classify.call_args.args[0].notes, second.notes)


if __name__ == "__main__":
    unittest.main()
