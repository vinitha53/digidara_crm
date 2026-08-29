from datetime import datetime, timedelta

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
    lead.ai_next_followup_at = (base or datetime.utcnow()) + followup_interval(lead, settings)
    return lead.ai_next_followup_at
