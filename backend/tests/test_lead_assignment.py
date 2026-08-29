import os
import unittest
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["DIGIDARA_SKIP_AUTO_APP"] = "1"
os.environ["SECRET_KEY"] = "test-lead-assignment-secret"
os.environ["JWT_SECRET_KEY"] = "test-lead-assignment-jwt-secret"

from flask_jwt_extended import create_access_token

from app import create_app
from extensions import db
from models import CompanySettings, Lead, MessageLog, RolePermission, User
from services.ai_service import generate_followup_message
from services.lead_assignment_service import send_lead_assignment_notification
from routes.ai_followups import skip_reason


class LeadAssignmentTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True, GROQ_API_KEY="")
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()

        self.admin = User(name="Admin", email="admin@example.com", role="admin", is_active=1)
        self.staff = User(name="Sales Staff", email="staff@example.com", phone="9000000099", role="staff", department="sales", is_active=1)
        self.inactive = User(name="Inactive Staff", email="inactive@example.com", role="staff", is_active=0)
        for user in (self.admin, self.staff, self.inactive):
            user.set_password("Password@123")
            db.session.add(user)
        db.session.commit()

        self.admin_headers = {"Authorization": f"Bearer {create_access_token(identity=str(self.admin.id))}"}
        self.staff_headers = {"Authorization": f"Bearer {create_access_token(identity=str(self.staff.id))}"}
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def lead_payload(self, **updates):
        payload = {
            "name": "Assigned Lead",
            "phone": "9000000000",
            "service": "AI Training",
            "lead_category": "course",
            "course_name": "AI Training",
            "source": "website",
            "status": "new",
            "tag": "new",
        }
        payload.update(updates)
        return payload

    def test_admin_must_select_an_active_staff_member(self):
        missing = self.client.post("/api/leads/", json=self.lead_payload(), headers=self.admin_headers)
        inactive = self.client.post(
            "/api/leads/",
            json=self.lead_payload(assigned_to=self.inactive.id),
            headers=self.admin_headers,
        )

        self.assertEqual(missing.status_code, 400)
        self.assertEqual(inactive.status_code, 400)
        self.assertEqual(Lead.query.count(), 0)

    @patch("routes.leads.send_lead_acknowledgement")
    def test_admin_can_assign_a_new_lead_to_staff(self, acknowledgement):
        with patch("routes.leads.send_lead_assignment_notification") as assignment_notification:
            response = self.client.post(
                "/api/leads/",
                json=self.lead_payload(assigned_to=self.staff.id),
                headers=self.admin_headers,
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["assigned_to"], self.staff.id)
        self.assertEqual(response.get_json()["assigned_name"], self.staff.name)
        self.assertIn(response.get_json()["tag"], {"hot", "warm", "cold"})
        self.assertIsNotNone(response.get_json()["ai_scored_at"])
        acknowledgement.assert_called_once()
        assignment_notification.assert_called_once()
        self.assertEqual(assignment_notification.call_args.args[1].id, self.staff.id)

    @patch("routes.leads.send_lead_acknowledgement")
    def test_staff_created_lead_is_assigned_to_the_creator(self, acknowledgement):
        response = self.client.post(
            "/api/leads/",
            json=self.lead_payload(assigned_to=self.admin.id),
            headers=self.staff_headers,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["assigned_to"], self.staff.id)
        acknowledgement.assert_called_once()

    def test_assignee_list_contains_only_active_non_admin_users(self):
        response = self.client.get("/api/leads/assignees", headers=self.admin_headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.get_json()], [self.staff.id])

    @patch("services.lead_assignment_service.send_whatsapp_template")
    def test_assignment_notification_uses_meta_template_and_logs_delivery(self, send_template):
        send_template.return_value = {"ok": True, "data": {"messages": [{"id": "wamid.test"}]}}
        lead = Lead(
            name="Priya", phone="9888877777", service="GenAI Course", course_name="GenAI Course",
            lead_category="course", tag="hot", assigned_to=self.staff.id,
        )
        db.session.add(lead)
        db.session.flush()

        send_lead_assignment_notification(lead, self.staff)
        db.session.commit()

        send_template.assert_called_once_with(
            self.staff.phone,
            "staff_lead_assignment",
            "en",
            ["Sales Staff", "Priya", "GenAI Course", "9888877777", "Hot"],
        )
        log = MessageLog.query.filter_by(recipient_type="employee", recipient_id=self.staff.id).one()
        self.assertEqual(log.status, "sent")
        self.assertEqual(log.template_used, "staff_lead_assignment")

    @patch("routes.leads.send_lead_assignment_notification")
    def test_reassignment_notifies_only_when_assignee_changes(self, assignment_notification):
        lead = Lead(name="Reassign Me", phone="9000000088", service="Course", assigned_to=self.inactive.id)
        db.session.add(lead)
        db.session.commit()

        changed = self.client.put(
            f"/api/leads/{lead.id}", json={"assigned_to": self.staff.id}, headers=self.admin_headers,
        )
        unchanged = self.client.put(
            f"/api/leads/{lead.id}", json={"assigned_to": self.staff.id}, headers=self.admin_headers,
        )

        self.assertEqual(changed.status_code, 200)
        self.assertEqual(unchanged.status_code, 200)
        assignment_notification.assert_called_once()
        self.assertEqual(assignment_notification.call_args.args[1].id, self.staff.id)

    @patch("routes.leads.send_lead_assignment_notification")
    def test_bulk_assignment_notifies_each_new_assignee_once(self, assignment_notification):
        already_assigned = Lead(name="Already Assigned", phone="9000000077", service="Course", assigned_to=self.staff.id)
        newly_assigned = Lead(name="Newly Assigned", phone="9000000066", service="Project", assigned_to=self.inactive.id)
        db.session.add_all([already_assigned, newly_assigned])
        db.session.commit()

        response = self.client.post(
            "/api/leads/bulk",
            json={"ids": [already_assigned.id, newly_assigned.id], "action": "assign", "value": self.staff.id},
            headers=self.admin_headers,
        )

        self.assertEqual(response.status_code, 200)
        assignment_notification.assert_called_once()
        self.assertEqual(assignment_notification.call_args.args[0].id, newly_assigned.id)

    def test_lost_status_requires_a_standard_why_lost_category(self):
        lead = Lead(name="Potential Loss", phone="9000000065", service="Course", assigned_to=self.staff.id)
        db.session.add(lead)
        db.session.commit()

        missing = self.client.put(
            f"/api/leads/{lead.id}", json={"status": "lost"}, headers=self.admin_headers,
        )
        selected = self.client.put(
            f"/api/leads/{lead.id}",
            json={"status": "lost", "lost_reason": "Payment too high"},
            headers=self.admin_headers,
        )

        self.assertEqual(missing.status_code, 400)
        self.assertIn("Choose a Why Lost category", missing.get_json()["message"])
        self.assertEqual(selected.status_code, 200)
        self.assertEqual(selected.get_json()["lost_reason"], "Payment too high")

    def test_other_loss_category_requires_and_preserves_details(self):
        lead = Lead(name="Other Loss", phone="9000000064", service="Course", assigned_to=self.staff.id)
        db.session.add(lead)
        db.session.commit()

        missing_detail = self.client.put(
            f"/api/leads/{lead.id}",
            json={"status": "lost", "lost_reason": "Other"},
            headers=self.admin_headers,
        )
        saved = self.client.put(
            f"/api/leads/{lead.id}",
            json={"status": "lost", "lost_reason": "Other", "lost_reason_detail": "Relocating overseas"},
            headers=self.admin_headers,
        )

        self.assertEqual(missing_detail.status_code, 400)
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.get_json()["lost_reason_detail"], "Relocating overseas")

    def test_dashboard_combines_legacy_loss_keywords_into_categories(self):
        db.session.add_all([
            Lead(name="Legacy Budget", phone="9000000063", service="Course", assigned_to=self.staff.id, status="lost", lost_reason="Budget issue"),
            Lead(name="Current Price", phone="9000000062", service="Course", assigned_to=self.staff.id, status="lost", lost_reason="Payment too high"),
        ])
        db.session.commit()

        response = self.client.get("/api/reports/owner-overview", headers=self.admin_headers)

        self.assertEqual(response.status_code, 200)
        payment = next(row for row in response.get_json()["loss_reasons"] if row["key"] == "Payment too high")
        self.assertEqual(payment["count"], 2)

    def test_dashboard_lead_movement_supports_month_ranges(self):
        three_months = self.client.get(
            "/api/reports/owner-overview?trend_months=3", headers=self.admin_headers,
        )
        twelve_months = self.client.get(
            "/api/reports/owner-overview?trend_months=12", headers=self.admin_headers,
        )
        invalid_range = self.client.get(
            "/api/reports/owner-overview?trend_months=99", headers=self.admin_headers,
        )

        self.assertEqual(three_months.status_code, 200)
        self.assertEqual(len(three_months.get_json()["monthly_trend"]), 3)
        self.assertEqual(three_months.get_json()["monthly_trend_months"], 3)
        self.assertEqual(len(twelve_months.get_json()["monthly_trend"]), 12)
        self.assertEqual(twelve_months.get_json()["monthly_trend_months"], 12)
        self.assertEqual(len(invalid_range.get_json()["monthly_trend"]), 6)

    @patch("routes.ai_followups.generate_followup_message")
    def test_generate_button_reloads_updated_notes_and_changes_variation(self, generate_message):
        generate_message.side_effect = lambda lead, context, settings, variation_index=0: {
            "message": f"Variation {variation_index}: {lead.notes}",
            "prompt": context,
            "model": "test-model",
            "status": "success",
            "error": None,
        }
        lead = Lead(
            name="Notes Lead", phone="9000000055", service="AI Course",
            notes="Asked for course fees", assigned_to=self.staff.id,
        )
        db.session.add(lead)
        db.session.commit()

        first = self.client.post(f"/api/ai-followups/lead/{lead.id}/generate", headers=self.admin_headers)
        lead.notes = "Requested a callback tomorrow after 5 PM"
        db.session.commit()
        second = self.client.post(f"/api/ai-followups/lead/{lead.id}/generate", headers=self.admin_headers)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.get_json()["generated_message"], "Variation 0: Asked for course fees")
        self.assertEqual(second.get_json()["generated_message"], "Variation 1: Requested a callback tomorrow after 5 PM")
        self.assertIn("Notes: Requested a callback tomorrow after 5 PM", generate_message.call_args.args[1])

    def test_fallback_generation_uses_notes_and_returns_different_wording(self):
        self.app.config["GROQ_API_KEY"] = ""
        lead = Lead(
            name="Priya", phone="9000000044", service="GenAI Course",
            notes="Requested the weekend batch details", assigned_to=self.staff.id,
        )
        settings = CompanySettings(ai_followup_llm_model="llama-3.3-70b-versatile")

        first = generate_followup_message(lead, "", settings, variation_index=0)["message"]
        second = generate_followup_message(lead, "", settings, variation_index=1)["message"]

        self.assertIn("Requested the weekend batch details", first)
        self.assertIn("Requested the weekend batch details", second)
        self.assertNotEqual(first, second)

    def test_automatic_acknowledgement_does_not_block_scheduled_followup(self):
        lead = Lead(
            name="Automation Test", phone="9000000043", service="GenAI Course",
            assigned_to=self.staff.id,
        )
        db.session.add(lead)
        db.session.flush()
        db.session.add(MessageLog(
            recipient_type="lead", recipient_id=lead.id, recipient_name=lead.name,
            channel="WhatsApp", message_body="Enquiry received",
            template_used=self.app.config["WHATSAPP_LEAD_TEMPLATE_NAME"], status="sent",
        ))
        db.session.commit()

        self.assertIsNone(skip_reason(lead))

        db.session.add(MessageLog(
            recipient_type="lead", recipient_id=lead.id, recipient_name=lead.name,
            channel="WhatsApp", message_body="Manual salesperson message",
            template_used=None, status="sent",
        ))
        db.session.commit()

        self.assertEqual(skip_reason(lead), "Recent salesperson communication exists")

    def test_staff_can_list_and_open_only_assigned_leads(self):
        own = Lead(name="My Lead", phone="9000000001", service="Course", assigned_to=self.staff.id)
        other = Lead(name="Other Lead", phone="9000000002", service="Project", assigned_to=self.inactive.id)
        db.session.add_all([own, other])
        db.session.commit()

        listing = self.client.get("/api/leads/", headers=self.staff_headers)
        own_detail = self.client.get(f"/api/leads/{own.id}", headers=self.staff_headers)
        other_detail = self.client.get(f"/api/leads/{other.id}", headers=self.staff_headers)

        self.assertEqual(listing.status_code, 200)
        self.assertEqual([row["id"] for row in listing.get_json()["items"]], [own.id])
        self.assertEqual(own_detail.status_code, 200)
        self.assertEqual(other_detail.status_code, 404)

        own_followups = self.client.get(f"/api/ai-followups/lead/{own.id}", headers=self.staff_headers)
        other_followups = self.client.get(f"/api/ai-followups/lead/{other.id}", headers=self.staff_headers)
        self.assertEqual(own_followups.status_code, 200)
        self.assertEqual(other_followups.status_code, 404)

    def test_staff_menu_access_follows_configured_permission_rows(self):
        db.session.add_all([
            RolePermission(role="staff", page_key="leads", action="assign", allowed=1),
            RolePermission(role="staff", page_key="reports", action="view", allowed=1),
        ])
        db.session.commit()

        me = self.client.get("/api/auth/me", headers=self.staff_headers)

        self.assertEqual(me.status_code, 200)
        permissions = me.get_json()["permissions"]
        self.assertTrue(permissions["leads"]["assign"])
        self.assertTrue(permissions["reports"]["view"])

        own = Lead(name="Still Mine", phone="9000000005", service="Course", assigned_to=self.staff.id)
        other = Lead(name="Still Hidden", phone="9000000006", service="Course", assigned_to=self.inactive.id)
        db.session.add_all([own, other])
        db.session.commit()
        listing = self.client.get("/api/leads/", headers=self.staff_headers)
        self.assertEqual([row["id"] for row in listing.get_json()["items"]], [own.id])

    def test_staff_dashboard_uses_only_assigned_leads(self):
        db.session.add_all([
            Lead(name="My Won Lead", phone="9000000003", service="Course", assigned_to=self.staff.id, status="won", lead_category="course"),
            Lead(name="Other Lost Lead", phone="9000000004", service="Project", assigned_to=self.inactive.id, status="lost", lead_category="business"),
        ])
        db.session.commit()

        staff_response = self.client.get("/api/reports/owner-overview", headers=self.staff_headers)
        admin_response = self.client.get("/api/reports/owner-overview", headers=self.admin_headers)

        self.assertEqual(staff_response.status_code, 200)
        self.assertEqual(staff_response.get_json()["total_leads"], 1)
        self.assertEqual(staff_response.get_json()["won_leads"], 1)
        self.assertEqual(staff_response.get_json()["lost_leads"], 0)
        self.assertEqual(admin_response.status_code, 200)
        self.assertEqual(admin_response.get_json()["total_leads"], 2)


if __name__ == "__main__":
    unittest.main()
