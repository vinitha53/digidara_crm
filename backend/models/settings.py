from datetime import datetime
from extensions import db


class CompanySettings(db.Model):
    __tablename__ = "company_settings"

    id = db.Column(db.Integer, primary_key=True, default=1)
    company_name = db.Column(db.Text, default="Digidara Technologies Pvt Ltd")
    tagline = db.Column(db.Text)
    about_crm = db.Column(db.Text)
    website = db.Column(db.Text, default="https://digidaratechnologies.com")
    email = db.Column(db.Text, default="info@digidaratechnologies.com")
    phone = db.Column(db.Text)
    city = db.Column(db.Text, default="Coimbatore, Tamil Nadu, India")
    gst_number = db.Column(db.Text)
    logo_url = db.Column(db.Text)
    primary_color = db.Column(db.Text, default="#534AB7")
    google_review_url = db.Column(db.Text, default="https://g.page/r/CXarerFSXX1qEBM/review")
    google_review_place_id = db.Column(db.Text)
    google_review_api_key = db.Column(db.Text)
    whatsapp_api_token = db.Column(db.Text)
    whatsapp_phone_number_id = db.Column(db.Text)
    gmail_address = db.Column(db.Text)
    gmail_app_password = db.Column(db.Text)
    course_name_options = db.Column(db.Text, default="GenAI Course\nPython Full Stack\nAI Training")
    internship_name_options = db.Column(db.Text, default="AI Internship\nML / Data Science\nWeb Development Internship")
    business_service_options = db.Column(db.Text, default="AI Product Development\nDigital Marketing\nAI Consulting\nWebsite Development\nSoftware Development")
    ai_followups_enabled = db.Column(db.Boolean, default=False)
    ai_followup_hot_interval_days = db.Column(db.Integer, default=2)
    ai_followup_warm_interval_days = db.Column(db.Integer, default=4)
    ai_followup_cold_interval_days = db.Column(db.Integer, default=5)
    ai_followup_business_hours = db.Column(db.Text, default="09:00-18:00")
    ai_followup_working_days = db.Column(db.Text, default="Mon,Tue,Wed,Thu,Fri,Sat")
    ai_followup_max_count = db.Column(db.Integer, default=10)
    ai_followup_stop_after_no_response = db.Column(db.Integer, default=0)
    ai_followup_preferred_channel = db.Column(db.Text, default="WhatsApp")
    ai_followup_llm_model = db.Column(db.Text, default="llama3-8b-8192")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            c.name: (getattr(self, c.name).isoformat() if hasattr(getattr(self, c.name), "isoformat") else getattr(self, c.name))
            for c in self.__table__.columns
        }
