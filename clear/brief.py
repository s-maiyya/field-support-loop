"""Alert headline + <=60-word brief (also the audio script). LLM writes it from Signal+Evidence only."""
import json
import re

from . import llm
from .models import Alert

SOURCE_NAMES = {"tavily": "web news", "firms": "NASA FIRMS satellite fire data",
                "nrc_node": "NRC field reports", "partner_b_node": "Partner B node"}

SYSTEM = """You write a spoken alert brief for a humanitarian decision-maker.
Rules: aim for 40 to 50 words and never exceed 60, plain spoken English, no bullet points, calm neutral tone (no words like urgent, severe, very confident). Cover: what happened, where, how confident (use the trust score out of 100),
the recommended action and its cost band in euros. If no action is recommended, say more information is needed and say what is missing.
Use ONLY the facts in the JSON provided. Do not add any number, place, cause or fact that is not in it (never say what caused the event).
If extraction_confidence is not "high", say the report is unconfirmed or partial. If the note said people were counted in families, say families."""


def headline(alert: Alert) -> str:
    s = alert.signal
    what = s.hazard_type.replace("_", " ").capitalize()
    where = s.location_name or "unspecified location"
    if s.admin2 and s.location_name and s.admin2 != s.location_name:
        where += f" ({s.admin2})"
    scale = f" – ~{s.people_affected_est} reported" if s.people_affected_est else ""
    return f"{what} at {where}{scale}, severity {s.severity}/3"


def _facts(alert: Alert) -> dict:
    s = alert.signal
    agree = sorted({SOURCE_NAMES[e.source] for e in alert.evidence if e.agrees})
    return {
        "location": s.location_name, "hazard": s.hazard_type, "severity_1_to_3": s.severity,
        "people_affected_as_stated": s.people_affected_est,
        "quote_on_scale": s.quotes.get("people_affected_est"),
        "needs": s.needs, "time_reference": s.time_reference,
        "extraction_confidence": s.extraction_confidence,
        "trust_score_out_of_100": alert.trust_score,
        "sources_agreeing": agree,
        "recommended_action": alert.action.name if alert.action else None,
        "action_is_information_request": bool(alert.action and alert.action.id == "request_info"),
        "cost_band_eur": alert.action.cost_band_eur if alert.action else None,
        "needs_country_director_approval": alert.escalate,
        "missing_from_note": [k for k, v in (("location", s.location_name), ("scale", s.people_affected_est)) if not v],
    }


def _fallback(alert: Alert) -> str:
    """Deterministic brief, used if the LLM is unavailable."""
    a, s = alert.action, alert.signal
    if a and a.id == "request_info":
        return f"Low confidence signal, trust {alert.trust_score} out of 100. {alert.headline}. More information is needed before any action."
    cost = f" Cost band {a.cost_band_eur[0]} to {a.cost_band_eur[1]} euros." if a else ""
    return f"{alert.headline}. Trust {alert.trust_score} out of 100. Recommended: {a.name if a else 'none'}.{cost}"


CAUSE_WORDS = {"fire", "fires", "burned", "burnt", "burning", "attack", "attacks", "shelling", "conflict", "violence", "war", "fighting", "clashes"}


def _numbers(text: str) -> set:
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*", text)}


def _grounded(text: str, facts: str) -> bool:
    """Reject briefs that introduce a number or a cause not present in the facts we supplied."""
    if not _numbers(text) <= _numbers(facts) | {"3", "100"}:
        return False
    words = set(re.findall(r"[a-z]+", text.lower()))
    return not ((words & CAUSE_WORDS) - set(re.findall(r"[a-z]+", facts.lower())))


def write_brief(alert: Alert) -> str:
    facts = json.dumps(_facts(alert))
    for _ in range(2):
        try:
            text = llm.chat(SYSTEM, facts, max_tokens=200).strip().strip('"')
            if len(text.split()) <= 60 and _grounded(text, facts):
                return text
        except Exception as e:  # noqa: BLE001
            alert.notes.append(f"Brief LLM unavailable ({type(e).__name__}); used template brief")
            break
    return _fallback(alert)
