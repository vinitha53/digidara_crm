import os
from datetime import timedelta
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv()

RETIRED_GROQ_MODELS = {
    "llama-3.3-70b-versatile": "openai/gpt-oss-120b",
    "llama-3.1-8b-instant": "openai/gpt-oss-20b",
}


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
    # Access is short lived and may only be renewed inside the 30-minute
    # rolling session window.  A refresh token must never survive for days on
    # a shared CRM workstation.
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=int(os.getenv("JWT_ACCESS_TOKEN_MINUTES", "15")))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(minutes=int(os.getenv("JWT_REFRESH_TOKEN_MINUTES", "30")))
    JWT_SESSION_POLICY = os.getenv("JWT_SESSION_POLICY", "idle-30-v1")
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
        for value in os.getenv("INTEGRATION_ALLOWED_SOURCES", "whatsapp,chatbot,website,google_form").split(",")
        if value.strip()
    ]
    CRM_AGENCY_ID = int(os.getenv("CRM_AGENCY_ID", "2"))
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL = RETIRED_GROQ_MODELS.get(
        os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
    )
    GROQ_FALLBACK_MODELS = [
        value.strip()
        for value in os.getenv("GROQ_FALLBACK_MODELS", "qwen/qwen3.6-27b,openai/gpt-oss-20b").split(",")
        if value.strip()
    ]
    AI_CHAT_MAX_CONVERSATIONS = int(os.getenv("AI_CHAT_MAX_CONVERSATIONS", "30"))
    AI_CHAT_MAX_MESSAGES_PER_CONVERSATION = int(os.getenv("AI_CHAT_MAX_MESSAGES_PER_CONVERSATION", "50"))
    AI_CHAT_CONTEXT_MESSAGES = int(os.getenv("AI_CHAT_CONTEXT_MESSAGES", "6"))
    AI_FOLLOWUP_TEST_MODE = os.getenv("AI_FOLLOWUP_TEST_MODE", "0") == "1"
    AI_FOLLOWUP_TEST_HOT_MINUTES = int(os.getenv("AI_FOLLOWUP_TEST_HOT_MINUTES", "3"))
    AI_FOLLOWUP_TEST_WARM_MINUTES = int(os.getenv("AI_FOLLOWUP_TEST_WARM_MINUTES", "5"))
    AI_FOLLOWUP_TEST_COLD_MINUTES = int(os.getenv("AI_FOLLOWUP_TEST_COLD_MINUTES", "7"))
    AI_FOLLOWUP_SCHEDULER_INTERVAL_SECONDS = max(10, int(os.getenv("AI_FOLLOWUP_SCHEDULER_INTERVAL_SECONDS", "15")))
    WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
    WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID") or os.getenv("PHONE_NUMBER_ID", "")
    WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "")
    WHATSAPP_GRAPH_API_VERSION = os.getenv("WHATSAPP_GRAPH_API_VERSION", "v23.0")
    WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")
    WHATSAPP_WEBHOOK_VERIFY_TOKEN = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN") or os.getenv("VERIFY_TOKEN", "")
    CAMPAIGN_SEND_ENABLED = os.getenv("CAMPAIGN_SEND_ENABLED", "0") == "1"
    CAMPAIGN_REQUIRE_MARKETING_CONSENT = os.getenv("CAMPAIGN_REQUIRE_MARKETING_CONSENT", "1") == "1"
    CAMPAIGN_BATCH_SIZE = max(1, int(os.getenv("CAMPAIGN_BATCH_SIZE", "25")))
    CAMPAIGN_MAX_RETRIES = max(0, int(os.getenv("CAMPAIGN_MAX_RETRIES", "3")))
    CAMPAIGN_DELAY_MS = max(0, int(os.getenv("CAMPAIGN_DELAY_MS", "500")))
    CAMPAIGN_WORKER_INTERVAL_SECONDS = max(1, int(os.getenv("CAMPAIGN_WORKER_INTERVAL_SECONDS", "5")))
    CAMPAIGN_TEST_RECIPIENT_LIMIT = max(1, int(os.getenv("CAMPAIGN_TEST_RECIPIENT_LIMIT", "5")))
    CAMPAIGN_QUIET_HOURS_START = os.getenv("CAMPAIGN_QUIET_HOURS_START", "")
    CAMPAIGN_QUIET_HOURS_END = os.getenv("CAMPAIGN_QUIET_HOURS_END", "")
    CAMPAIGN_MEDIA_DIR = os.getenv("CAMPAIGN_MEDIA_DIR", "campaign_media")
    CAMPAIGN_MEDIA_MAX_BYTES = max(1024, int(os.getenv("CAMPAIGN_MEDIA_MAX_BYTES", str(5 * 1024 * 1024))))
    WHATSAPP_LEAD_TEMPLATE_NAME = os.getenv("WHATSAPP_LEAD_TEMPLATE_NAME", "lead_enquiry_acknowledgement")
    WHATSAPP_LEAD_ASSIGNMENT_TEMPLATE_NAME = os.getenv("WHATSAPP_LEAD_ASSIGNMENT_TEMPLATE_NAME", "staff_lead_assignment")
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
