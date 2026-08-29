"""
DigiDARA Technologies - WhatsApp AI Bot v9.0 (Python + OpenAI API)
================================================================
LLM    : OpenAI GPT-4o (primary); local Ollama if OpenAI fails / no key
Method : Structured Prompt Engineering (Role + Rules + Knowledge + History)
         OpenAI first for quality; OLLAMA_* used only as fallback
Storage: MySQL (pymysql — works with MySQL 8.0)
Summary: One team lead report daily at 6:30 PM Asia/Kolkata
"""

import os, re, json, http.client, threading, time, logging, sys, hashlib, hmac
from datetime import datetime, date, timedelta, timezone
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from dotenv import load_dotenv
from flask import Flask, request, jsonify
import pymysql, pymysql.cursors
import schedule

load_dotenv()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ─────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger("DigiDARA")

def step(emoji, msg):
    """Print a clear step log — easy to follow in terminal."""
    log.info(f"{emoji}  {msg}")

# ─────────────────────────────────────────────────────────────
# CREDENTIALS & CONFIG
# ─────────────────────────────────────────────────────────────
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "957554507448611")
WHATSAPP_TOKEN  = os.getenv("WHATSAPP_TOKEN",  "YOUR_PERMANENT_TOKEN_HERE")
VERIFY_TOKEN    = os.getenv("VERIFY_TOKEN",    "digidara_webhook_2026")
def parse_phone_numbers(value: str) -> list:
    numbers = [re.sub(r"\D", "", item) for item in re.split(r"[,;\s]+", value or "")]
    return list(dict.fromkeys(number for number in numbers if number))


ADMIN_NUMBERS = parse_phone_numbers(os.getenv("OWNER_NUMBER", "919500406945"))
OPERATIONS_NUMBERS = parse_phone_numbers(os.getenv("OPERATIONS_NUMBERS", ""))
OWNER_NUMBERS = list(dict.fromkeys(ADMIN_NUMBERS + OPERATIONS_NUMBERS))
OWNER_NUMBER    = OWNER_NUMBERS[0] if OWNER_NUMBERS else "919500406945"
if len(OWNER_NUMBERS) != 3:
    log.warning(
        "Team notifications expect 3 recipients (1 admin + 2 operations); "
        f"currently configured: {len(OWNER_NUMBERS)}"
    )
SUMMARY_SECRET  = os.getenv("SUMMARY_SECRET",  "digidara123")
PORT            = int(os.getenv("PORT", 3002))
COMPANY_DOMAIN  = "https://www.digidaratechnologies.com"

CRM_API_URL = os.getenv("CRM_API_URL", "").strip()
CRM_INTEGRATION_API_KEY = os.getenv("CRM_INTEGRATION_API_KEY", "").strip()
CRM_INTEGRATION_SIGNING_SECRET = os.getenv("CRM_INTEGRATION_SIGNING_SECRET", "").strip()
CRM_PUSH_TIMEOUT_SECONDS = max(5, int(os.getenv("CRM_PUSH_TIMEOUT_SECONDS", "15")))
CRM_PUSH_RETRY_COUNT = max(1, min(5, int(os.getenv("CRM_PUSH_RETRY_COUNT", "3"))))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL   = "gpt-4o"
OPENAI_HOST    = "api.openai.com"

OLLAMA_HOST  = os.getenv("OLLAMA_HOST",  "127.0.0.1")
OLLAMA_PORT  = int(os.getenv("OLLAMA_PORT", 11434))
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

SUMMARY_TIME = os.getenv("SUMMARY_TIME", "18:00")
SUMMARY_TIME_EVENING = os.getenv("SUMMARY_TIME_EVENING", "18:30")
SUMMARY_MODE = os.getenv("SUMMARY_MODE", "interval").strip().lower()
SUMMARY_INTERVAL = int(os.getenv("SUMMARY_INTERVAL", "10"))
APP_TZ_NAME = os.getenv("APP_TIMEZONE", "Asia/Kolkata")
try:
    APP_TZ = ZoneInfo(APP_TZ_NAME)
except ZoneInfoNotFoundError:
    log.warning(f"Timezone '{APP_TZ_NAME}' not found; falling back to fixed IST offset")
    APP_TZ = timezone(timedelta(hours=5, minutes=30), "IST")
WA_TEMPLATE_LANGUAGE = os.getenv("WA_TEMPLATE_LANGUAGE", "en")
DAILY_SUMMARY_TEMPLATE_NAME = os.getenv("DAILY_SUMMARY_TEMPLATE_NAME", "digidara_evening_lead_summary")
NEW_LEAD_TEMPLATE_NAME = os.getenv("NEW_LEAD_TEMPLATE_NAME", "digidara_new_lead_alert")
CUSTOMER_SUMMARY_TEMPLATE_NAME = os.getenv("CUSTOMER_SUMMARY_TEMPLATE_NAME", "chat_summary_followup")
WA_TEMPLATE_FALLBACK_TO_TEXT = os.getenv("WA_TEMPLATE_FALLBACK_TO_TEXT", "true").lower() in ("1", "true", "yes", "on")
DAILY_SUMMARY_TEMPLATE_PARAM_COUNT = int(os.getenv("DAILY_SUMMARY_TEMPLATE_PARAM_COUNT", "5"))
NEW_LEAD_TEMPLATE_PARAM_COUNT = int(os.getenv("NEW_LEAD_TEMPLATE_PARAM_COUNT", "5"))
CUSTOMER_SUMMARY_TEMPLATE_PARAM_COUNT = int(os.getenv("CUSTOMER_SUMMARY_TEMPLATE_PARAM_COUNT", "3"))
INACTIVITY_SUMMARY_ENABLED = os.getenv("INACTIVITY_SUMMARY_ENABLED", "true").lower() in ("1", "true", "yes", "on")
INACTIVITY_SUMMARY_DELAY_SECONDS = int(os.getenv("INACTIVITY_SUMMARY_DELAY_SECONDS", "300"))

_inactivity_timers = {}
_inactivity_lock = threading.Lock()
_processed_message_ids = {}
_processed_message_lock = threading.Lock()
MESSAGE_DEDUP_TTL_SECONDS = 3600

def app_now():
    return datetime.now(APP_TZ).replace(tzinfo=None)

def app_today():
    return app_now().date()


def claim_inbound_message(message_id: str) -> bool:
    """Return False when Meta retries an inbound message already being processed."""
    if not message_id:
        return True

    now = time.time()
    with _processed_message_lock:
        expired_before = now - MESSAGE_DEDUP_TTL_SECONDS
        expired_ids = [
            seen_id
            for seen_id, seen_at in _processed_message_ids.items()
            if seen_at < expired_before
        ]
        for seen_id in expired_ids:
            _processed_message_ids.pop(seen_id, None)

        if message_id in _processed_message_ids:
            return False
        _processed_message_ids[message_id] = now
        return True

def normalize_summary_time(value: str) -> str:
    raw = (value or "").strip()
    if re.fullmatch(r"\d{1,2}:\d{2}", raw):
        hour, minute = raw.split(":")
        return f"{int(hour):02d}:{minute}"
    if re.fullmatch(r"\d{1,2}:\d{2}:\d{2}", raw):
        hour, minute, second = raw.split(":")
        return f"{int(hour):02d}:{minute}:{second}"
    log.warning(f"Invalid SUMMARY_TIME '{raw}', falling back to 18:00")
    return "18:00"

def server_summary_time(value: str) -> str:
    parts = [int(p) for p in normalize_summary_time(value).split(":")]
    while len(parts) < 3:
        parts.append(0)

    app_target = datetime.now(APP_TZ).replace(
        hour=parts[0],
        minute=parts[1],
        second=parts[2],
        microsecond=0,
    )
    server_target = app_target.astimezone()
    if parts[2]:
        return server_target.strftime("%H:%M:%S")
    return server_target.strftime("%H:%M")

# ─────────────────────────────────────────────────────────────
# LOAD & COMPRESS KNOWLEDGE BASE
# ─────────────────────────────────────────────────────────────
KNOWLEDGE_BASE = ""

def load_knowledge():
    """
    Load knowledge.txt and compress it to ~1500 tokens max.
    Strips all JSON schema, SEO tags, HTML — keeps only factual content.
    llama3.2:3b context window: ~128k tokens, but we keep it tight for speed.
    """
    global KNOWLEDGE_BASE

    paths = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "knowledge.txt"),
        os.path.join(os.getcwd(), "knowledge.txt"),
    ]
    raw = ""
    for p in paths:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                raw = f.read()
            log.info(f"✅ knowledge.txt loaded: {p} ({len(raw)//1024}KB)")
            break

    if not raw:
        log.warning("⚠️  knowledge.txt not found — using built-in fallback")
        KNOWLEDGE_BASE = _fallback_knowledge()
        return

    parts = []

    # 1. Extract FAQ Q&As from JSON block
    faq = re.search(r'"faq"\s*:\s*\[(.*?)\]\s*,\s*"intents"', raw, re.DOTALL)
    if faq:
        qas = re.findall(r'"q"\s*:\s*"([^"]+)"\s*,\s*"a"\s*:\s*"([^"]+)"', faq.group(0))
        if qas:
            parts.append("## FAQ")
            for q, a in qas:
                parts.append(f"Q: {q}\nA: {a}")

    # 2. Structured facts block (hardcoded from your knowledge — most reliable)
    parts.append("""## ABOUT
- Company: DigiDARA Technologies Private Limited
- Type: ISO-Certified AI Training & Consulting | Trichy, Tamil Nadu, India
- ISO: 9001:2015 | 27001:2013 | 20000-1:2018
- Founder: Senthil Rajamarthandan (27+ yrs, HCL & Cognizant)
- Mission: Close the AI skills gap through project-based education
- Vision: 1 million learners by 2030 | Make Trichy a global AI hub
- Impact: 5000+ students | 100+ projects | 50+ college partnerships
- Contact: +91-95004-06945 | support@digidaratechnologies.com
- Website: www.digidaratechnologies.com
- Hours: Mon-Fri 9:30AM-7:30PM | Sat 10AM-6PM | Sun Closed
- Address: 2nd Floor, Periyasamy Tower, Near Chathiram Bus Stand, Trichy 620002""")

    parts.append("""## COURSES  (www.digidaratechnologies.com/courses)
All courses: ISO Certificate | Live Projects | Capstone | Placement Support | Lifetime Access
Modes: Online / Offline / Hybrid

1. Data Science & Analytics — 3 Months
   Tools: Python, Pandas, NumPy, Matplotlib, Power BI, Tableau
   Outcome: Build dashboards, make data-driven decisions

2. AI & Machine Learning — 3 Months
   Tools: TensorFlow, Keras, Scikit-learn, PyTorch, Jupyter
   Outcome: Build, train & deploy intelligent ML models

3. Generative AI & Agentic AI — 3 Months
   Tools: LangChain, LangGraph, RAG, ChromaDB, FAISS, Streamlit, FastAPI, GPT, Gemini
   Outcome: Build autonomous AI agents (EduMate, CareerMate, InfoMate)

4. AI in Digital Marketing — 3 Months
   Tools: ChatGPT, Jasper AI, Canva AI, HubSpot AI, Google Ads AI, SurferSEO
   Outcome: AI-powered marketing campaigns with measurable ROI

5. Python Full Stack Development — 3 Months
   Tools: HTML, CSS, JS, React, Flask, Django, MySQL, MongoDB, AWS
   Outcome: Build & deploy complete full-stack web applications

6. AI for Managers & Business Leaders — 3 Months
   Focus: AI strategy, governance, transformation roadmap, ethical AI
   Outcome: Lead AI-driven change in your organisation""")

    parts.append("""## INTERNSHIPS  (www.digidaratechnologies.com/internships)
- Duration: 15 days to 1 month
- Modes: Online / Offline / Hybrid
- Tracks: Data Science | AI & ML | Generative+Agentic AI | Python Full Stack | AI Digital Marketing
- Every internship includes:
  * 2 mini projects + 1 capstone project
  * 1:1 mentorship & weekly review sessions
  * ISO-aligned Internship Certificate
  * Letter of Recommendation for top performers
  * Portfolio on GitHub & LinkedIn
- Bootcamp: Python & AI Foundations (1 Month, 20+ AI tools)""")

    parts.append("""## AI SERVICES  (www.digidaratechnologies.com/services)
1. AI Chatbot & Virtual Assistant — NLP bots for Website/WhatsApp/Instagram, 24/7 support
2. Custom AI Agent Development — LangChain + LangGraph + RAG autonomous agents
3. AI Business Consulting — Strategy, process automation, data governance, ethical AI
4. AI-Powered Digital Marketing — Content automation, ad optimisation, performance dashboards
Industries: Education | Healthcare | Retail | Finance | Manufacturing | MSMEs""")

    parts.append("""## CAREER SUPPORT  (www.digidaratechnologies.com/career-support)
- ATS-friendly Resume Building
- LinkedIn Optimisation (headline, keywords, summary)
- Technical Mock Interviews (AI, Python, ML, GenAI)
- 1:1 Mentorship + personalised career roadmap
- Job referrals via 50+ industry partners
- Placement drives with local & national tech companies
- Target roles: AI Intern | Data Analyst | ML Engineer | Python Developer""")

    parts.append("""## FOUNDER  (www.digidaratechnologies.com/founder)
- Name: Senthil Rajamarthandan | Title: Founder & Managing Director
- Experience: 27+ years IT leadership at HCL Technologies & Cognizant
- Expertise: Generative AI, Agentic AI, Digital Transformation, Cloud, AI Strategy
- LinkedIn: linkedin.com/in/senthilrajamarthandan""")

    KNOWLEDGE_BASE = "\n\n".join(parts)
    log.info(f"✅ Knowledge ready: {len(KNOWLEDGE_BASE)//1024}KB (~{len(KNOWLEDGE_BASE)//4} tokens)")


def _fallback_knowledge():
    return """## ABOUT
DigiDARA Technologies Private Limited | ISO-Certified AI Training & Consulting | Trichy, Tamil Nadu
Founder: Senthil Rajamarthandan | Contact: +91-95004-06945 | support@digidaratechnologies.com

## COURSES
Data Science (3M) | AI & ML (3M) | Generative+Agentic AI (3M) | AI Digital Marketing (3M) | Python Full Stack (3M) | AI for Managers (3M)
All include: ISO Certificate, Live Projects, Placement Support

## INTERNSHIPS
15 days to 1 month | All tracks | Certificate + LOR for top performers

## SERVICES
AI Chatbots | Custom AI Agents | AI Consulting | AI Digital Marketing"""

# ─────────────────────────────────────────────────────────────
# STRUCTURED PROMPT BUILDER  (best for llama3.2:3b)
#
# Strategy: Role + Rules + Knowledge + Conversation History
#
# Why NOT ReAct for 3b?
#   - ReAct needs reliable tool-calling — llama3.2:3b often misformats tool calls
#   - ReAct loops (Thought→Action→Observation) add 3x tokens per turn
#   - 3b models lose track of the loop structure mid-way
#
# Why Structured Prompt wins:
#   - Single-pass inference — fast on local hardware
#   - Clear role definition prevents hallucination outside DigiDARA scope
#   - Compressed knowledge fits in context with room for history
#   - Short history (4 msgs) keeps responses focused and fast
# ─────────────────────────────────────────────────────────────
def build_system_prompt():
    return f"""<|system|>
You are DigiDARA AI Assistant — the official WhatsApp chatbot for DigiDARA Technologies.

STRICT RULES (follow every rule, no exceptions):
1. Answer ONLY using the knowledge base below. Do not invent facts.
2. Always address the user by their name in every reply.
3. Keep replies SHORT — maximum 5 bullet points or 4 sentences. No long essays.
4. Use bullet points for lists. Use *bold* for important terms (WhatsApp format).
5. Always end with ONE relevant link or phone number.
6. NEVER mention fees, pricing, or costs. Say: "Please contact our team: +91-95004-06945"
7. If asked about topics outside DigiDARA, say: "I can only help with DigiDARA topics. For other queries, please call +91-95004-06945"
8. Reply in the same language the user writes (English or Tamil).
9. Be warm and friendly. Use 1-2 emojis naturally.

RELEVANT LINKS TO INCLUDE:
- Courses     → www.digidaratechnologies.com/courses
- Internships → www.digidaratechnologies.com/internships
- Services    → www.digidaratechnologies.com/services
- Career      → www.digidaratechnologies.com/career-support
- Website     → www.digidaratechnologies.com
- Phone       → +91-95004-06945

KNOWLEDGE BASE:
{KNOWLEDGE_BASE}
<|end|>"""

# ─────────────────────────────────────────────────────────────
# MYSQL — pymysql (works with MySQL 8.0 caching_sha2_password)
# ─────────────────────────────────────────────────────────────
db_config = {}

def init_db():
    global db_config
    db_config = {
        "host"       : os.getenv("DB_HOST", "localhost"),
        "port"       : int(os.getenv("DB_PORT", 3306)),
        "user"       : os.getenv("DB_USER", "root"),
        "password"   : os.getenv("DB_PASSWORD", "Digidara123"),
        "database"   : os.getenv("DB_NAME", "digidara_bot"),
        "charset"    : "utf8mb4",
        "autocommit" : True,
        "cursorclass": pymysql.cursors.DictCursor
    }
    # Test connection
    conn = pymysql.connect(**db_config)
    conn.close()

    for sql in [
        """CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            phone VARCHAR(20) UNIQUE NOT NULL,
            name VARCHAR(100) DEFAULT NULL,
            state VARCHAR(50) DEFAULT 'ASK_NAME',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) CHARACTER SET utf8mb4""",

        """CREATE TABLE IF NOT EXISTS messages (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            phone        VARCHAR(20)  NOT NULL,
            name         VARCHAR(100) DEFAULT NULL,
            chat_date    DATE         NOT NULL,
            conversation LONGTEXT     NOT NULL,
            created_at   DATETIME     DEFAULT CURRENT_TIMESTAMP,
            updated_at   DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_phone_date (phone, chat_date),
            INDEX idx_phone (phone),
            INDEX idx_date  (chat_date)
        ) CHARACTER SET utf8mb4""",

        """CREATE TABLE IF NOT EXISTS summaries (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            phone        VARCHAR(20)  NOT NULL,
            name         VARCHAR(100) DEFAULT NULL,
            summary_date DATE         NOT NULL,
            summary_text LONGTEXT     NOT NULL,
            created_at   DATETIME     DEFAULT CURRENT_TIMESTAMP,
            updated_at   DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_phone_date (phone, summary_date)
        ) CHARACTER SET utf8mb4""",

        """CREATE TABLE IF NOT EXISTS daily_reports (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            report_date  DATE   UNIQUE NOT NULL,
            report_text  LONGTEXT      NOT NULL,
            sent_to      VARCHAR(64)   NOT NULL,
            created_at   DATETIME      DEFAULT CURRENT_TIMESTAMP
        ) CHARACTER SET utf8mb4"""
    ]:
        run_sql(sql)

    run_sql("ALTER TABLE daily_reports MODIFY sent_to VARCHAR(64) NOT NULL")

    log.info("✅ MySQL connected & all tables ready")


def get_conn():
    return pymysql.connect(**db_config)

def run_sql(query, params=None, fetch=False):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            if fetch:
                return cur.fetchall()
        conn.commit()
        return None
    finally:
        conn.close()

def one(query, params=None):
    rows = run_sql(query, params, fetch=True)
    return rows[0] if rows else None

def many(query, params=None):
    return run_sql(query, params, fetch=True) or []


# ─────────────────────────────────────────────────────────────
# DB HELPERS
# ─────────────────────────────────────────────────────────────
def get_user(phone):
    return one("SELECT * FROM users WHERE phone = %s", (phone,))

def create_user(phone):
    run_sql("INSERT IGNORE INTO users (phone, state) VALUES (%s, %s)", (phone, "ASK_NAME"))
    return get_user(phone)

def update_user(phone, **fields):
    sets = ", ".join(f"{k} = %s" for k in fields)
    run_sql(f"UPDATE users SET {sets} WHERE phone = %s", [*fields.values(), phone])

def append_msg(phone, name, role, content):
    """
    One row per user per day.
    Each message is appended as [ROLE HH:MM] text to the conversation column.
    """
    now   = app_now()
    ts    = now.strftime("%H:%M")
    tag   = "User" if role == "user" else "Bot"
    entry = f"[{tag} {ts}] {content.strip()[:800]}\n"
    today = now.date().isoformat()

    # Upsert: insert row if not exists, else append to conversation
    # COALESCE handles NULL conversation on first append
    run_sql("""
        INSERT INTO messages (phone, name, chat_date, conversation, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            conversation = CONCAT(COALESCE(conversation, ''), %s),
            name = %s,
            updated_at = %s
    """, (phone, name, today, entry, now, now, entry, name, now))

def get_history(phone, limit=4):
    """
    Read today's conversation and return last N exchanges as
    [{role, content}] list for LLM context.
    """
    row = one("SELECT conversation FROM messages WHERE phone=%s AND chat_date=%s", (phone, app_today()))
    if not row or not row.get("conversation"):
        return []

    lines = [l.strip() for l in row["conversation"].strip().split("\n") if l.strip()]
    # Convert back to role/content format for LLM
    history = []
    for line in lines[-(limit * 2):]:
        if line.startswith("[User "):
            text = re.sub(r"\[User \d+:\d+\] ", "", line, count=1)
            history.append({"role": "user", "content": text})
        elif line.startswith("[Bot "):
            text = re.sub(r"\[Bot \d+:\d+\] ", "", line, count=1)
            history.append({"role": "assistant", "content": text})
    return history

def get_today_conversation(phone):
    """Return raw conversation string for a user today."""
    row = one("SELECT conversation, name FROM messages WHERE phone=%s AND chat_date=%s", (phone, app_today()))
    return row if row else {}

def has_conversation_today(phone):
    return bool(one("SELECT id FROM messages WHERE phone=%s AND chat_date=%s", (phone, app_today())))

def get_last_user_enquiry(phone):
    """
    Return the most recent user message before today.
    This gives returning leads a useful continuation point without adding columns.
    """
    rows = many("""
        SELECT conversation
        FROM messages
        WHERE phone = %s AND chat_date < %s
        ORDER BY chat_date DESC, updated_at DESC
        LIMIT 5
    """, (phone, app_today()))

    for row in rows:
        conversation = row.get("conversation") or ""
        user_lines = [line for line in conversation.splitlines() if line.startswith("[User ")]
        if user_lines:
            enquiry = re.sub(r"^\[User \d+:\d+\]\s*", "", user_lines[-1]).strip()
            return enquiry[:160]
    return ""

def today_active_users():
    return many("""
        SELECT phone, name FROM messages
        WHERE chat_date = %s
        ORDER BY updated_at DESC
    """, (app_today(),))

def today_stats():
    rows = many("SELECT phone, name, conversation FROM messages WHERE chat_date = %s", (app_today(),))
    total_users = len(rows)
    total_user_msgs = 0
    total_bot_msgs  = 0
    for r in rows:
        conv = r.get("conversation") or ""
        total_user_msgs += conv.count("[User ")
        total_bot_msgs  += conv.count("[Bot ")
    return {
        "total_users"    : total_users,
        "total_messages" : total_user_msgs + total_bot_msgs,
        "user_messages"  : total_user_msgs,
        "bot_messages"   : total_bot_msgs
    }

def new_users_today():
    return many("SELECT phone, name FROM users WHERE DATE(created_at) = %s", (app_today(),))

def save_summary(phone, name, text, d):
    run_sql("""
        INSERT INTO summaries (phone, name, summary_date, summary_text)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE summary_text=%s, name=%s, updated_at=NOW()
    """, (phone, name, d, text, text, name))

def save_daily_report(text, d):
    sent_to = ",".join(OWNER_NUMBERS)[:64] or "unknown"
    run_sql("""
        INSERT INTO daily_reports (report_date, report_text, sent_to)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE report_text=%s
    """, (d, text, sent_to, text))


# ─────────────────────────────────────────────────────────────
# LEAD CLASSIFICATION
# ─────────────────────────────────────────────────────────────
PAYMENT_KW = [
    "fee","fees","price","pricing","cost","how much","payment","pay",
    "amount","charge","discount","offer","emi","installment","scholarship",
    "afford","rupees","rs ","₹","money","expensive","cheap","rate",
    "package","batch price","course fee","total fee","registration fee",
    "admission fee","enroll fee","joining fee"
]

def is_payment(text):
    t = text.lower()
    return any(k in t for k in PAYMENT_KW)

HOT_LEAD_KW = [
    "join", "joining", "enroll", "enrol", "admission", "register", "registration",
    "apply", "call me", "contact me", "visit", "demo", "trial", "book", "seat",
    "batch", "start date", "when start", "certificate", "placement", "job",
    "career", "internship", "fresher", "resume", "interview"
]

WARM_LEAD_KW = [
    "course", "courses", "training", "class", "classes", "online", "offline",
    "hybrid", "duration", "syllabus", "curriculum", "project", "ai", "ml",
    "data science", "python", "full stack", "generative ai", "digital marketing",
    "athena", "summer camp", "service", "chatbot", "consulting"
]

def _contains_any(text, keywords):
    t = (text or "").lower()
    for k in keywords:
        term = k.strip().lower()
        if not term:
            continue
        pattern = r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])"
        if re.search(pattern, t):
            return k
    return None

def classify_lead(conversation="", latest_text=""):
    text = f"{conversation or ''}\n{latest_text or ''}"
    user_msgs = len(re.findall(r"\[User ", conversation or ""))
    payment_hit = _contains_any(text, PAYMENT_KW)
    hot_hit = _contains_any(text, HOT_LEAD_KW)
    warm_hit = _contains_any(text, WARM_LEAD_KW)

    if payment_hit:
        return {"lead_status": "Hot", "lead_reason": f"Payment/fee intent: {payment_hit}", "lead_score": 100, "lead_trigger": payment_hit, "needs_owner_followup": True}
    if hot_hit:
        return {"lead_status": "Hot", "lead_reason": f"High intent keyword: {hot_hit}", "lead_score": 85, "lead_trigger": hot_hit, "needs_owner_followup": True}
    if user_msgs >= 4 and warm_hit:
        return {"lead_status": "Hot", "lead_reason": f"Repeated interest in {warm_hit}", "lead_score": 80, "lead_trigger": warm_hit, "needs_owner_followup": True}
    if warm_hit or user_msgs >= 2:
        return {"lead_status": "Warm", "lead_reason": f"Interested in {warm_hit}" if warm_hit else "Multiple user messages", "lead_score": 55, "lead_trigger": warm_hit or "engagement", "needs_owner_followup": False}
    return {"lead_status": "Cold", "lead_reason": "Low intent or first casual message", "lead_score": 20, "lead_trigger": "", "needs_owner_followup": False}

def payment_msg(name):
    return (
        f"Hi {name}! 😊\n\n"
        f"💰 *Regarding Fees & Pricing*\n\n"
        f"Our fees are personalised based on:\n"
        f"• Learning mode (Online / Offline / Hybrid)\n"
        f"• Course track & duration\n"
        f"• Special offers & scholarships\n\n"
        f"🔴 *Please contact our team directly:*\n\n"
        f"📞 *Call/WhatsApp:* +91-95004-06945\n"
        f"📧 *Email:* support@digidaratechnologies.com\n"
        f"🌐 *Website:* www.digidaratechnologies.com\n\n"
        f"⏰ Mon–Fri 9:30AM–7:30PM | Sat 10AM–6PM\n\n"
        f"Our counsellor will get back to you shortly! 🎯"
    )


# ─────────────────────────────────────────────────────────────
# LLM - OpenAI (primary) + Ollama (fallback)
# ─────────────────────────────────────────────────────────────
OLLAMA_HOST  = os.getenv("OLLAMA_HOST", "127.0.0.1")
OLLAMA_PORT  = int(os.getenv("OLLAMA_PORT", 11434))
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")


def call_openai(messages, max_tokens, temperature):
    """OpenAI /v1/chat/completions primary LLM."""
    key = (OPENAI_API_KEY or "").strip()
    if not key:
        return None
    payload = json.dumps({
        "model"       : OPENAI_MODEL,
        "messages"    : messages,
        "max_tokens"  : max_tokens,
        "temperature" : temperature,
    }, ensure_ascii=False).encode("utf-8")
    try:
        log.info(f"OpenAI -> {OPENAI_MODEL} ({len(payload)} bytes)")
        conn = http.client.HTTPSConnection(OPENAI_HOST, timeout=90)
        conn.request(
            "POST",
            "/v1/chat/completions",
            payload,
            {
                "Content-Type"   : "application/json",
                "Authorization"  : f"Bearer {key}",
                "Content-Length" : str(len(payload)),
            },
        )
        res  = conn.getresponse()
        body = res.read().decode("utf-8")
        conn.close()
        log.info(f"OpenAI HTTP {res.status} | {len(body)} bytes")
        if res.status != 200:
            log.error(f"OpenAI HTTP {res.status}: {body[:500]}")
            return None
        data = json.loads(body)
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        reply = (msg.get("content") or "").strip()
        if reply:
            log.info(f"OpenAI reply: {len(reply)} chars")
        return reply if reply else None
    except Exception as e:
        log.error(f"OpenAI error: {type(e).__name__}: {e}")
        return None


def call_ollama(messages, max_tokens, temperature):
    payload = json.dumps({
        "model"   : OLLAMA_MODEL,
        "messages": messages,
        "stream"  : False,
        "options" : {
            "temperature": temperature,
            "num_predict" : max_tokens,
        },
    }).encode("utf-8")

    try:
        log.info(f"🔗 Connecting to Ollama at {OLLAMA_HOST}:{OLLAMA_PORT}...")
        conn = http.client.HTTPConnection(OLLAMA_HOST, OLLAMA_PORT, timeout=120)
        log.info(f"📤 Sending {len(payload)} bytes to /api/chat ...")
        conn.request("POST", "/api/chat", payload, {
            "Content-Type"  : "application/json",
            "Content-Length": str(len(payload))
        })
        log.info("⌛ Waiting for Ollama response (may take 5-30s on first run)...")
        res  = conn.getresponse()
        body = res.read().decode("utf-8")
        conn.close()
        log.info(f"📥 Ollama responded: HTTP {res.status} | {len(body)} bytes")

        if res.status != 200:
            log.error(f"❌ Ollama HTTP {res.status}: {body[:300]}")
            return None

        data = json.loads(body)
        reply = data.get("message", {}).get("content", "").strip()
        tokens_eval = data.get("eval_count", "?")
        tokens_prompt = data.get("prompt_eval_count", "?")
        log.info(f"📊 Ollama tokens — prompt: {tokens_prompt} | reply: {tokens_eval}")
        return reply

    except ConnectionRefusedError:
        log.error("❌ Ollama not running! Open Ollama Desktop or run: ollama serve")
        return None
    except Exception as e:
        log.error(f"❌ Ollama error: {type(e).__name__}: {e}")
        return None


def call_llm(messages, max_tokens, temperature):
    """Use OpenAI when API key is set and the call succeeds; otherwise Ollama."""
    key = (OPENAI_API_KEY or "").strip()
    if key:
        reply = call_openai(messages, max_tokens, temperature)
        if reply:
            return reply
        log.warning("OpenAI unavailable or empty - falling back to Ollama")
    return call_ollama(messages, max_tokens, temperature)


def ask_llm_chat(name: str, history: list, user_text: str) -> str:
    """
    Build Structured Prompt messages for chat.
    Format: [system] + [few-shot example] + [history] + [current user message]
    """
    system_content = build_system_prompt()

    messages = [
        {"role": "system", "content": system_content},

        # One-shot example so the model learns the expected format
        {"role": "user",      "content": "My name is Priya. What courses do you offer?"},
        {"role": "assistant", "content": (
            "Hi Priya! 😊 We offer 6 courses at DigiDARA Technologies:\n\n"
            "• *Data Science & Analytics* — 3 Months\n"
            "• *AI & Machine Learning* — 3 Months\n"
            "• *Generative AI & Agentic AI* — 3 Months\n"
            "• *AI in Digital Marketing* — 3 Months\n"
            "• *Python Full Stack Development* — 3 Months\n"
            "• *AI for Managers* — 3 Months\n\n"
            "All include ISO certificate, live projects & placement support!\n\n"
            "🎓 View details: www.digidaratechnologies.com/courses"
        )},
    ]

    # Add conversation history (last 4 exchanges = 8 messages max)
    for h in history[-8:]:
        messages.append({"role": h["role"], "content": h["content"]})

    # Current user message with name context
    messages.append({
        "role"   : "user",
        "content": f"[My name is {name}] {user_text}"
    })

    reply = call_llm(messages, max_tokens=512, temperature=0.5)

    if not reply:
        log.error(f"❌ LLM returned empty reply for: \"{user_text[:60]}\"")
        return (
            f"Sorry {name}, I'm having a technical issue right now! 😅\n\n"
            f"Please contact us directly:\n"
            f"📞 +91-95004-06945\n"
            f"📧 support@digidaratechnologies.com"
        )
    log.info(f"✅ LLM reply ready: {len(reply)} chars")
    return reply


def ask_llm_summary(prompt: str, max_tokens: int = 600) -> str:
    """Summary via OpenAI (or Ollama fallback)."""
    messages = [{"role": "user", "content": prompt}]
    result = call_llm(messages, max_tokens=max_tokens, temperature=0.3)
    return result or "Summary generation failed."


# ─────────────────────────────────────────────────────────────
# WHATSAPP SEND
# ─────────────────────────────────────────────────────────────
def send_wa(to: str, text: str):
    ok = True
    for i, chunk in enumerate(split_msg(text)):
        ok = _wa_send(to, chunk) and ok
        if i > 0:
            time.sleep(0.7)
    return ok

def _wa_send(to: str, body: str):
    payload = json.dumps({
        "messaging_product": "whatsapp",
        "recipient_type"   : "individual",
        "to"               : to,
        "type"             : "text",
        "text"             : {"preview_url": False, "body": body}
    }).encode("utf-8")
    try:
        conn = http.client.HTTPSConnection("graph.facebook.com", timeout=20)
        conn.request("POST", f"/v18.0/{PHONE_NUMBER_ID}/messages", payload, {
            "Authorization" : f"Bearer {WHATSAPP_TOKEN}",
            "Content-Type"  : "application/json",
            "Content-Length": str(len(payload))
        })
        res  = conn.getresponse()
        body = res.read().decode("utf-8")
        conn.close()
        if res.status == 200:
            log.info(f"✅ WA → {to} | HTTP 200")
            return True
        else:
            log.error(f"❌ WA FAILED → {to} | HTTP {res.status} | {body[:300]}")
            return False
    except Exception as e:
        log.error(f"❌ WA send error: {e}")
        return False

def send_wa_template_or_text(to: str, template_name: str, text: str, body_params=None, preserve_linebreaks=False) -> bool:
    sent = send_wa_template(to, template_name, body_params or [text], preserve_linebreaks=preserve_linebreaks)
    if sent:
        return True

    if WA_TEMPLATE_FALLBACK_TO_TEXT:
        log.warning(f"Template {template_name} failed for {to}; falling back to text send")
        return send_wa(to, text)

    log.error(f"Template {template_name} failed for {to}; text fallback disabled")
    return False

def send_owner_template_or_text(template_name: str, text: str, body_params=None, preserve_linebreaks=False) -> int:
    sent_count = 0
    for owner in OWNER_NUMBERS:
        if send_wa_template_or_text(owner, template_name, text, body_params, preserve_linebreaks=preserve_linebreaks):
            sent_count += 1
        time.sleep(0.5)
    return sent_count

def clean_template_param(value, maxlen=1800, preserve_linebreaks=False) -> str:
    text = "" if value is None else str(value)
    if preserve_linebreaks:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n+", " | ", text)
    else:
        text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r" {2,}", " ", text).strip()
    if not text:
        text = "-"
    return text[:maxlen].strip()

def compact_template_highlights(value, maxlen=650) -> str:
    text = clean_template_param(value, maxlen=maxlen + 1)
    if len(text) <= maxlen:
        return text
    clipped = text[:maxlen].rsplit(" ", 1)[0].strip(" .,-;:")
    return f"{clipped}..." if clipped else text[:maxlen]

def template_params(params: list, count: int) -> list:
    return [clean_template_param(p) for p in params[:max(0, count)]]

def daily_summary_template_params(
    date_label,
    active_users,
    total_messages,
    user_messages,
    combined_summary,
) -> list:
    return [
        clean_template_param(date_label),
        clean_template_param(active_users),
        clean_template_param(total_messages),
        clean_template_param(user_messages),
        compact_template_highlights(combined_summary, maxlen=750),
    ]

def new_lead_template_params(name, phone, message, lead_status, next_action) -> list:
    return template_params(
        [name, f"+{phone}", message, lead_status, next_action],
        NEW_LEAD_TEMPLATE_PARAM_COUNT,
    )


def limit_words(value: str, max_words: int, max_chars: int = 900) -> str:
    text = (value or "").strip()
    matches = list(re.finditer(r"\S+", text))
    if len(matches) > max_words:
        text = text[:matches[max_words - 1].end()].rstrip(" .,-;:") + "..."
    if len(text) <= max_chars:
        return text
    clipped = text[:max_chars].rsplit(" ", 1)[0].rstrip(" .,-;:")
    return f"{clipped}..." if clipped else text[:max_chars]

def send_wa_template(to: str, template_name: str, body_params=None, preserve_linebreaks=False) -> bool:
    body_params = [
        clean_template_param(p, preserve_linebreaks=preserve_linebreaks)
        for p in (body_params or [])
    ]
    log.info(f"Template {template_name} -> {to} with {len(body_params)} body param(s)")
    log.info(f"Template params preview: {[p[:80] for p in body_params]}")
    template = {
        "name": template_name,
        "language": {"code": WA_TEMPLATE_LANGUAGE},
    }
    if body_params:
        template["components"] = [{
            "type": "body",
            "parameters": [{"type": "text", "text": p} for p in body_params],
        }]

    payload = json.dumps({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "template",
        "template": template,
    }, ensure_ascii=False).encode("utf-8")
    try:
        conn = http.client.HTTPSConnection("graph.facebook.com", timeout=20)
        conn.request("POST", f"/v18.0/{PHONE_NUMBER_ID}/messages", payload, {
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
            "Content-Type": "application/json",
            "Content-Length": str(len(payload))
        })
        res = conn.getresponse()
        body = res.read().decode("utf-8")
        conn.close()
        if res.status == 200:
            log.info(f"Template {template_name} sent to {to} | HTTP 200")
            return True
        log.error(f"Template {template_name} failed to {to} | HTTP {res.status} | {body[:300]}")
        return False
    except Exception as e:
        log.error(f"Template {template_name} send error: {e}")
        return False

def mark_read(mid: str):
    payload = json.dumps({
        "messaging_product": "whatsapp",
        "status": "read", "message_id": mid
    }).encode("utf-8")
    try:
        conn = http.client.HTTPSConnection("graph.facebook.com", timeout=10)
        conn.request("POST", f"/v18.0/{PHONE_NUMBER_ID}/messages", payload, {
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
            "Content-Type" : "application/json",
            "Content-Length": str(len(payload))
        })
        conn.getresponse().read(); conn.close()
    except Exception:
        pass

def split_msg(text: str, maxlen=4000) -> list:
    if len(text) <= maxlen:
        return [text]
    chunks, buf = [], text
    while buf:
        if len(buf) <= maxlen:
            chunks.append(buf); break
        cut = buf.rfind("\n", 0, maxlen)
        if cut < 100: cut = maxlen
        chunks.append(buf[:cut].strip())
        buf = buf[cut:].strip()
    return [c for c in chunks if c]


# ─────────────────────────────────────────────────────────────
# CUSTOMER INACTIVITY SUMMARY
# ─────────────────────────────────────────────────────────────
def cancel_inactivity_summary(phone: str):
    with _inactivity_lock:
        timer_info = _inactivity_timers.pop(phone, None)
    if timer_info:
        timer_info["timer"].cancel()

def schedule_inactivity_summary(phone: str, name: str):
    if not INACTIVITY_SUMMARY_ENABLED:
        return

    delay = max(30, INACTIVITY_SUMMARY_DELAY_SECONDS)
    token = time.time()
    timer = threading.Timer(delay, _send_inactivity_summary_if_idle, args=(phone, token))
    timer.daemon = True

    with _inactivity_lock:
        old = _inactivity_timers.pop(phone, None)
        if old:
            old["timer"].cancel()
        _inactivity_timers[phone] = {"timer": timer, "token": token, "name": name}

    timer.start()
    step("TIMER", f"Customer summary scheduled for +{phone} in {delay}s")

def parse_summary_parts(raw: str):
    text = (raw or "").strip()
    summary = ""
    next_step = ""

    summary_match = re.search(r"SUMMARY\s*:\s*(.+?)(?:\n\s*NEXT[_ ]?STEP\s*:|$)", text, re.I | re.S)
    next_match = re.search(r"NEXT[_ ]?STEP\s*:\s*(.+)$", text, re.I | re.S)
    if summary_match:
        summary = summary_match.group(1).strip()
    if next_match:
        next_step = next_match.group(1).strip()

    if not summary:
        lines = [line.strip(" -") for line in text.splitlines() if line.strip()]
        summary = lines[0] if lines else "We discussed your enquiry with DigiDARA Technologies."
        if len(lines) > 1:
            next_step = lines[1]

    if not next_step:
        next_step = "Reply here if you want more details or need any changes."

    return compact_template_highlights(summary, 850), compact_template_highlights(next_step, 300)

def customer_summary_template_params(name: str, summary: str, next_step: str) -> list:
    return template_params(
        [name or "there", summary, next_step],
        CUSTOMER_SUMMARY_TEMPLATE_PARAM_COUNT
    )


def latest_customer_message(conversation: str) -> str:
    """Return the latest customer-authored message from the stored transcript."""
    for line in reversed((conversation or "").splitlines()):
        if line.startswith("[User "):
            return re.sub(r"^\[User \d{1,2}:\d{2}\]\s*", "", line).strip()[:1000]
    return ""


def crm_conversation_notes(name: str, conversation: str, latest_text: str = "") -> str:
    """Create sales-facing notes for CRM; this text is never sent to the customer."""
    conversation = (conversation or "").strip()
    latest_text = (latest_text or latest_customer_message(conversation)).strip()
    prompt = f"""Summarize this WhatsApp conversation for a CRM salesperson.

Customer: {name or 'WhatsApp User'}
Conversation:
{conversation[-6000:]}

Return concise plain text using exactly these labels:
Main enquiry:
Interested course or service:
Customer intent:
Urgency or timeline:
Pricing or payment interest:
Objections or concerns:
Requested action:
Recommended next step:
Latest customer message:

Rules:
- Use only facts stated in the conversation.
- Write "Not stated" when information is missing.
- Do not classify the lead as hot, warm, or cold; the CRM will classify it.
- Do not include internal instructions or markdown fences.
- Keep the complete summary under 1,500 characters."""
    generated = ask_llm_summary(prompt, max_tokens=350).strip()
    if generated and generated.lower() != "summary generation failed.":
        return generated[:5000]

    recent_user_messages = []
    for line in conversation.splitlines():
        if line.startswith("[User "):
            recent_user_messages.append(
                re.sub(r"^\[User \d{1,2}:\d{2}\]\s*", "", line).strip()
            )
    recent = " | ".join(value for value in recent_user_messages[-6:] if value)
    return (
        "WhatsApp conversation summary: LLM summary was unavailable.\n"
        f"Recent customer messages: {recent or latest_text or 'Not stated'}\n"
        f"Latest customer message: {latest_text or 'Not stated'}"
    )[:5000]

def _send_inactivity_summary_if_idle(phone: str, token: float):
    with _inactivity_lock:
        timer_info = _inactivity_timers.get(phone)
        if not timer_info or timer_info.get("token") != token:
            return
        _inactivity_timers.pop(phone, None)

    try:
        row = get_today_conversation(phone)
        conv = (row.get("conversation") or "").strip()
        name = row.get("name") or (get_user(phone) or {}).get("name") or "there"
        if not conv or "[User " not in conv:
            step("TIMER", f"No customer messages to summarize for +{phone}")
            return

        prompt = f"""Create a short customer-facing WhatsApp follow-up summary.

Customer name: {name}
Conversation:
{conv[-2500:]}

Return exactly:
SUMMARY: one friendly sentence summarizing what was discussed.
NEXT_STEP: one helpful next step, not promotional, max 18 words.

Rules:
- Mention only facts from the conversation.
- Do not include prices or promises unless the conversation already includes them.
- Keep it useful and polite."""

        raw = ask_llm_summary(prompt, max_tokens=180)
        summary, next_step = parse_summary_parts(raw)
        crm_notes = crm_conversation_notes(
            name=name,
            conversation=conv,
            latest_text=latest_customer_message(conv),
        )
        # CRM persistence is independent of whether the customer-facing
        # summary template is delivered successfully.
        push_lead_to_crm(
            phone=phone,
            name=name,
            text=latest_customer_message(conv),
            notes=crm_notes,
        )
        msg = (
            f"Hi {name}, here is a quick summary of our conversation:\n\n"
            f"{summary}\n\n"
            f"Next step: {next_step}\n\n"
            "Reply to this message if you need any changes or more help."
        )

        sent = send_wa_template_or_text(
            phone,
            CUSTOMER_SUMMARY_TEMPLATE_NAME,
            msg,
            customer_summary_template_params(name, summary, next_step),
            preserve_linebreaks=True
        )
        if sent:
            append_msg(phone, name, "assistant", msg)
            save_summary(phone, name, msg, app_today())
            step("OK", f"Inactivity summary sent to +{phone}")
        else:
            step("WARN", f"Inactivity summary failed for +{phone}")
    except Exception as e:
        log.error(f"Customer inactivity summary error for +{phone}: {e}")
        import traceback
        log.error(traceback.format_exc())


# ─────────────────────────────────────────────────────────────
# NAME VALIDATION
# ─────────────────────────────────────────────────────────────
def is_valid_name(text: str) -> bool:
    t = text.strip()
    return (
        2 <= len(t) <= 50
        and not any(c.isdigit() for c in t)
        and bool(re.match(r'^[\w\s]+$', t))
        and len(t.split()) <= 4
    )

def extract_name(text: str) -> str:
    candidate = re.sub(r"\s+", " ", text.strip())
    candidate = re.sub(
        r"^(my name is|name is|i am|i'm|im|this is|it's|its)\s+",
        "",
        candidate,
        flags=re.IGNORECASE,
    ).strip(" .,!?:;-")
    return candidate

def clean_name(text: str) -> str:
    words = extract_name(text).split()[:2]
    return " ".join(w.capitalize() for w in words)

def ask_name_message() -> str:
    return (
        "Hi! Welcome to *DigiDARA Technologies*.\n\n"
        "May I know your *full name* to get started?"
    )

def invalid_name_message() -> str:
    return (
        "I'd love to help! First, please tell me your *name*.\n\n"
        "Just type your name, for example:\n"
        "*Senthil* or *Priya Kumar*"
    )

def services_menu_message(name: str) -> str:
    return (
        f"*Hello {name}!* Wonderful to meet you.\n\n"
        f"Welcome to *DigiDARA Technologies*, Trichy's leading ISO-Certified "
        f"AI Training & Consulting company.\n\n"
        f"I can help you with:\n"
        f"- *Courses*: AI, Data Science, Full Stack and more\n"
        f"- *Internships*: 15 days to 1 month with ISO certificate\n"
        f"- *AI Services*: Chatbots, agents and consulting\n"
        f"- *Career Support*: Resume, mock interviews and placements\n\n"
        f"What would you like to know, *{name}*?"
    )

def returning_user_message(name: str, last_enquiry: str = "") -> str:
    if last_enquiry:
        return (
            f"Welcome back, *{name}*.\n\n"
            f"Your last enquiry was: \"{last_enquiry}\"\n\n"
            f"Now tell me, what can I help you with?"
        )

    return (
        f"Welcome back, *{name}*.\n\n"
        f"Now tell me, what can I help you with?"
    )

def save_name_and_send_menu(phone: str, text: str):
    full_name = clean_name(text)
    step("✅", f"Valid name accepted: {full_name}")
    update_user(phone, name=full_name, state="CHATTING")
    step("💾", "Name saved to DB | State → CHATTING")

    greeting = services_menu_message(full_name)
    send_wa(phone, greeting)
    append_msg(phone, full_name, "assistant", greeting)
    schedule_inactivity_summary(phone, full_name)
    step("✅", f"Services menu sent to {full_name}")


# ─────────────────────────────────────────────────────────────
# GREETING DETECTION
# ─────────────────────────────────────────────────────────────
def is_greeting(text: str) -> bool:
    """
    Check if the message is just a greeting like 'hi', 'hello', 'hey', etc.
    Return True if greeting, False if actual query/question.
    """
    greetings = [
        "hi", "hello", "hey", "hallo", "hiya", "howdy",
        "good morning", "good afternoon", "good evening",
        "good night", "namaste", "salaam", "assalam",
        "thanks", "thank you", "ok", "okay", "kk",
        "yes", "no", "yeah", "nope", "sure", "alright",
        "good", "fine", "fine thanks"
    ]
    cleaned = text.strip().lower()
    # Check exact or close matches
    for greeting in greetings:
        if greeting == cleaned or (cleaned.startswith(greeting) and len(cleaned) <= len(greeting) + 3):
            return True
    # Check if message is very short and looks like a greeting
    if len(cleaned) <= 5 and cleaned[0].isalpha():
        return True
    return False


# ─────────────────────────────────────────────────────────────
# MESSAGE HANDLER — State Machine
# ─────────────────────────────────────────────────────────────
def push_lead_to_crm(
    phone: str,
    name: str,
    text: str = "",
    lead=None,
    notes: str = "",
    email: str = "",
):
    """Create/update one CRM lead through its signed API.

    The stable external ID makes repeated WhatsApp messages update the same
    CRM row. The bot deliberately does not send a tag or score; CRM owns LLM
    classification using the supplied notes.
    """
    if not (
        CRM_API_URL
        and CRM_INTEGRATION_API_KEY
        and CRM_INTEGRATION_SIGNING_SECRET
    ):
        log.error("CRM integration environment variables are missing")
        return False

    normalized_phone = re.sub(r"\D", "", phone or "")
    if not normalized_phone:
        log.error("CRM lead push skipped: phone is missing")
        return False

    crm_notes = (notes or f"Latest WhatsApp enquiry: {text}" or "WhatsApp enquiry").strip()
    payload = {
        "source_system": "whatsapp",
        "source": "whatsapp",
        "external_id": f"whatsapp:{normalized_phone}",
        "external_created_at": datetime.now(timezone.utc).isoformat(),
        "name": name or "WhatsApp User",
        "phone": normalized_phone,
        "email": (email or "").strip() or None,
        "lead_category": "course",
        "service": "WhatsApp Enquiry",
        "message": text[:2000],
        "notes": crm_notes[:5000],
    }
    body = json.dumps(
        payload,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    timestamp = str(int(time.time()))
    signature = hmac.new(
        CRM_INTEGRATION_SIGNING_SECRET.encode("utf-8"),
        timestamp.encode("utf-8") + b"." + body,
        hashlib.sha256,
    ).hexdigest()

    parsed = urlsplit(CRM_API_URL)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query

    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        log.error("CRM lead push skipped: CRM_API_URL must be a valid HTTP(S) URL")
        return False

    for attempt in range(1, CRM_PUSH_RETRY_COUNT + 1):
        connection = None
        try:
            connection_class = (
                http.client.HTTPSConnection
                if parsed.scheme == "https"
                else http.client.HTTPConnection
            )
            connection = connection_class(
                parsed.hostname,
                parsed.port,
                timeout=CRM_PUSH_TIMEOUT_SECONDS,
            )
            connection.request(
                "POST",
                path,
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "X-CRM-API-Key": CRM_INTEGRATION_API_KEY,
                    "X-CRM-Timestamp": timestamp,
                    "X-CRM-Signature": signature,
                },
            )
            response = connection.getresponse()
            response_body = response.read().decode("utf-8", errors="replace")
            log.info(
                "CRM lead push: HTTP %s | attempt %s/%s | %s",
                response.status,
                attempt,
                CRM_PUSH_RETRY_COUNT,
                response_body[:500],
            )
            if response.status in (200, 201):
                return True
            # Authentication, signature and validation errors require a
            # configuration/code correction, not an automatic retry.
            if response.status < 500:
                return False
        except Exception as exc:
            log.warning(
                "CRM lead push attempt %s/%s failed: %s",
                attempt,
                CRM_PUSH_RETRY_COUNT,
                exc,
            )
        finally:
            if connection:
                connection.close()
        if attempt < CRM_PUSH_RETRY_COUNT:
            time.sleep(min(4, 2 ** (attempt - 1)))

    log.error("CRM lead push failed after %s attempt(s)", CRM_PUSH_RETRY_COUNT)
    return False


def handle_message(phone: str, text: str):
    cancel_inactivity_summary(phone)
    step("📩", f"New message from +{phone}")
    step("💬", f'User said: "{text[:80]}"')

    user = get_user(phone) or create_user(phone)
    state = user["state"]
    name  = user.get("name") or "Friend"
    if user.get("name") and state != "CHATTING":
        state = "CHATTING"
        update_user(phone, state=state)
        step("RECOVER", f"Existing named user moved to {state}")
    step("👤", f"User state: {state} | Name: {name}")

    # ── STATE 1: First message — ask name ──────────────────
    if state == "ASK_NAME":
        step("🆕", "New user — asking for name only")
        send_wa(phone, ask_name_message())
        update_user(phone, state="WAIT_NAME")
        step("✅", "Name prompt sent | State → WAIT_NAME")
        return

    # ── STATE 2: Waiting for name — validate properly ──────
    if state == "WAIT_NAME":
        step("✏️ ", f"Validating name input: \"{text}\"")
        name_candidate = extract_name(text)
        if not is_valid_name(name_candidate):
            step("❌", f"Invalid name \"{text}\" — asking again")
            send_wa(phone, invalid_name_message())
            return  # Stay in WAIT_NAME until valid name given

        save_name_and_send_menu(phone, name_candidate)
        return

    # ── STATE 3: Chatting — LLM handles everything ─────────
    if state == "CHATTING":
        # Check if user sent a greeting (HI, HELLO, etc.)
        if is_greeting(text):
            step("👋", f"Greeting detected: \"{text}\"")
            last_enquiry = get_last_user_enquiry(phone)
            msg = returning_user_message(name, last_enquiry)
            send_wa(phone, msg)
            append_msg(phone, name, "user", text)
            append_msg(phone, name, "assistant", msg)
            schedule_inactivity_summary(phone, name)
            threading.Thread(
                target=_notify_team_new_lead,
                args=(phone, name, text), daemon=True
            ).start()
            step("✅", f"Greeting response sent to {name}")
            return

        # Payment query → redirect instantly, notify owner
        if is_payment(text):
            step("💰", f"Payment keyword detected in: \"{text[:60]}\"")
            append_msg(phone, name, "user", text)
            msg = payment_msg(name)
            send_wa(phone, msg)
            append_msg(phone, name, "assistant", msg)
            schedule_inactivity_summary(phone, name)
            step("📲", f"Payment redirect sent to {name} | Notifying owner...")
            threading.Thread(
                target=_notify_team_new_lead,
                args=(phone, name, text), daemon=True
            ).start()
            step("✅", "Team lead-alert thread started")
            return

        # Normal query -> OpenAI when configured, else Ollama
        step("💾", f"Saving user message to DB")
        append_msg(phone, name, "user", text)
        threading.Thread(
            target=_notify_team_new_lead,
            args=(phone, name, text), daemon=True
        ).start()
        history = get_history(phone, limit=4)
        step("📚", f"Loaded {len(history)} history messages from DB")

        llm_route = f"OpenAI ({OPENAI_MODEL})" if (OPENAI_API_KEY or "").strip() else f"Ollama ({OLLAMA_MODEL})"
        step("🤖", f"Sending to {llm_route}...")
        t_start = time.time()
        time.sleep(0.3)
        reply = ask_llm_chat(name, history, text)
        t_end = time.time()
        step("⚡", f"LLM replied in {t_end - t_start:.1f}s | {len(reply)} chars")

        send_wa(phone, reply)
        append_msg(phone, name, "assistant", reply)
        schedule_inactivity_summary(phone, name)
        step("OK", f"Reply sent & saved for {name}")
        return

    if state not in ("ASK_NAME", "WAIT_NAME", "CHATTING"):
        recovered_state = "CHATTING" if user.get("name") else "ASK_NAME"
        step("WARN", f"Unknown state {state}; recovering to {recovered_state}")
        update_user(phone, state=recovered_state)
        handle_message(phone, text)
        return
# ─────────────────────────────────────────────────────────────
# TEAM LEAD NOTIFICATION
# ─────────────────────────────────────────────────────────────
def _notify_team_new_lead(phone: str, name: str, text: str):
    lead = classify_lead(latest_text=text)
    push_lead_to_crm(phone=phone, name=name, text=text, lead=lead)
    if is_payment(text):
        next_action = "Call immediately and confirm fees, course, and preferred learning mode."
    elif lead["lead_status"] == "Hot":
        next_action = "Call today and confirm the course, timing, and enrollment plan."
    elif lead["lead_status"] == "Warm":
        next_action = "Send the relevant details and follow up within one business day."
    else:
        next_action = "Review the enquiry and reply with the most relevant information."

    lead_label = f"{lead['lead_status']} ({lead['lead_score']}/100)"
    msg = (
        f"🔔 *New WhatsApp Lead*\n\n"
        f"👤 *Name:* {name}\n"
        f"📱 *Number:* +{phone}\n"
        f"🎯 *Lead:* {lead_label}\n"
        f"💬 *Asked:* {text[:300]}\n\n"
        f"➡️ *Next action:* {next_action}"
    )
    send_owner_template_or_text(
        NEW_LEAD_TEMPLATE_NAME,
        msg,
        new_lead_template_params(name, phone, text[:300], lead_label, next_action),
    )
    log.info(f"✅ Team notified: enquiry from {phone}")


# ─────────────────────────────────────────────────────────────
# DAILY SUMMARY JOB - COMBINED MESSAGE (Database + LLM Insights)
# ─────────────────────────────────────────────────────────────
def run_daily_summary(schedule_time=None):
    """Send one evening template containing a compact LLM lead summary."""
    try:
        now = app_now()
        today = now.date().isoformat()
        date_label = now.strftime("%A, %d %B %Y %I:%M %p")
        stats = today_stats()
        new_users = new_users_today()
        active = today_active_users()

        conversation_blocks = []
        for user in active[:20]:
            phone = user["phone"]
            name = user.get("name") or "Unknown"
            row = get_today_conversation(phone)
            conversation = (row.get("conversation") or "").strip()
            if conversation:
                user_message_count = conversation.count("[User ")
                bot_message_count = conversation.count("[Bot ")
                conversation_blocks.append(
                    f"Name: {name}\n"
                    f"Phone: +{phone}\n"
                    f"User messages: {user_message_count}\n"
                    f"Bot messages: {bot_message_count}\n"
                    f"Conversation:\n{conversation[-1400:]}"
                )

        if not conversation_blocks:
            llm_report = (
                "Hot topics: None | Top leads: None | Payment queries: None | "
                "Tomorrow: Monitor new WhatsApp enquiries and follow up when messages arrive."
            )
        else:
            step("LLM", "Generating evening lead summary...")
            prompt = f"""Create the evening WhatsApp management report for DigiDARA.

DATABASE DETAILS:
- Active users: {stats.get('total_users', 0)}
- Total messages: {stats.get('total_messages', 0)}
- User messages: {stats.get('user_messages', 0)}
- Bot messages: {stats.get('bot_messages', 0)}
- New users: {len(new_users)}

CONVERSATIONS:
{chr(10).join(conversation_blocks)}

Return exactly one plain-text line in this format:
Hot topics: [top 1-2 topics] | Top leads: [up to 3 names, phone numbers, interests and status] | Payment queries: [names/details or None] | Tomorrow: [up to 3 short actions] | User notes: [brief notes for the most important users]

Rules:
- Use only supplied facts.
- Prioritize payment and high-intent leads.
- Use None when no matching information exists.
- Maximum 90 words.
- Do not use line breaks, tabs, markdown, headings, or an introduction."""

            llm_report = ask_llm_summary(prompt, max_tokens=180)
            if not llm_report or llm_report == "Summary generation failed.":
                llm_report = (
                    "Hot topics: Review dashboard | Top leads: Review active conversations | "
                    "Payment queries: Check manually | Tomorrow: Contact payment and high-intent enquiries first."
                )

        llm_report = compact_template_highlights(llm_report, maxlen=650)
        template_summary = (
            f"Bot messages: {stats.get('bot_messages', 0)}; "
            f"New users: {len(new_users)} | "
            f"{llm_report}"
        )
        fallback_message = (
            f"DigiDARA WhatsApp Bot Evening Summary\n"
            f"{date_label}\n"
            f"Active users: {stats.get('total_users', 0)}\n"
            f"Total messages: {stats.get('total_messages', 0)}\n"
            f"User messages: {stats.get('user_messages', 0)}\n"
            f"{template_summary}"
        )

        sent_count = send_owner_template_or_text(
            DAILY_SUMMARY_TEMPLATE_NAME,
            fallback_message,
            daily_summary_template_params(
                date_label,
                stats.get("total_users", 0),
                stats.get("total_messages", 0),
                stats.get("user_messages", 0),
                template_summary,
            )
        )
        save_daily_report(fallback_message, today)
        step("OK", f"Evening summary sent as one template to {sent_count}/{len(OWNER_NUMBERS)} recipient(s)")
    except Exception as e:
        log.error(f"Summary error: {e}")
        import traceback
        log.error(traceback.format_exc())


def start_scheduler():
    schedule.clear()
    
    if SUMMARY_MODE == "daily":
        evening_time = SUMMARY_TIME_EVENING
        server_evening = server_summary_time(evening_time)
        schedule.every().day.at(server_evening).do(run_daily_summary, schedule_time=evening_time).tag("evening_summary")
        log.info(f"✅ Evening summary: {evening_time} {APP_TZ_NAME} ({server_evening} server time)")
        
    elif SUMMARY_MODE == "interval":
        # Testing mode: every N minutes
        interval = max(1, SUMMARY_INTERVAL)
        schedule.every(interval).minutes.do(run_daily_summary, schedule_time="TEST").tag("test_summary")
        log.info(f"⏰ Testing mode: every {interval} minutes")
        log.info("   → To enable the 6:30 PM daily summary: set SUMMARY_MODE=daily in .env")
    else:
        log.warning(f"❌ Unknown SUMMARY_MODE '{SUMMARY_MODE}' — summary disabled")

    def _loop():
        while True:
            try:
                schedule.run_pending()
            except Exception as e:
                log.error(f"❌ Scheduler error: {e}")
                import traceback
                log.error(traceback.format_exc())
            time.sleep(5)

    threading.Thread(target=_loop, daemon=True).start()
    log.info(f"📅 Scheduler started (mode: {SUMMARY_MODE})")


def next_summary_run_label():
    """Show the next scheduled evening summary."""
    jobs = schedule.get_jobs("evening_summary")
    if jobs:
        return f"Evening: {jobs[0].next_run.strftime('%Y-%m-%d %I:%M %p')}"
    return "Not scheduled"


def summary_schedule_label():
    """Show current summary schedule configuration"""
    if SUMMARY_MODE == "daily":
        return f"Daily: {SUMMARY_TIME_EVENING} {APP_TZ_NAME}"
    elif SUMMARY_MODE == "interval":
        return f"Every {max(1, SUMMARY_INTERVAL)} minutes (TESTING)"
    return "Disabled"


# FLASK ROUTES
# ─────────────────────────────────────────────────────────────
app = Flask(__name__)

@app.get("/")
def health():
    openai_cfg = bool((OPENAI_API_KEY or "").strip())
    ollama_ok = False
    try:
        c = http.client.HTTPConnection(OLLAMA_HOST, OLLAMA_PORT, timeout=3)
        c.request("GET", "/api/tags")
        r = c.getresponse(); r.read(); c.close()
        ollama_ok = r.status == 200
    except Exception:
        pass

    return jsonify({
        "name"       : "DigiDARA WhatsApp Bot v9.0",
        "status"     : "✅ Running",
        "openai"     : f"configured ({OPENAI_MODEL})" if openai_cfg else "OPENAI_API_KEY not set - using Ollama only",
        "ollama"     : f"✅ {OLLAMA_MODEL} ready" if ollama_ok else f"❌ Ollama not reachable at {OLLAMA_HOST}:{OLLAMA_PORT}",
        "knowledge"  : f"✅ {len(KNOWLEDGE_BASE)//1024}KB loaded (~{len(KNOWLEDGE_BASE)//4} tokens)",
        "summary"    : summary_schedule_label(),
        "summary_mode": SUMMARY_MODE,
        "app_timezone": APP_TZ_NAME,
        "next_summary_run_server_time": next_summary_run_label(),
        "time"       : app_now().isoformat()
    })

@app.get("/webhook")
def verify():
    mode, token, challenge = (
        request.args.get("hub.mode"),
        request.args.get("hub.verify_token"),
        request.args.get("hub.challenge")
    )
    if mode == "subscribe" and token == VERIFY_TOKEN:
        log.info("✅ Webhook verified!")
        return challenge, 200
    return "Forbidden", 403

@app.post("/webhook")
def receive():
    body = request.get_json(silent=True) or {}
    if body.get("object") != "whatsapp_business_account":
        return "OK", 200

    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})

            for msg in value.get("messages", []):
                phone = msg.get("from")
                mtype = msg.get("type")
                message_id = msg.get("id", "")
                if not claim_inbound_message(message_id):
                    log.info(f"Duplicate inbound message ignored: {message_id[:24]}")
                    continue
                log.info(f"📩 From: {phone} | Type: {mtype}")
                mark_read(message_id)

                if mtype == "text":
                    text = msg["text"]["body"].strip()
                    log.info(f'💬 Received: "{text}"')
                    log.info(f"🔀 Dispatching to handler thread...")
                    def _safe_handle(p=phone, t=text):
                        try:
                            handle_message(p, t)
                        except Exception as ex:
                            log.error(f"❌ handle_message CRASHED: {type(ex).__name__}: {ex}")
                            import traceback
                            log.error(traceback.format_exc())
                    threading.Thread(target=_safe_handle, daemon=True).start()
                else:
                    log.info(f"⚠️  Non-text message type: {mtype} — sending redirect")
                    u  = get_user(phone)
                    nm = (u or {}).get("name") or "there"
                    send_wa(phone,
                        f"Hi {nm}! 😊 I can only process *text messages* right now.\n\n"
                        f"Please type your question or contact us:\n"
                        f"📞 +91-95004-06945"
                    )

            for s in value.get("statuses", []):
                recipient = s.get('recipient_id', 'unknown')
                if s.get("errors"):
                    log.warning(f"WhatsApp delivery error for +{recipient}: {s.get('errors')}")
                log.info(f"📊 Delivery status: {s.get('status')} (msg: {s.get('id','')[:20]}) to +{recipient}")

    return "OK", 200

@app.get("/send-summary")
def manual_summary():
    if request.args.get("secret") != SUMMARY_SECRET:
        return jsonify({"error": "Unauthorized"}), 403
    threading.Thread(target=run_daily_summary, daemon=True).start()
    return jsonify({"success": True, "message": "Summary job started!"})

@app.get("/stats")
def stats():
    if request.args.get("secret") != SUMMARY_SECRET:
        return jsonify({"error": "Unauthorized"}), 403
    return jsonify({
        "today"    : today_stats(),
        "new_users": new_users_today(),
        "active"   : today_active_users()
    })

@app.get("/ollama-status")
def ollama_status():
    """Check which models are available in Ollama."""
    try:
        c = http.client.HTTPConnection(OLLAMA_HOST, OLLAMA_PORT, timeout=5)
        c.request("GET", "/api/tags")
        r = c.getresponse()
        data = json.loads(r.read().decode())
        c.close()
        models = [m["name"] for m in data.get("models", [])]
        return jsonify({"status": "✅ Ollama running", "models": models, "using": OLLAMA_MODEL})
    except Exception as e:
        return jsonify({"status": "❌ Ollama not running", "error": str(e), "fix": "Run: ollama serve"})


# ─────────────────────────────────────────────────────────────
# STARTUP
# ─────────────────────────────────────────────────────────────

@app.get("/admin")
@app.get("/admin1")
@app.get("/whatsappaichatbot")
@app.get("/whatsapp_ai_chatbot")
def admin_page():
    """Serve the admin UI."""
    admin_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "admin.html")
    if os.path.exists(admin_path):
        with open(admin_path, "r", encoding="utf-8") as f:
            return f.read(), 200, {"Content-Type": "text/html; charset=utf-8"}
    return "admin.html not found", 404

@app.get("/api/chats")
def api_chats():
    """Return all conversations for download."""
    if request.args.get("secret") != SUMMARY_SECRET:
        return jsonify({"error": "Unauthorized"}), 403
    rows = many("""
        SELECT m.phone, m.name, m.chat_date, m.conversation,
               DATE_FORMAT(m.chat_date, '%%Y-%%m-%%d') AS chat_date_iso,
               DATE_FORMAT(m.created_at, '%%Y-%%m-%%dT%%H:%%i:%%s') AS created_at_iso,
               DATE_FORMAT(m.updated_at, '%%Y-%%m-%%dT%%H:%%i:%%s') AS updated_at_iso,
               s.summary_text
        FROM messages m
        LEFT JOIN summaries s ON m.phone = s.phone AND m.chat_date = s.summary_date
        ORDER BY m.chat_date DESC, m.updated_at DESC
    """)
    for r in rows:
        r.update(classify_lead(r.get("conversation") or ""))
    return jsonify({"chats": rows, "total": len(rows)})

@app.get("/api/chats/download")
def download_chats():
    """Download all chats as a formatted text file."""
    if request.args.get("secret") != SUMMARY_SECRET:
        return jsonify({"error": "Unauthorized"}), 403
    rows = many("""
        SELECT m.phone, m.name, m.chat_date, m.conversation, s.summary_text
        FROM messages m
        LEFT JOIN summaries s ON m.phone = s.phone AND m.chat_date = s.summary_date
        ORDER BY m.chat_date DESC
    """)
    lines = ["DigiDARA Technologies — WhatsApp Chat Export"]
    lines.append(f"Generated: {app_now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 60)
    for r in rows:
        lead = classify_lead(r.get("conversation") or "")
        lines.append(f"\nUser: {r.get('name','Unknown')} | +{r['phone']} | {r['chat_date']}")
        lines.append(f"Lead: {lead['lead_status']} ({lead['lead_score']}/100) | {lead['lead_reason']}")
        lines.append("-" * 40)
        lines.append(r.get("conversation") or "(no messages)")
        if r.get("summary_text"):
            lines.append("\n📋 SUMMARY:")
            lines.append(r["summary_text"])
        lines.append("=" * 60)
    content = "\n".join(lines)
    from flask import Response
    return Response(
        content,
        mimetype="text/plain",
        headers={"Content-Disposition": f"attachment; filename=digidara_chats_{app_today()}.txt"}
    )

@app.post("/api/upload-knowledge")
def upload_knowledge():
    """
    Upload a document (PDF/TXT/DOCX) → extract text →
    ask LLM to merge it into knowledge base → save updated knowledge.txt
    """
    global KNOWLEDGE_BASE
    if request.args.get("secret") != SUMMARY_SECRET:
        return jsonify({"error": "Unauthorized"}), 403

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file     = request.files["file"]
    filename = file.filename.lower()
    raw_text = ""

    try:
        if filename.endswith(".txt"):
            raw_text = file.read().decode("utf-8", errors="ignore")

        elif filename.endswith(".pdf"):
            import io
            pdf_bytes = file.read()
            try:
                import pypdf
                reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
                raw_text = "\n".join(p.extract_text() or "" for p in reader.pages)
            except ImportError:
                return jsonify({"error": "pypdf not installed. Run: pip install pypdf"}), 500

        elif filename.endswith(".docx"):
            import io
            docx_bytes = file.read()
            try:
                import docx
                doc = docx.Document(io.BytesIO(docx_bytes))
                raw_text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            except ImportError:
                return jsonify({"error": "python-docx not installed. Run: pip install python-docx"}), 500

        else:
            return jsonify({"error": "Unsupported file type. Use .txt, .pdf, or .docx"}), 400

        if not raw_text.strip():
            return jsonify({"error": "Could not extract text from file"}), 400

        raw_text = raw_text[:8000]  # Limit to prevent token overflow
        log.info(f"📄 Extracted {len(raw_text)} chars from {filename}")

        # Extract clean facts from uploaded document ONLY — no merging with old KB
        step("🤖", f"Asking LLM to extract facts from: {filename}")
        extract_prompt = f"""You are building a knowledge base for DigiDARA Technologies chatbot.

UPLOADED DOCUMENT:
{raw_text}

Extract ALL useful facts, information, and details from the document above.
Format them cleanly using ## sections and bullet points.
Do NOT add any information that is not in the document.
Do NOT include any old or unrelated content.
Return ONLY the extracted knowledge base text, nothing else."""

        updated_kb = ask_llm_summary(extract_prompt)

        if not updated_kb or len(updated_kb) < 50:
            # If LLM fails, use raw text directly as knowledge base
            step("⚠️ ", "LLM extraction failed — using raw text directly")
            updated_kb = raw_text

        # Completely replace knowledge.txt with new content only
        kb_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "knowledge.txt")
        with open(kb_path, "w", encoding="utf-8") as f:
            f.write(updated_kb)

        KNOWLEDGE_BASE = updated_kb
        step("✅", f"knowledge.txt fully replaced! New size: {len(KNOWLEDGE_BASE)//1024}KB (~{len(KNOWLEDGE_BASE)//4} tokens)")

        return jsonify({
            "success": True,
            "message": f"Knowledge base updated from {filename}",
            "chars_extracted": len(raw_text),
            "new_kb_size": len(KNOWLEDGE_BASE),
            "preview": KNOWLEDGE_BASE[:300] + "..."
        })

    except Exception as e:
        log.error(f"❌ Upload error: {e}")
        import traceback
        log.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.get("/api/knowledge-status")
def api_knowledge_status():
    """Return current knowledge base info."""
    if request.args.get("secret") != SUMMARY_SECRET:
        return jsonify({"error": "Unauthorized"}), 403
    return jsonify({
        "size_chars" : len(KNOWLEDGE_BASE),
        "size_kb"    : len(KNOWLEDGE_BASE) // 1024,
        "tokens_est" : len(KNOWLEDGE_BASE) // 4,
        "preview"    : KNOWLEDGE_BASE[:500]
    })

@app.get("/test-summary")
def test_summary():
    """Trigger the single evening summary manually."""
    secret = request.args.get("secret", "")
    if secret != SUMMARY_SECRET:
        return jsonify({"error": "Unauthorized"}), 403

    try:
        step("🧪", "TEST: Triggering evening summary...")
        run_daily_summary(schedule_time="TEST")
        return jsonify({"status": "✅ Evening summary sent"})
    except Exception as e:
        log.error(f"❌ Test error: {e}")
        import traceback
        log.error(traceback.format_exc())
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

if __name__ == "__main__":
    print()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("DigiDARA AI WhatsApp Bot v9.0 - OpenAI GPT-4o")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # 1. Load & compress knowledge
    load_knowledge()

    # 2. Connect MySQL
    try:
        init_db()
    except Exception as e:
        log.error(f"❌ MySQL failed: {e}")
        log.error("Fix: ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY 'your_pass';")
        exit(1)

    # 3. LLM backends
    if (OPENAI_API_KEY or "").strip():
        log.info(f"OpenAI configured | Primary model: {OPENAI_MODEL}")
    else:
        log.warning("OPENAI_API_KEY not set - chat will use Ollama only")
    try:
        c = http.client.HTTPConnection(OLLAMA_HOST, OLLAMA_PORT, timeout=3)
        c.request("GET", "/api/tags")
        r = c.getresponse()
        data = json.loads(r.read().decode()); c.close()
        models = [m["name"] for m in data.get("models", [])]
        if any(OLLAMA_MODEL in m for m in models):
            log.info(f"✅ Ollama fallback ready | Model: {OLLAMA_MODEL}")
        else:
            log.warning(f"⚠️  Model '{OLLAMA_MODEL}' not found in Ollama!")
            log.warning(f"   Available: {models}")
            log.warning(f"   Run: ollama pull {OLLAMA_MODEL}")
    except Exception:
        log.warning(f"⚠️  Ollama not reachable at {OLLAMA_HOST}:{OLLAMA_PORT}")
        if (OPENAI_API_KEY or "").strip():
            log.warning("   OpenAI will still work; fix Ollama for fallback.")
        else:
            log.warning("   Start Ollama or set OPENAI_API_KEY for cloud LLM.")

    # 4. Start scheduler
    start_scheduler()

    print(f"🌐  Health    : http://localhost:{PORT}")
    print(f"📡  Webhook   : http://localhost:{PORT}/webhook")
    print(f"OpenAI    : {OPENAI_MODEL}  (needs OPENAI_API_KEY in .env)")
    print(f"🤖  Ollama FB : http://{OLLAMA_HOST}:{OLLAMA_PORT}  ({OLLAMA_MODEL})")
    print(f"🧪  Summary   : http://localhost:{PORT}/send-summary?secret={SUMMARY_SECRET}")
    print(f"📊  Stats     : http://localhost:{PORT}/stats?secret={SUMMARY_SECRET}")
    print(f"🔍  Ollama ck : http://localhost:{PORT}/ollama-status")
    print(f"⏰  Summary   : Daily at {SUMMARY_TIME_EVENING} {APP_TZ_NAME}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()

    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True) #https://145.223.19.26:8888/93e08967
