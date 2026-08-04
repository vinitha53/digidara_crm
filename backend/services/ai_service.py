import json
from datetime import datetime
from flask import current_app


def lead_scoring_context(lead, message_count=0, successful_messages=0, open_tasks=0):
    score = 20
    factors = []
    source_scores = {"whatsapp": 22, "chatbot": 20, "website": 18, "email": 14, "inperson": 16}
    source_score = source_scores.get((lead.source or "").lower(), 10)
    score += source_score
    factors.append(f"Source quality +{source_score}")
    if lead.phone:
        score += 8
        factors.append("Phone available +8")
    if lead.email:
        score += 6
        factors.append("Email available +6")
    if lead.notes and len(lead.notes) > 20:
        score += 8
        factors.append("Detailed notes +8")
    if lead.deal_value:
        value_score = min(12, int(lead.deal_value or 0) // 25000)
        score += value_score
        factors.append(f"Deal value +{value_score}")
    if lead.status in {"qualified", "won"}:
        score += 18
        factors.append(f"Advanced stage {lead.status} +18")
    elif lead.status == "contacted":
        score += 10
        factors.append("Contacted stage +10")
    elif lead.status == "lost":
        score -= 25
        factors.append("Lost stage -25")
    score += min(12, message_count * 3)
    if message_count:
        factors.append(f"Communication volume +{min(12, message_count * 3)}")
    score += min(10, successful_messages * 4)
    if successful_messages:
        factors.append(f"Delivered messages +{min(10, successful_messages * 4)}")
    score -= min(12, open_tasks * 3)
    if open_tasks:
        factors.append(f"Open tasks -{min(12, open_tasks * 3)}")
    score = max(0, min(100, score))
    tag = "hot" if score >= 75 else "warm" if score >= 50 else "cold"
    action = next_best_action(lead, score, tag, message_count, open_tasks)
    return {
        "tag": tag,
        "score": score,
        "reason": f"{tag.title()} lead with {score}/100 score based on source, stage, engagement, and CRM completeness.",
        "factors": "; ".join(factors),
        "next_best_action": action,
    }


def next_best_action(lead, score, tag, message_count=0, open_tasks=0):
    interest = lead.course_name or lead.internship_name or lead.business_requirement or lead.service
    if lead.status == "new":
        return f"Contact the lead today and confirm interest in {interest}."
    if open_tasks:
        return "Complete the open task before sending another follow-up."
    if tag == "hot" or score >= 75:
        return "Call or WhatsApp now, answer objections, and move the lead to qualified or won."
    if tag == "warm":
        return f"Send a helpful follow-up with details, pricing, or next steps for {interest}."
    if message_count == 0:
        return "Send the first introduction message and ask one qualifying question."
    return "Use a softer nurture message and pause if there is no response."


def classify_lead(lead, message_count=0, successful_messages=0, open_tasks=0):
    fallback = lead_scoring_context(lead, message_count, successful_messages, open_tasks)
    key = current_app.config.get("GROQ_API_KEY")
    if not key:
        return fallback
    try:
        from groq import Groq
        client = Groq(api_key=key)
        prompt = (
            "Score this CRM lead for sales priority. Return only JSON with tag, score, reason, factors, next_best_action. "
            "tag must be hot, warm, or cold. score must be 0-100. "
            f"Name: {lead.name}; category: {lead.lead_category}; service: {lead.service}; source: {lead.source}; "
            f"stage: {lead.status}; deal_value: {lead.deal_value}; notes: {lead.notes}; "
            f"message_count: {message_count}; successful_messages: {successful_messages}; open_tasks: {open_tasks}"
        )
        chat = client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        data = json.loads(chat.choices[0].message.content)
        return {
            "tag": data.get("tag", fallback["tag"]),
            "score": max(0, min(100, int(data.get("score", fallback["score"])))),
            "reason": data.get("reason", fallback["reason"]),
            "factors": data.get("factors", fallback["factors"]),
            "next_best_action": data.get("next_best_action", fallback["next_best_action"]),
        }
    except Exception:
        return fallback


def summarize_communication(recipient, messages, channel="Mixed"):
    transcript = "\n".join([
        f"{m.sent_at.isoformat() if m.sent_at else ''} {m.channel} {m.status}: {m.message_body}"
        for m in messages
    ])
    fallback = fallback_summary(recipient, messages, channel)
    key = current_app.config.get("GROQ_API_KEY")
    model = "llama3-8b-8192"
    if key and transcript:
        try:
            from groq import Groq
            client = Groq(api_key=key)
            prompt = (
                "Summarize this CRM communication thread. Return only JSON with summary_text, key_points, sentiment, next_action. "
                "Keep it useful for a salesperson.\n\n"
                f"Recipient: {recipient.name}\nChannel: {channel}\nTranscript:\n{transcript[:6000]}"
            )
            chat = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            data = json.loads(chat.choices[0].message.content)
            return {
                "summary_text": data.get("summary_text", fallback["summary_text"]),
                "key_points": data.get("key_points", fallback["key_points"]),
                "sentiment": data.get("sentiment", fallback["sentiment"]),
                "next_action": data.get("next_action", fallback["next_action"]),
                "model": model,
            }
        except Exception:
            return fallback
    return fallback


def fallback_summary(recipient, messages, channel):
    count = len(messages)
    latest = messages[0].message_body if messages else "No messages available."
    failed = len([m for m in messages if m.status == "failed"])
    sent = len([m for m in messages if m.status == "sent"])
    sentiment = "positive" if sent and not failed else "needs_attention" if failed else "neutral"
    return {
        "summary_text": f"{recipient.name} has {count} recorded {channel} communication item(s). Latest: {latest[:220]}",
        "key_points": f"Sent: {sent}; Failed: {failed}; Last reviewed: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
        "sentiment": sentiment,
        "next_action": "Review the latest message and follow up with a clear next step.",
        "model": "deterministic-fallback",
    }


def generate_followup_message(lead, context, settings):
    model = settings.ai_followup_llm_model or "llama3-8b-8192"
    prompt = (
        "You are an enterprise CRM follow-up assistant for Digidara Technologies. "
        "Generate one natural, personalized follow-up message in 2 to 3 short lines. Do not repeat previous messages. "
        "Be professional, concise, context-aware, and suggest the next logical step. "
        "Return only the message text.\n\n"
        f"Lead: {lead.name}\n"
        f"Temperature: {lead.tag}\n"
        f"Stage: {lead.status}\n"
        f"Source: {lead.source}\n"
        f"Interest/service: {lead.service}\n"
        f"Lead score: {lead.ai_score}\n"
        f"AI reason: {lead.ai_reason}\n"
        f"Assigned salesperson: {lead.assigned_user.name if lead.assigned_user else 'Unassigned'}\n"
        f"Context:\n{context}"
    )
    key = current_app.config.get("GROQ_API_KEY")
    if key:
        try:
            from groq import Groq
            client = Groq(api_key=key)
            chat = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.35,
            )
            text = chat.choices[0].message.content.strip()
            return {"message": text, "prompt": prompt, "model": model, "status": "success", "error": None}
        except Exception as exc:
            return {"message": fallback_followup(lead, context), "prompt": prompt, "model": model, "status": "fallback", "error": str(exc)}
    return {"message": fallback_followup(lead, context), "prompt": prompt, "model": "deterministic-fallback", "status": "fallback", "error": None}


def fallback_followup(lead, context):
    interest = lead.course_name or lead.internship_name or lead.business_requirement or lead.service
    if lead.tag == "hot":
        opener = "I wanted to quickly continue our conversation"
    elif lead.tag == "cold":
        opener = "Checking in to see if this is still relevant for you"
    else:
        opener = "Following up on your interest"
    return (
        f"Hi {lead.name}, {opener} about {interest}. "
        "If you have any pending questions, I can help clarify the next steps and share the most suitable option for you."
    )
