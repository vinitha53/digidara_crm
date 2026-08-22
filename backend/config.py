import os
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv()


def mysql_database_url():
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "3306")
    user = os.getenv("DB_USER", "root")
    # Do not hardcode a default password; prefer explicit environment variable.
    password = quote_plus(os.getenv("DB_PASSWORD", ""))
    name = os.getenv("DB_NAME", "digidara_crm12")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}"


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or mysql_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    BOT_DB_HOST = os.getenv("BOT_DB_HOST", os.getenv("DB_HOST", "localhost"))
    BOT_DB_PORT = int(os.getenv("BOT_DB_PORT", os.getenv("DB_PORT", "3306")))
    BOT_DB_USER = os.getenv("BOT_DB_USER", os.getenv("DB_USER", "root"))
    BOT_DB_PASSWORD = os.getenv("BOT_DB_PASSWORD", os.getenv("DB_PASSWORD", ""))
    BOT_DB_NAME = os.getenv("BOT_DB_NAME", "digidara_bot")
    WEBSITE_DB_HOST = os.getenv("WEBSITE_DB_HOST", os.getenv("DB_HOST", "localhost"))
    WEBSITE_DB_PORT = int(os.getenv("WEBSITE_DB_PORT", os.getenv("DB_PORT", "3306")))
    WEBSITE_DB_USER = os.getenv("WEBSITE_DB_USER", os.getenv("DB_USER", "root"))
    WEBSITE_DB_PASSWORD = os.getenv("WEBSITE_DB_PASSWORD", os.getenv("DB_PASSWORD", ""))
    WEBSITE_DB_NAME = os.getenv("WEBSITE_DB_NAME", "")
    CRM_INTEGRATION_API_KEY = os.getenv("CRM_INTEGRATION_API_KEY", "")
    CRM_INTEGRATION_SIGNING_SECRET = os.getenv("CRM_INTEGRATION_SIGNING_SECRET", "")
    INTEGRATION_ALLOWED_SOURCES = [
        value.strip().lower()
        for value in os.getenv("INTEGRATION_ALLOWED_SOURCES", "whatsapp,chatbot,website").split(",")
        if value.strip()
    ]
    CRM_AGENCY_ID = int(os.getenv("CRM_AGENCY_ID", "2"))
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "llama3-8b-8192")
    WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
    WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    WHATSAPP_LEAD_TEMPLATE_NAME = os.getenv("WHATSAPP_LEAD_TEMPLATE_NAME", "lead_enquiry_acknowledgement")
    WHATSAPP_CUSTOMER_TEMPLATE_NAME = os.getenv("WHATSAPP_CUSTOMER_TEMPLATE_NAME", "customer_conversion_welcome")
    WHATSAPP_COMMUNICATION_TEMPLATE_NAME = os.getenv("WHATSAPP_COMMUNICATION_TEMPLATE_NAME", "customer_communication_message")
    WHATSAPP_AI_FOLLOWUP_TEMPLATE_NAME = os.getenv("WHATSAPP_AI_FOLLOWUP_TEMPLATE_NAME", "ai_lead_followup_message")
    WHATSAPP_LOGIN_OTP_TEMPLATE_NAME = os.getenv("WHATSAPP_LOGIN_OTP_TEMPLATE_NAME", "staff_login_otp")
    WHATSAPP_TEMPLATE_LANGUAGE = os.getenv("WHATSAPP_TEMPLATE_LANGUAGE", "en")
    WHATSAPP_LOGIN_OTP_URL_BUTTON_ENABLED = os.getenv("WHATSAPP_LOGIN_OTP_URL_BUTTON_ENABLED", "1") == "1"
    LOGIN_OTP_TTL_SECONDS = int(os.getenv("LOGIN_OTP_TTL_SECONDS", "300"))
    LOGIN_OTP_RESEND_SECONDS = int(os.getenv("LOGIN_OTP_RESEND_SECONDS", "60"))
    LOGIN_OTP_MAX_ATTEMPTS = int(os.getenv("LOGIN_OTP_MAX_ATTEMPTS", "5"))
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER") or os.getenv("GMAIL_ADDRESS", "")
    SMTP_PASS = os.getenv("SMTP_PASS") or os.getenv("GMAIL_APP_PASSWORD", "")
    GOOGLE_REVIEW_PLACE_ID = os.getenv("GOOGLE_REVIEW_PLACE_ID", "")
    GOOGLE_REVIEW_API_KEY = os.getenv("GOOGLE_REVIEW_API_KEY", "")
