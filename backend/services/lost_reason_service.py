LOST_REASON_OPTIONS = (
    "Payment too high",
    "Timing issue",
    "Family issue",
    "Chose a competitor",
    "No response",
    "Not interested",
    "Not a good fit",
    "Other",
)


def canonical_lost_reason(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    exact = {option.lower(): option for option in LOST_REASON_OPTIONS}
    if raw.lower() in exact:
        return exact[raw.lower()]

    text = raw.lower()
    keyword_groups = (
        ("Payment too high", ("payment", "price", "pricing", "cost", "budget", "expensive", "fee")),
        ("Timing issue", ("timing", "not now", "later", "delay", "schedule", "busy")),
        ("Family issue", ("family", "parent", "personal reason")),
        ("Chose a competitor", ("competitor", "another provider", "other provider", "alternative")),
        ("No response", ("no response", "not responding", "unresponsive", "unreachable", "no reply")),
        ("Not interested", ("not interested", "declined", "changed mind")),
        ("Not a good fit", ("not qualified", "not a fit", "not suitable", "requirement mismatch", "ineligible")),
    )
    return next((label for label, keywords in keyword_groups if any(keyword in text for keyword in keywords)), "Other")


def validate_lost_reason(status, reason, detail=None):
    if status != "lost":
        return None, None
    raw_reason = str(reason or "").strip()
    if not raw_reason:
        raise ValueError("Choose a Why Lost category before marking this lead as lost.")
    category = canonical_lost_reason(raw_reason)
    clean_detail = str(detail or "").strip() or None
    if category == "Other" and raw_reason.lower() != "other":
        clean_detail = clean_detail or raw_reason
    if category == "Other" and not clean_detail:
        raise ValueError("Add a short explanation when the Why Lost category is Other.")
    return category, clean_detail
