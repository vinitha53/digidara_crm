import os
import unittest
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["DIGIDARA_SKIP_AUTO_APP"] = "1"
os.environ["SECRET_KEY"] = "test-login-otp-secret"
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret"

from flask_jwt_extended import create_refresh_token, decode_token
from app import create_app
from extensions import db
from models import LoginOtpChallenge, User


class LoginOtpTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True, LOGIN_OTP_RESEND_SECONDS=60)
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        user = User(
            name="Digidara Admin",
            login_id="admin",
            email="admin@digidaratechnologies.com",
            phone="+916369979579",
            role="admin",
            is_active=1,
            otp_enabled=1,
        )
        user.set_password("Admin@1234")
        db.session.add(user)
        staff = User(
            name="Digidara Staff",
            login_id="staff",
            email="staff@digidaratechnologies.com",
            phone="+919000000001",
            role="staff",
            is_active=1,
            otp_enabled=0,
        )
        staff.set_password("Staff@1234")
        db.session.add(staff)
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    @patch("routes.auth.send_whatsapp_template")
    def test_login_uses_database_phone_and_requires_valid_otp_before_issuing_jwt(self, send_template):
        captured = {}

        def sent(to, template, language, params, url_button_params):
            captured.update(
                to=to,
                template=template,
                language=language,
                otp=params[0],
                url_button_otp=url_button_params[0],
            )
            return {"ok": True, "data": {"messages": [{"id": "wamid.test-login"}]}}

        send_template.side_effect = sent
        response = self.client.post("/api/auth/login", json={
            "email": "admin",
            "password": "Admin@1234",
            "login_type": "admin",
        })

        self.assertEqual(response.status_code, 202)
        challenge_id = response.get_json()["challenge_id"]
        self.assertNotIn("access_token", response.get_json())
        self.assertEqual(captured["to"], "916369979579")
        self.assertEqual(captured["template"], "staff_login_otp")
        self.assertEqual(len(captured["otp"]), 6)
        self.assertEqual(captured["url_button_otp"], captured["otp"])
        challenge = db.session.get(LoginOtpChallenge, challenge_id)
        self.assertEqual(challenge.delivery_status, "sent")
        self.assertEqual(challenge.send_attempts, 1)
        self.assertEqual(challenge.meta_message_id, "wamid.test-login")

        incorrect = self.client.post("/api/auth/verify-otp", json={
            "challenge_id": challenge_id,
            "otp": "000000" if captured["otp"] != "000000" else "111111",
        })
        self.assertEqual(incorrect.status_code, 401)

        verified = self.client.post("/api/auth/verify-otp", json={
            "challenge_id": challenge_id,
            "otp": captured["otp"],
        })
        self.assertEqual(verified.status_code, 200)
        self.assertIn("access_token", verified.get_json())
        self.assertEqual(verified.get_json()["user"]["login_id"], "admin")

        reused = self.client.post("/api/auth/verify-otp", json={
            "challenge_id": challenge_id,
            "otp": captured["otp"],
        })
        self.assertEqual(reused.status_code, 401)

    @patch("routes.auth.send_whatsapp_template")
    def test_repeated_login_reuses_challenge_and_sends_only_once(self, send_template):
        send_template.return_value = {"ok": True, "data": {"messages": [{"id": "wamid.single"}]}}
        credentials = {"email": "admin", "password": "Admin@1234", "login_type": "admin"}

        first = self.client.post("/api/auth/login", json=credentials)
        second = self.client.post("/api/auth/login", json=credentials)

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 202)
        self.assertEqual(first.get_json()["challenge_id"], second.get_json()["challenge_id"])
        self.assertEqual(send_template.call_count, 1)
        self.assertEqual(LoginOtpChallenge.query.count(), 1)

    @patch("routes.auth.send_whatsapp_template")
    def test_missing_database_phone_does_not_send_otp(self, send_template):
        user = User.query.filter_by(login_id="admin").one()
        user.phone = None
        db.session.commit()
        response = self.client.post("/api/auth/login", json={
            "email": "admin",
            "password": "Admin@1234",
            "login_type": "admin",
        })

        self.assertEqual(response.status_code, 409)
        send_template.assert_not_called()
        self.assertEqual(LoginOtpChallenge.query.count(), 0)

    @patch("routes.auth.send_whatsapp_template", return_value={"ok": False, "error": "not configured"})
    def test_delivery_failure_never_issues_tokens(self, _send_template):
        response = self.client.post("/api/auth/login", json={
            "email": "admin",
            "password": "Admin@1234",
            "login_type": "admin",
        })

        self.assertEqual(response.status_code, 503)
        self.assertNotIn("access_token", response.get_json())
        challenge = LoginOtpChallenge.query.one()
        self.assertIsNotNone(challenge.consumed_at)

    @patch("routes.auth.send_whatsapp_template")
    def test_resend_invalidates_the_previous_otp(self, send_template):
        sent_otps = []
        self.app.config["LOGIN_OTP_RESEND_SECONDS"] = 0

        def sent(_to, _template, _language, params, url_button_params):
            self.assertEqual(url_button_params, params)
            sent_otps.append(params[0])
            return {"ok": True}

        send_template.side_effect = sent
        with patch("routes.auth.new_otp", side_effect=["123456", "654321"]):
            started = self.client.post("/api/auth/login", json={
                "email": "admin",
                "password": "Admin@1234",
                "login_type": "admin",
            }).get_json()
            resent = self.client.post("/api/auth/resend-otp", json={
                "challenge_id": started["challenge_id"],
            })

        self.assertEqual(resent.status_code, 200)
        challenge = db.session.get(LoginOtpChallenge, started["challenge_id"])
        self.assertEqual(challenge.send_attempts, 2)
        old_otp = self.client.post("/api/auth/verify-otp", json={
            "challenge_id": started["challenge_id"],
            "otp": sent_otps[0],
        })
        self.assertEqual(old_otp.status_code, 401)
        new_otp = self.client.post("/api/auth/verify-otp", json={
            "challenge_id": started["challenge_id"],
            "otp": sent_otps[1],
        })
        self.assertEqual(new_otp.status_code, 200)

    @patch("routes.auth.send_whatsapp_template")
    def test_explicitly_disabled_otp_keeps_legacy_login_compatible(self, send_template):
        user = User.query.filter_by(login_id="admin").one()
        user.otp_enabled = 0
        db.session.commit()

        response = self.client.post("/api/auth/login", json={
            "email": "admin",
            "password": "Admin@1234",
            "login_type": "admin",
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn("access_token", response.get_json())
        send_template.assert_not_called()

    def test_admin_login_rejects_staff_accounts(self):
        response = self.client.post("/api/auth/login", json={
            "email": "staff",
            "password": "Staff@1234",
            "login_type": "admin",
        })

        self.assertEqual(response.status_code, 403)
        self.assertIn("Staff Login", response.get_json()["message"])
        self.assertNotIn("access_token", response.get_json())

    def test_staff_login_rejects_administrator_accounts(self):
        response = self.client.post("/api/auth/login", json={
            "email": "admin",
            "password": "Admin@1234",
            "login_type": "staff",
        })

        self.assertEqual(response.status_code, 403)
        self.assertIn("Admin Login", response.get_json()["message"])
        self.assertNotIn("access_token", response.get_json())

    def test_staff_login_accepts_non_admin_accounts(self):
        response = self.client.post("/api/auth/login", json={
            "email": "staff",
            "password": "Staff@1234",
            "login_type": "staff",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["user"]["role"], "staff")
        self.assertIn("access_token", response.get_json())
        self.assertIn("refresh_token", response.get_json())

    def test_refresh_rotates_tokens_and_keeps_an_active_user_signed_in(self):
        login = self.client.post("/api/auth/login", json={
            "email": "staff",
            "password": "Staff@1234",
            "login_type": "staff",
        }).get_json()

        renewed = self.client.post(
            "/api/auth/refresh",
            headers={"Authorization": f"Bearer {login['refresh_token']}"},
        )

        self.assertEqual(renewed.status_code, 200)
        self.assertIn("access_token", renewed.get_json())
        self.assertIn("refresh_token", renewed.get_json())
        me = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {renewed.get_json()['access_token']}"},
        )
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.get_json()["login_id"], "staff")

    def test_refresh_token_session_window_is_thirty_minutes(self):
        login = self.client.post("/api/auth/login", json={
            "email": "staff",
            "password": "Staff@1234",
            "login_type": "staff",
        }).get_json()

        claims = decode_token(login["refresh_token"])
        self.assertGreaterEqual(claims["exp"] - claims["iat"], 29 * 60)
        self.assertLessEqual(claims["exp"] - claims["iat"], 30 * 60)
        self.assertEqual(claims["session_policy"], "idle-30-v1")

    def test_refresh_rejects_tokens_from_the_old_long_lived_policy(self):
        staff = User.query.filter_by(login_id="staff").one()
        old_token = create_refresh_token(identity=str(staff.id))

        response = self.client.post(
            "/api/auth/refresh",
            headers={"Authorization": f"Bearer {old_token}"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertIn("updated security policy", response.get_json()["message"])

    def test_refresh_rejects_a_user_whose_access_was_deactivated(self):
        staff = User.query.filter_by(login_id="staff").one()
        token = create_refresh_token(identity=str(staff.id))
        staff.is_active = 0
        db.session.commit()

        response = self.client.post(
            "/api/auth/refresh",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertIn("no longer active", response.get_json()["message"])


if __name__ == "__main__":
    unittest.main()
