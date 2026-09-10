import hashlib
import hmac
import json
import os
import time
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["DIGIDARA_SKIP_AUTO_APP"] = "1"
os.environ["SECRET_KEY"] = "test-campaign-secret-key-over-32-bytes"
os.environ["JWT_SECRET_KEY"] = "test-campaign-jwt-key-over-32-bytes"

from flask_jwt_extended import create_access_token

from app import create_app
from extensions import db
from models import Campaign, CampaignRecipient, Lead, MessageEvent, User, WhatsAppTemplate
from services.campaign_service import process_due_campaigns


class WhatsAppCampaignTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(
            TESTING=True, CRM_AGENCY_ID=2, CAMPAIGN_REQUIRE_MARKETING_CONSENT=True,
            CAMPAIGN_SEND_ENABLED=True, CAMPAIGN_DELAY_MS=0, CAMPAIGN_MAX_RETRIES=2,
            CRM_INTEGRATION_SIGNING_SECRET="campaign-forward-secret",
            WHATSAPP_ACCESS_TOKEN="test-token", WHATSAPP_PHONE_NUMBER_ID="phone-id",
        )
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.admin = User(name="Admin", email="admin@example.com", role="admin", branch="HQ", is_active=1)
        self.staff = User(name="Staff", email="staff@example.com", role="staff", branch="Chennai", is_active=1)
        self.other = User(name="Other", email="other@example.com", role="staff", branch="Madurai", is_active=1)
        for user in (self.admin, self.staff, self.other):
            user.set_password("Password@123")
            db.session.add(user)
        db.session.flush()
        self.hot = self.add_lead("Hot Lead", "9000000001", "hot", self.staff, marketing_opt_in=True)
        self.warm = self.add_lead("Warm Lead", "9000000002", "warm", self.staff, whatsapp_opt_in=True)
        self.cold = self.add_lead("Cold Lead", "9000000003", "cold", self.other, marketing_opt_in=True)
        self.opted = self.add_lead("Opted Out", "9000000004", "hot", self.staff, marketing_opt_in=True, opted_out=True)
        self.invalid = self.add_lead("No Phone", "bad", "hot", self.staff, marketing_opt_in=True)
        self.duplicate = self.add_lead("Duplicate", "+91 90000 00001", "warm", self.staff, marketing_opt_in=True)
        self.pending = self.add_lead("Pending Consent", "9000000006", "warm", self.staff)
        db.session.commit()
        self.headers = {"Authorization": f"Bearer {create_access_token(identity=str(self.admin.id))}"}
        self.staff_headers = {"Authorization": f"Bearer {create_access_token(identity=str(self.staff.id))}"}
        self.client = self.app.test_client()
        self.template = self.add_template()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def add_lead(self, name, phone, tag, owner, **values):
        lead = Lead(name=name, phone=phone, service="AI Course", course_name="AI Course", lead_category="course", tag=tag, status="new", source="website", assigned_to=owner.id, **values)
        db.session.add(lead)
        return lead

    def add_template(self, name="approved_offer", header_type="TEXT"):
        template = WhatsAppTemplate(
            agency_id=2, meta_template_id=f"meta-{name}", name=name, language="en", category="MARKETING", status="APPROVED",
            header_type=header_type, body_text="Hi {{1}}, explore {{2}}", footer_text="Reply STOP to opt out",
            components=[{"type": "HEADER", "format": header_type}, {"type": "BODY", "text": "Hi {{1}}, explore {{2}}"}], buttons=[],
        )
        db.session.add(template)
        db.session.commit()
        return template

    def campaign_payload(self, audience_type="hot", mapping=None, header_type="TEXT"):
        return {
            "name": "September Offer", "audience_type": audience_type,
            "audience_filter": {"classification": audience_type},
            "template_name": self.template.name, "template_language": "en", "template_category": "MARKETING",
            "template_snapshot": {"components": self.template.components}, "header_type": header_type,
            "message_body": self.template.body_text,
            "variable_mapping": {"body": mapping or {"1": {"field": "name"}, "2": {"field": "service"}}},
        }

    def create_campaign(self, **updates):
        payload = self.campaign_payload()
        payload.update(updates)
        response = self.client.post("/api/campaigns/", json=payload, headers=self.headers)
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        return Campaign.query.get(response.get_json()["id"])

    def test_audience_classification_and_suppression_counts(self):
        hot = self.client.get("/api/campaigns/audience?classification=hot", headers=self.headers).get_json()
        warm = self.client.get("/api/campaigns/audience?classification=warm", headers=self.headers).get_json()
        cold = self.client.get("/api/campaigns/audience?classification=cold", headers=self.headers).get_json()
        all_rows = self.client.get("/api/campaigns/audience?classification=all", headers=self.headers).get_json()

        self.assertEqual(hot["eligible_count"], 1)
        self.assertEqual(hot["exclusion_reasons"], {"invalid_or_missing_phone": 1, "opted_out": 1})
        self.assertEqual(warm["eligible_count"], 2)
        self.assertEqual(warm["exclusion_reasons"], {"consent_required": 1})
        self.assertEqual(cold["eligible_count"], 1)
        self.assertEqual(all_rows["eligible_count"], 3)
        self.assertEqual(all_rows["exclusion_reasons"]["duplicate_phone"], 1)

    def test_staff_audience_and_csv_export_are_assignment_scoped(self):
        response = self.client.get("/api/leads/export?classification=all", headers=self.staff_headers)
        # Staff has no campaign.export permission by default.
        self.assertEqual(response.status_code, 403)

        admin_export = self.client.get("/api/leads/export?classification=cold", headers=self.headers)
        self.assertEqual(admin_export.status_code, 200)
        self.assertIn("Cold Lead", admin_export.get_data(as_text=True))
        self.assertNotIn("Hot Lead", admin_export.get_data(as_text=True))
        response = self.client.get("/api/campaigns/audience?classification=all", headers=self.staff_headers)
        self.assertEqual(response.status_code, 403)

    @patch("routes.campaigns.fetch_approved_templates")
    def test_template_refresh_only_persists_approved_templates(self, fetch):
        fetch.return_value = {"ok": True, "templates": [{
            "id": "new-approved", "name": "new_offer", "language": "en_US", "category": "MARKETING", "status": "APPROVED",
            "components": [{"type": "BODY", "text": "Hello {{1}}"}],
        }], "paging": {}}
        response = self.client.post("/api/campaigns/templates/refresh", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["count"], 1)
        self.assertIsNotNone(WhatsAppTemplate.query.filter_by(meta_template_id="new-approved", status="APPROVED").first())

    def test_launch_snapshots_recipients_and_prevents_double_launch(self):
        campaign = self.create_campaign()
        response = self.client.post(f"/api/campaigns/{campaign.id}/launch", json={"confirmed": True}, headers=self.headers)
        again = self.client.post(f"/api/campaigns/{campaign.id}/launch", json={"confirmed": True}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(again.status_code, 409)
        self.assertEqual(CampaignRecipient.query.filter_by(campaign_id=campaign.id, status="queued").count(), 1)

    def test_missing_variable_is_skipped(self):
        self.hot.email = None
        db.session.commit()
        campaign = self.create_campaign(variable_mapping={"body": {"1": {"field": "name"}, "2": {"field": "email"}}})
        response = self.client.post(f"/api/campaigns/{campaign.id}/launch", json={"confirmed": True}, headers=self.headers)
        self.assertEqual(response.status_code, 400)
        self.assertIn("no eligible recipients", " ".join(response.get_json()["errors"]).lower())

    @patch("services.campaign_service.send_whatsapp_template")
    def test_worker_sends_real_template_and_updates_actual_counts(self, send):
        send.return_value = {"ok": True, "data": {"messages": [{"id": "wamid.campaign-1"}]}, "recipient_phone": "919000000001"}
        campaign = self.create_campaign()
        self.client.post(f"/api/campaigns/{campaign.id}/launch", json={"confirmed": True}, headers=self.headers)
        result = process_due_campaigns()
        db.session.refresh(campaign)
        recipient = CampaignRecipient.query.filter_by(campaign_id=campaign.id).first()
        self.assertEqual(result["processed"], 1)
        self.assertEqual(recipient.status, "accepted")
        self.assertEqual(recipient.provider_message_id, "wamid.campaign-1")
        self.assertEqual(campaign.sent_count, 1)
        self.assertEqual(campaign.opened_count, 0)
        send.assert_called_once()

    @patch("services.campaign_service.send_whatsapp_template")
    def test_image_header_campaign_sends_meta_media_id(self, send):
        self.template.header_type = "IMAGE"
        self.template.components = [{"type": "HEADER", "format": "IMAGE"}, {"type": "BODY", "text": "Hi {{1}}, explore {{2}}"}]
        db.session.commit()
        send.return_value = {"ok": True, "data": {"messages": [{"id": "wamid.image"}]}}
        campaign = self.create_campaign(
            header_type="IMAGE", media_id="meta-media-42",
            template_snapshot={"components": self.template.components},
        )
        self.client.post(f"/api/campaigns/{campaign.id}/launch", json={"confirmed": True}, headers=self.headers)
        process_due_campaigns()
        self.assertEqual(send.call_args.kwargs["header_media_id"], "meta-media-42")

    @patch("services.campaign_service.send_whatsapp_template")
    def test_transient_failure_retries_without_duplicate_provider_send(self, send):
        send.side_effect = [
            {"ok": False, "error": "rate limited", "error_code": "429", "transient": True},
            {"ok": True, "data": {"messages": [{"id": "wamid.retry"}]}, "recipient_phone": "919000000001"},
        ]
        campaign = self.create_campaign()
        self.client.post(f"/api/campaigns/{campaign.id}/launch", json={"confirmed": True}, headers=self.headers)
        process_due_campaigns()
        recipient = CampaignRecipient.query.filter_by(campaign_id=campaign.id).first()
        self.assertEqual(recipient.status, "retry")
        recipient.next_retry_at = datetime.utcnow() - timedelta(seconds=1)
        campaign.status = "queued"
        db.session.commit()
        process_due_campaigns()
        self.assertEqual(recipient.status, "accepted")
        self.assertEqual(recipient.retry_count, 1)
        self.assertEqual(send.call_count, 2)

    def test_pause_resume_cancel_lifecycle(self):
        campaign = self.create_campaign()
        self.client.post(f"/api/campaigns/{campaign.id}/launch", json={"confirmed": True}, headers=self.headers)
        self.assertEqual(self.client.post(f"/api/campaigns/{campaign.id}/pause", headers=self.headers).status_code, 200)
        self.assertEqual(self.client.post(f"/api/campaigns/{campaign.id}/resume", headers=self.headers).status_code, 200)
        self.assertEqual(self.client.post(f"/api/campaigns/{campaign.id}/cancel", headers=self.headers).status_code, 200)
        self.assertEqual(campaign.status, "cancelled")

    def signed_webhook(self, payload):
        body = json.dumps(payload, separators=(",", ":")).encode()
        timestamp = str(int(time.time()))
        signature = hmac.new(b"campaign-forward-secret", timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
        return self.client.post("/api/campaigns/webhook-events", data=body, headers={"Content-Type": "application/json", "X-CRM-Timestamp": timestamp, "X-CRM-Signature": signature})

    @patch("services.campaign_service.send_whatsapp_template")
    def test_webhook_tracks_delivery_read_reply_and_stop(self, send):
        send.return_value = {"ok": True, "data": {"messages": [{"id": "wamid.events"}]}}
        campaign = self.create_campaign()
        self.client.post(f"/api/campaigns/{campaign.id}/launch", json={"confirmed": True}, headers=self.headers)
        process_due_campaigns()
        for status in ("delivered", "read"):
            response = self.signed_webhook({"entry": [{"changes": [{"value": {"statuses": [{"id": "wamid.events", "status": status, "timestamp": "1789027200"}]}}]}]})
            self.assertEqual(response.status_code, 200)
        response = self.signed_webhook({"entry": [{"changes": [{"value": {"messages": [{"id": "wamid.reply", "from": "919000000001", "timestamp": "1789027300", "type": "text", "text": {"body": "STOP"}, "context": {"id": "wamid.events"}}]}}]}]})
        self.assertEqual(response.status_code, 200)
        recipient = CampaignRecipient.query.filter_by(provider_message_id="wamid.events").first()
        self.assertEqual(recipient.status, "opted_out")
        self.assertEqual(recipient.last_reply_text, "STOP")
        self.assertEqual(recipient.reply_count, 1)
        self.assertTrue(self.hot.opted_out)
        self.assertFalse(self.hot.ai_followup_enabled)
        self.assertEqual(MessageEvent.query.count(), 3)
        # Idempotent duplicate inbound event does not increment twice.
        self.signed_webhook({"entry": [{"changes": [{"value": {"messages": [{"id": "wamid.reply", "from": "919000000001", "timestamp": "1789027300", "type": "text", "text": {"body": "STOP"}, "context": {"id": "wamid.events"}}]}}]}]})
        self.assertEqual(recipient.reply_count, 1)


if __name__ == "__main__":
    unittest.main()
