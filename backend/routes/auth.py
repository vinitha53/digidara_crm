from datetime import datetime, timedelta
import hashlib
import hmac
import re
import secrets
import uuid

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import create_access_token, create_refresh_token, get_jwt_identity, jwt_required
from sqlalchemy import or_
from extensions import db
from models import LoginOtpChallenge, Role, User
from permissions import permission_role, serialize_permissions
from services.whatsapp_service import send_whatsapp_template
from services.integration_service import integration_config
from .utils import current_user, login_required

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def auth_user(user):
    data = user.to_dict()
    data["permission_role"] = permission_role(user.role)
    role = Role.query.filter_by(key=data["permission_role"]).first()
    data["role_label"] = role.label if role else ("Administrator" if data["permission_role"] == "admin" else "Staff")
    data["permissions"] = serialize_permissions(user.role)
    return data


def phone_digits(value):
    digits = re.sub(r"\D+", "", str(value or ""))
    if digits.startswith("00"):
        digits = digits[2:]
    return digits


def whatsapp_recipient(phone):
    digits = phone_digits(phone)
    if len(digits) == 10:
        return f"91{digits}"
    return digits


def masked_phone(phone):
    digits = phone_digits(phone)
    return f"******{digits[-4:]}" if len(digits) >= 4 else "your registered number"


def otp_digest(challenge_id, otp):
    key = current_app.config["SECRET_KEY"].encode("utf-8")
    return hmac.new(key, f"{challenge_id}:{otp}".encode("utf-8"), hashlib.sha256).hexdigest()


def new_otp():
    return f"{secrets.randbelow(1_000_000):06d}"


def otp_response(challenge):
    wait_seconds = max(0, current_app.config["LOGIN_OTP_RESEND_SECONDS"] - int((datetime.utcnow() - challenge.last_sent_at).total_seconds()))
    return {
        "otp_required": True,
        "challenge_id": challenge.id,
        "phone_hint": masked_phone(challenge.user.phone),
        "expires_in": max(0, int((challenge.expires_at - datetime.utcnow()).total_seconds())),
        "resend_in": wait_seconds,
    }


def send_login_otp(challenge, otp):
    whatsapp = integration_config("whatsapp")
    template_name = whatsapp.get("login_otp_template") or current_app.config["WHATSAPP_LOGIN_OTP_TEMPLATE_NAME"]
    language = whatsapp.get("template_language") or current_app.config.get("WHATSAPP_TEMPLATE_LANGUAGE", "en")
    url_button_enabled = whatsapp.get(
        "login_otp_url_button",
        current_app.config.get("WHATSAPP_LOGIN_OTP_URL_BUTTON_ENABLED", True),
    )
    if isinstance(url_button_enabled, str):
        url_button_enabled = url_button_enabled.strip().lower() in {"1", "true", "yes", "on"}
    return send_whatsapp_template(
        whatsapp_recipient(challenge.user.phone),
        template_name,
        language,
        [otp],
        [otp] if url_button_enabled else None,
    )


def meta_message_id(result):
    messages = (result.get("data") or {}).get("messages") or []
    return str(messages[0].get("id") or "")[:190] if messages else None


def issue_tokens(user):
    user.last_login = datetime.utcnow()
    return {
        "access_token": create_access_token(identity=str(user.id)),
        "refresh_token": create_refresh_token(identity=str(user.id)),
        "user": auth_user(user),
    }


@bp.post("/login")
def login():
    data = request.get_json() or {}
    login = data.get("email", "").strip().lower()
    user = User.query.filter(or_(User.email == login, User.login_id == login)).with_for_update().first()
    if (
        not user
        or not user.check_password(data.get("password", ""))
        or not user.is_active
    ):
        return jsonify({"message": "Invalid credentials"}), 401

    if not user.otp_enabled:
        payload = issue_tokens(user)
        db.session.commit()
        return jsonify(payload)

    if not phone_digits(user.phone):
        return jsonify({"message": "No registered phone number is available for this account. Contact your administrator."}), 409

    now = datetime.utcnow()
    latest = LoginOtpChallenge.query.filter_by(user_id=user.id, consumed_at=None).order_by(LoginOtpChallenge.created_at.desc()).first()
    resend_seconds = current_app.config["LOGIN_OTP_RESEND_SECONDS"]
    if latest and (now - latest.last_sent_at).total_seconds() < resend_seconds:
        return jsonify(otp_response(latest)), 202

    if latest:
        latest.consumed_at = now
    challenge = LoginOtpChallenge(
        id=str(uuid.uuid4()),
        user_id=user.id,
        otp_hash="pending",
        expires_at=now + timedelta(seconds=current_app.config["LOGIN_OTP_TTL_SECONDS"]),
        attempts=0,
        max_attempts=current_app.config["LOGIN_OTP_MAX_ATTEMPTS"],
        last_sent_at=now,
        send_attempts=1,
        delivery_status="sending",
    )
    otp = new_otp()
    challenge.otp_hash = otp_digest(challenge.id, otp)
    db.session.add(challenge)
    db.session.commit()

    result = send_login_otp(challenge, otp)
    if not result.get("ok"):
        challenge.delivery_status = "failed"
        challenge.consumed_at = datetime.utcnow()
        db.session.commit()
        current_app.logger.error("Login OTP delivery failed for user %s: %s", user.id, result.get("error") or result.get("data"))
        return jsonify({"message": "We could not send the login OTP. Check the WhatsApp integration and try again."}), 503

    challenge.delivery_status = "sent"
    challenge.meta_message_id = meta_message_id(result)
    db.session.commit()
    return jsonify(otp_response(challenge)), 202


@bp.post("/verify-otp")
def verify_otp():
    data = request.get_json() or {}
    challenge_id = str(data.get("challenge_id") or "").strip()
    otp = re.sub(r"\D+", "", str(data.get("otp") or ""))
    challenge = LoginOtpChallenge.query.filter_by(id=challenge_id).with_for_update().first() if challenge_id else None
    now = datetime.utcnow()

    if not challenge or challenge.consumed_at or not challenge.user or not challenge.user.is_active:
        return jsonify({"message": "This OTP request is no longer valid. Please sign in again."}), 401
    if challenge.expires_at <= now:
        challenge.consumed_at = now
        db.session.commit()
        return jsonify({"message": "The OTP has expired. Please sign in again."}), 401
    if challenge.attempts >= challenge.max_attempts:
        challenge.consumed_at = now
        db.session.commit()
        return jsonify({"message": "Too many incorrect attempts. Please sign in again."}), 429

    challenge.attempts += 1
    if len(otp) != 6 or not hmac.compare_digest(challenge.otp_hash, otp_digest(challenge.id, otp)):
        remaining = challenge.max_attempts - challenge.attempts
        if remaining <= 0:
            challenge.consumed_at = now
        db.session.commit()
        return jsonify({
            "message": "Incorrect OTP. Please sign in again." if remaining <= 0 else f"Incorrect OTP. {remaining} attempt{'s' if remaining != 1 else ''} remaining."
        }), 401

    challenge.consumed_at = now
    payload = issue_tokens(challenge.user)
    db.session.commit()
    return jsonify(payload)


@bp.post("/resend-otp")
def resend_otp():
    data = request.get_json() or {}
    challenge_id = str(data.get("challenge_id") or "").strip()
    challenge = LoginOtpChallenge.query.filter_by(id=challenge_id).with_for_update().first() if challenge_id else None
    now = datetime.utcnow()
    if not challenge or challenge.consumed_at or not challenge.user or not challenge.user.is_active or challenge.expires_at <= now:
        return jsonify({"message": "This OTP request is no longer valid. Please sign in again."}), 401

    wait_seconds = current_app.config["LOGIN_OTP_RESEND_SECONDS"] - int((now - challenge.last_sent_at).total_seconds())
    if wait_seconds > 0:
        return jsonify({"message": f"Please wait {wait_seconds} seconds before requesting another OTP.", **otp_response(challenge)}), 429

    otp = new_otp()
    challenge.otp_hash = otp_digest(challenge.id, otp)
    challenge.attempts = 0
    challenge.expires_at = now + timedelta(seconds=current_app.config["LOGIN_OTP_TTL_SECONDS"])
    challenge.last_sent_at = now
    challenge.send_attempts += 1
    challenge.delivery_status = "sending"
    db.session.commit()

    result = send_login_otp(challenge, otp)
    if not result.get("ok"):
        challenge.delivery_status = "failed"
        db.session.commit()
        current_app.logger.error("Login OTP resend failed for user %s: %s", challenge.user_id, result.get("error") or result.get("data"))
        return jsonify({"message": "We could not resend the login OTP. Check the WhatsApp integration and try again."}), 503
    challenge.delivery_status = "sent"
    challenge.meta_message_id = meta_message_id(result)
    db.session.commit()
    return jsonify({"message": "A new OTP was sent.", **otp_response(challenge)})


@bp.post("/logout")
@login_required
def logout():
    return jsonify({"message": "Logged out"})


@bp.get("/me")
@login_required
def me():
    return jsonify(auth_user(current_user()))


@bp.post("/change-password")
@login_required
def change_password():
    data = request.get_json() or {}
    user = current_user()
    if not user.check_password(data.get("current_password", "")):
        return jsonify({"message": "Current password is incorrect"}), 400
    user.set_password(data.get("new_password", ""))
    db.session.commit()
    return jsonify({"message": "Password changed"})


@bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    return jsonify({"access_token": create_access_token(identity=get_jwt_identity())})
