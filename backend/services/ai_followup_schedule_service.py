from datetime import datetime, time, timedelta

from flask import current_app


TEST_MINUTE_CONFIG = {
    "hot": "AI_FOLLOWUP_TEST_HOT_MINUTES",
    "warm": "AI_FOLLOWUP_TEST_WARM_MINUTES",
    "cold": "AI_FOLLOWUP_TEST_COLD_MINUTES",
}


def test_mode_enabled():
    return bool(current_app.config.get("AI_FOLLOWUP_TEST_MODE"))


def followup_interval(lead, settings):
    tag = (lead.tag or "warm").lower()
    if test_mode_enabled():
        key = TEST_MINUTE_CONFIG.get(tag, TEST_MINUTE_CONFIG["warm"])
        return timedelta(minutes=max(1, int(current_app.config.get(key) or 1)))
    if tag == "hot":
        days = int(getattr(settings, "ai_followup_hot_interval_days", None) or 2)
    elif tag == "cold":
        days = int(getattr(settings, "ai_followup_cold_interval_days", None) or 5)
    else:
        days = int(getattr(settings, "ai_followup_warm_interval_days", None) or 4)
    return timedelta(days=days)


def schedule_next_followup(lead, settings=None, base=None):
    candidate = (base or datetime.utcnow()) + followup_interval(lead, settings)
    if not test_mode_enabled() and settings:
        candidate = next_working_time(candidate, settings)
    lead.ai_next_followup_at = candidate
    return lead.ai_next_followup_at


def next_working_time(candidate, settings):
    raw_hours = str(getattr(settings, "ai_followup_business_hours", None) or "09:00-18:00")
    try:
        start_raw, end_raw = raw_hours.split("-", 1)
        start = time.fromisoformat(start_raw.strip())
        end = time.fromisoformat(end_raw.strip())
    except ValueError:
        start, end = time(9), time(18)
    working = {
        item.strip().title()[:3]
        for item in str(getattr(settings, "ai_followup_working_days", None) or "Mon,Tue,Wed,Thu,Fri,Sat").split(",")
        if item.strip()
    } or {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat"}
    for _ in range(8):
        if candidate.strftime("%a") not in working:
            candidate = datetime.combine(candidate.date() + timedelta(days=1), start)
            continue
        if candidate.time() < start:
            return datetime.combine(candidate.date(), start)
        if candidate.time() > end:
            candidate = datetime.combine(candidate.date() + timedelta(days=1), start)
            continue
        return candidate
    return candidate
