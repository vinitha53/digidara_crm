from datetime import datetime

from extensions import db


class LoginOtpChallenge(db.Model):
    __tablename__ = "login_otp_challenges"

    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    otp_hash = db.Column(db.String(64), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    max_attempts = db.Column(db.Integer, nullable=False, default=5)
    last_sent_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    send_attempts = db.Column(db.Integer, nullable=False, default=0)
    delivery_status = db.Column(db.String(20), nullable=False, default="pending")
    meta_message_id = db.Column(db.String(190))
    consumed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("login_otp_challenges", lazy=True))
