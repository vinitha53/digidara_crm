import csv
import io
import os
import unittest
from datetime import datetime, timedelta

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["DIGIDARA_SKIP_AUTO_APP"] = "1"
os.environ["SECRET_KEY"] = "test-lead-order-secret"
os.environ["JWT_SECRET_KEY"] = "test-lead-order-jwt-secret"

from flask_jwt_extended import create_access_token

from app import create_app
from extensions import db
from models import Lead, User


class LeadOrderingTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True)
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()

        user = User(name="Admin", email="admin@example.com", role="admin", is_active=1)
        user.set_password("Admin@1234")
        db.session.add(user)
        db.session.flush()

        now = datetime.utcnow()
        self.older = Lead(
            name="Older lead",
            phone="1000000001",
            service="Course",
            assigned_to=user.id,
            created_at=now - timedelta(days=1),
            updated_at=now,
        )
        self.newer = Lead(
            name="Newer lead",
            phone="1000000002",
            service="Course",
            assigned_to=user.id,
            created_at=now,
            updated_at=now - timedelta(days=1),
        )
        db.session.add_all([self.older, self.newer])
        db.session.commit()

        self.headers = {"Authorization": f"Bearer {create_access_token(identity=str(user.id))}"}
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_list_orders_by_creation_instead_of_last_update(self):
        response = self.client.get("/api/leads/", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [lead["name"] for lead in response.get_json()["items"]],
            ["Newer lead", "Older lead"],
        )

    def test_export_and_pipeline_use_the_same_newest_first_order(self):
        export_response = self.client.get("/api/leads/export", headers=self.headers)
        export_rows = list(csv.DictReader(io.StringIO(export_response.get_data(as_text=True))))
        pipeline_response = self.client.get("/api/leads/pipeline", headers=self.headers)

        self.assertEqual(export_response.status_code, 200)
        self.assertEqual([row["name"] for row in export_rows], ["Newer lead", "Older lead"])
        self.assertEqual(pipeline_response.status_code, 200)
        self.assertEqual(
            [lead["name"] for lead in pipeline_response.get_json()["new"]],
            ["Newer lead", "Older lead"],
        )


if __name__ == "__main__":
    unittest.main()
