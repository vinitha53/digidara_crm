import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["DIGIDARA_SKIP_AUTO_APP"] = "1"
os.environ["SECRET_KEY"] = "test-followup-sequence-secret-key"
os.environ["JWT_SECRET_KEY"] = "test-followup-sequence-jwt-key"

from flask_jwt_extended import create_access_token

from app import create_app
from extensions import db
from models import AIFollowUpHistory, CompanySettings, Lead, MessageLog, User
from routes.ai_followups import generate_for_lead, process_due_followups, send_history
from services.ai_followup_schedule_service import schedule_next_followup
from services.ai_followup_service import next_sequence_step, seed_sequence_templates


class AIFollowUpSequenceTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True, GROQ_API_KEY="", AI_FOLLOWUP_TEST_MODE=False)
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.admin = User(name="Admin", email="followup-admin@example.com", role="admin", is_active=1)
        self.staff = User(name="Owner", email="followup-owner@example.com", role="staff", is_active=1)
        self.admin.set_password("Password@123")
        self.staff.set_password("Password@123")
        db.session.add_all([self.admin, self.staff])
        db.session.flush()
        self.settings = CompanySettings(id=1, ai_followups_enabled=True, ai_followup_max_count=10, ai_followup_stop_after_no_response=0)
        db.session.add(self.settings)
        seed_sequence_templates()
        db.session.commit()
        self.client = self.app.test_client()
        self.admin_headers = {"Authorization": f"Bearer {create_access_token(identity=str(self.admin.id))}"}

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def lead(self, temperature="hot", **values):
        row = Lead(name=f"{temperature.title()} Lead", phone="9876543210", service="AI Course", tag=temperature, status="new", assigned_to=self.staff.id, ai_followup_enabled=True, **values)
        db.session.add(row)
        db.session.commit()
        return row

    def successful(self, lead, step):
        row = AIFollowUpHistory(lead_id=lead.id, status="sent", delivery_status="accepted", sequence_step=step, temperature_snapshot=lead.tag, idempotency_key=f"success:{lead.id}:{step}")
        db.session.add(row)
        db.session.commit()
        return row

    def test_hot_and_warm_sequences_progress_from_one_to_ten_never_eleven(self):
        for temperature in ("hot", "warm"):
            lead = self.lead(temperature)
            self.assertEqual(next_sequence_step(lead), 1)
            for step in range(1, 11):
                self.assertEqual(next_sequence_step(lead), step)
                self.successful(lead, step)
            self.assertEqual(next_sequence_step(lead), 11)
            lead.ai_followup_count = 10
            lead.ai_next_followup_at = datetime.utcnow() - timedelta(minutes=1)
            db.session.commit()
            result = process_due_followups()
            self.assertEqual(result["sent"], 0)
            self.assertFalse(lead.ai_followup_enabled)
            self.assertEqual(lead.ai_followup_stop_reason, "Sequence completed")

    def test_failed_and_skipped_records_do_not_advance_sequence(self):
        lead = self.lead()
        db.session.add_all([
            AIFollowUpHistory(lead_id=lead.id, status="failed", sequence_step=1, temperature_snapshot="hot", idempotency_key="failed-step"),
            AIFollowUpHistory(lead_id=lead.id, status="skipped", sequence_step=1, temperature_snapshot="hot", idempotency_key="skipped-step"),
        ])
        db.session.commit()
        self.assertEqual(next_sequence_step(lead), 1)

    def test_exact_recipient_final_edit_and_provider_id_are_persisted(self):
        lead = self.lead()
        history = generate_for_lead(lead, self.settings)
        db.session.commit()
        result = {"ok": True, "data": {"messages": [{"id": "wamid.followup-1"}]}, "recipient_phone": "919876543210", "transport": "template", "template_name": "ai-template"}
        with patch("routes.ai_followups.send_whatsapp_template", return_value=result):
            send_history(history, "Exact edited final message", self.admin.id)
            db.session.commit()
        self.assertEqual(history.final_message, "Exact edited final message")
        self.assertEqual(history.recipient_phone, "919876543210")
        self.assertEqual(history.provider_message_id, "wamid.followup-1")
        self.assertEqual(history.delivery_status, "accepted")
        log = MessageLog.query.filter_by(followup_id=history.id).one()
        self.assertEqual(log.message_body, "Exact edited final message")
        self.assertEqual(log.provider_message_id, "wamid.followup-1")

    def test_whatsapp_failure_is_failed_and_does_not_advance(self):
        lead = self.lead()
        history = generate_for_lead(lead, self.settings)
        db.session.commit()
        failed = {"ok": False, "error": "provider unavailable", "recipient_phone": "919876543210"}
        with patch("routes.ai_followups.send_whatsapp_template", return_value=failed), patch("routes.ai_followups.send_whatsapp", return_value=failed):
            send_history(history, actor_id=self.admin.id)
            db.session.commit()
        self.assertEqual(history.status, "failed")
        self.assertEqual(history.delivery_status, "failed")
        self.assertEqual(next_sequence_step(lead), 1)

    def test_duplicate_scheduler_run_does_not_send_same_step_twice(self):
        lead = self.lead(ai_next_followup_at=datetime.utcnow() - timedelta(minutes=1))
        accepted = {"ok": True, "data": {"messages": [{"id": "wamid.once"}]}, "recipient_phone": "919876543210"}
        with patch("routes.ai_followups.send_whatsapp_template", return_value=accepted) as sender:
            first = process_due_followups()
            second = process_due_followups()
        self.assertEqual(first["sent"], 1)
        self.assertEqual(second["sent"], 0)
        self.assertEqual(sender.call_count, 1)

    def test_business_hours_and_working_days_are_honored(self):
        lead = self.lead("hot")
        self.settings.ai_followup_hot_interval_days = 2
        self.settings.ai_followup_business_hours = "09:00-18:00"
        self.settings.ai_followup_working_days = "Mon,Tue,Wed,Thu,Fri"
        friday_evening = datetime(2026, 9, 4, 19, 30)
        scheduled = schedule_next_followup(lead, self.settings, friday_evening)
        self.assertEqual(scheduled, datetime(2026, 9, 7, 9, 0))

    @patch("routes.leads.send_customer_welcome")
    def test_won_lead_immediately_stops_and_reopen_does_not_resume(self, _welcome):
        lead = self.lead(ai_next_followup_at=datetime.utcnow())
        response = self.client.put(f"/api/leads/{lead.id}", json={"status": "won"}, headers=self.admin_headers)
        self.assertEqual(response.status_code, 200)
        db.session.refresh(lead)
        self.assertFalse(lead.ai_followup_enabled)
        self.assertIsNone(lead.ai_next_followup_at)
        reopen = self.client.put(f"/api/leads/{lead.id}", json={"status": "contacted"}, headers=self.admin_headers)
        self.assertEqual(reopen.status_code, 200)
        db.session.refresh(lead)
        self.assertFalse(lead.ai_followup_enabled)

    def test_lost_lead_stops_and_pending_message_is_cancelled(self):
        lead = self.lead(ai_next_followup_at=datetime.utcnow())
        pending = generate_for_lead(lead, self.settings)
        db.session.commit()
        response = self.client.put(f"/api/leads/{lead.id}", json={"status": "lost", "lost_reason": "No longer interested"}, headers=self.admin_headers)
        self.assertEqual(response.status_code, 200)
        db.session.refresh(pending)
        self.assertEqual(pending.status, "cancelled")
        self.assertFalse(lead.ai_followup_enabled)

    def test_no_phone_lead_is_visibly_skipped(self):
        lead = self.lead()
        lead.phone = ""
        history = generate_for_lead(lead, self.settings)
        db.session.commit()
        send_history(history, actor_id=self.admin.id)
        db.session.commit()
        self.assertEqual(history.status, "skipped")
        self.assertIn("Recipient phone number", history.provider_error)


if __name__ == "__main__":
    unittest.main()
