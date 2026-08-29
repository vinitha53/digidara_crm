import os
import unittest

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["DIGIDARA_SKIP_AUTO_APP"] = "1"
os.environ["SECRET_KEY"] = "test-employee-delete-secret"
os.environ["JWT_SECRET_KEY"] = "test-employee-delete-jwt-secret"

from flask_jwt_extended import create_access_token

from app import create_app
from extensions import db
from models import (
    AIInteraction, ActivityLog, Campaign, Customer, Lead, MessageLog, Notification,
    SavedView, Task, User, WorkflowRule,
)


class EmployeeDeletionTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True)
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.admin = User(name="Admin", email="admin@example.com", role="admin", is_active=1)
        self.admin.set_password("Admin@1234")
        self.employee = User(name="Delete Me", email="delete.me@example.com", role="staff", is_active=1)
        self.employee.set_password("Staff@1234")
        db.session.add_all([self.admin, self.employee])
        db.session.commit()
        self.headers = {"Authorization": f"Bearer {create_access_token(identity=str(self.admin.id))}"}
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_delete_physically_removes_employee_and_preserves_business_records(self):
        employee_id = self.employee.id
        lead = Lead(name="Owned Lead", phone="9000000301", service="Course", assigned_to=employee_id)
        db.session.add(lead)
        db.session.flush()
        customer = Customer(
            lead_id=lead.id, name="Owned Customer", phone="9000000301", service="Course",
            assigned_to=employee_id,
        )
        task = Task(title="Owned Task", assigned_to=employee_id, created_by=employee_id)
        campaign = Campaign(
            name="Owned Campaign", channel="email", audience="leads", message_body="Hello",
            created_by=employee_id,
        )
        workflow = WorkflowRule(name="Owned Workflow", actions="[]", created_by=employee_id)
        db.session.add_all([
            customer, task, campaign, workflow,
            ActivityLog(user_id=employee_id, action="updated lead", entity_type="lead", entity_id=lead.id),
            MessageLog(recipient_type="employee", recipient_id=employee_id, recipient_name="Delete Me", channel="WhatsApp"),
            Notification(user_id=employee_id, title="Personal notification"),
            SavedView(user_id=employee_id, module="leads", name="My view", filters="{}"),
            AIInteraction(user_id=employee_id, prompt="My prompt", response="My response"),
        ])
        db.session.commit()

        response = self.client.delete(f"/api/employees/{employee_id}", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertIn("permanently deleted", response.get_json()["message"])
        self.assertIsNone(db.session.get(User, employee_id))
        self.assertIsNone(db.session.get(Lead, lead.id).assigned_to)
        self.assertIsNone(db.session.get(Customer, customer.id).assigned_to)
        saved_task = db.session.get(Task, task.id)
        self.assertIsNone(saved_task.assigned_to)
        self.assertIsNone(saved_task.created_by)
        self.assertIsNone(db.session.get(Campaign, campaign.id).created_by)
        self.assertIsNone(db.session.get(WorkflowRule, workflow.id).created_by)
        self.assertIsNone(ActivityLog.query.filter_by(action="updated lead").one().user_id)
        self.assertEqual(MessageLog.query.filter_by(recipient_type="employee", recipient_id=employee_id).count(), 0)
        self.assertEqual(Notification.query.filter_by(user_id=employee_id).count(), 0)
        self.assertEqual(SavedView.query.filter_by(user_id=employee_id).count(), 0)
        self.assertEqual(AIInteraction.query.filter_by(user_id=employee_id).count(), 0)

    def test_employee_cannot_delete_own_account(self):
        response = self.client.delete(f"/api/employees/{self.admin.id}", headers=self.headers)

        self.assertEqual(response.status_code, 400)
        self.assertIsNotNone(db.session.get(User, self.admin.id))


if __name__ == "__main__":
    unittest.main()
