import os
import unittest

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["DIGIDARA_SKIP_AUTO_APP"] = "1"
os.environ["SECRET_KEY"] = "test-integration-secret-key-over-32-bytes"
os.environ["JWT_SECRET_KEY"] = "test-integration-jwt-key-over-32-bytes"

from app import create_app
from extensions import db
from models import Integration
from services.email_service import email_credentials
from services.whatsapp_service import whatsapp_credentials


class IntegrationServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(
            TESTING=True,
            CRM_AGENCY_ID=2,
            SMTP_HOST="",
            SMTP_USER="",
            SMTP_PASS="",
            WHATSAPP_TOKEN="",
            WHATSAPP_PHONE_NUMBER_ID="",
        )
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_whatsapp_credentials_are_loaded_from_active_agency_integration(self):
        db.session.add(Integration(
            name="WhatsApp",
            type="whatsapp",
            is_active=True,
            agency_id=2,
            config={
                "api_key": "test-api-key",
                "api_url": "https://graph.facebook.com/v19.0",
                "sender_number": "957554507448611",
            },
        ))
        db.session.commit()

        token, sender, api_url = whatsapp_credentials()

        self.assertEqual(token, "test-api-key")
        self.assertEqual(sender, "957554507448611")
        self.assertEqual(api_url, "https://graph.facebook.com/v19.0")

    def test_gmail_credentials_are_loaded_and_app_password_spaces_are_removed(self):
        db.session.add(Integration(
            name="Gmail",
            type="email",
            is_active=True,
            agency_id=2,
            config={
                "use_tls": True,
                "smtp_host": "smtp.gmail.com",
                "smtp_port": 587,
                "from_email": "sender@example.com",
                "app_password": "abcd efgh ijkl mnop",
            },
        ))
        db.session.commit()

        host, address, password, port, use_tls = email_credentials()

        self.assertEqual(host, "smtp.gmail.com")
        self.assertEqual(address, "sender@example.com")
        self.assertEqual(password, "abcdefghijklmnop")
        self.assertEqual(port, 587)
        self.assertTrue(use_tls)

    def test_integration_from_another_agency_is_not_used(self):
        db.session.add(Integration(
            name="WhatsApp",
            type="whatsapp",
            is_active=True,
            agency_id=99,
            config={"api_key": "wrong-agency", "sender_number": "123"},
        ))
        db.session.commit()

        token, sender, _ = whatsapp_credentials()

        self.assertFalse(token)
        self.assertFalse(sender)


if __name__ == "__main__":
    unittest.main()
