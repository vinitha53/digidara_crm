from datetime import datetime
from werkzeug.security import check_password_hash, generate_password_hash
from extensions import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, nullable=False)
    login_id = db.Column(db.Text, unique=True)
    email = db.Column(db.Text, unique=True, nullable=False)
    phone = db.Column(db.Text)
    password_hash = db.Column(db.Text, nullable=False)
    role = db.Column(db.Text, nullable=False, default="employee")
    branch = db.Column(db.Text)
    department = db.Column(db.Text)
    avatar_initials = db.Column(db.Text)
    avatar_color = db.Column(db.Text, default="#534AB7")
    is_active = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    otp_secret = db.Column(db.Text)
    otp_enabled = db.Column(db.Integer, default=1)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method="pbkdf2:sha256")

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "login_id": self.login_id,
            "email": self.email,
            "phone": self.phone,
            "role": self.role,
            "branch": self.branch,
            "department": self.department,
            "avatar_initials": self.avatar_initials,
            "avatar_color": self.avatar_color,
            "is_active": bool(self.is_active),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }
