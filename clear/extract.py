"""Token Factory: transcript -> validated Signal."""
import json
import re
from pathlib import Path

from openai import OpenAI
from pydantic import ValidationError

from . import config
from .models import Signal

PLACES = json.loads((Path(__file__).resolve().parent.parent / "data" / "places.json").read_text())

SYSTEM_PROMPT = """You extract a structured signal from the transcript of a humanitarian field coordinator's voice note in Sudan.

Return ONLY a JSON object with exactly these keys:
- location_name: place named in the note, or null
- hazard_type: one of "displacement", "armed_clash", "fire_burning", "flood", "market_shock", "disease", "other"
- severity: integer 1 (minor), 2 (significant), 3 (severe/urgent), judged only from what is said
- people_affected_est: integer or null. Use a number ONLY if the speaker states it. If they say "400 families", return 400 and do NOT convert or multiply. If unstated or vague, null.
- needs: list of needs mentioned by the speaker (short strings); [] if none
- time_reference: how the speaker anchors the time (e.g. "since last night"), or null
- extraction_confidence: "high" if location, hazard and scale are all clearly stated; "medium" if one is unclear or hedged (e.g. "not confirmed"); "low" if the note is vague or speculative
- quotes: object mapping each non-null field name above to an EXACT excerpt copied verbatim from the transcript that supports it

Rules:
- Never invent facts. If something is not stated, use null (or [] for needs).
- Every non-null field needs a supporting quote in "quotes", copied character-for-character from the transcript.
- Do not guess a location that is not named. "The border area" is not a place name.
- Choose the hazard for the main event affecting people. If people have arrived, fled or are moving, use "displacement" even when burning or fighting is mentioned as the cause.
- "displacement" = people arriving/fleeing/moving; "armed_clash" = fighting/attacks; "fire_burning" = burning/fires; "market_shock" = prices/market disruption.
"""

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=config.NEBIUS_API_KEY, base_url=config.NEBIUS_BASE_URL, timeout=config.TIMEOUT)
    return _client


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", s.lower())).strip()


def resolve_place(name):
    """Look up a place name in places.json. Returns (admin2, lat, lon) or (None, None, None)."""
    if not name:
        return None, None, None
    n = _norm(name)
    for key, p in PLACES.items():
        if _norm(key) == n:
            return p["admin2"], p["lat"], p["lon"]
    return None, None, None


def _call_llm(transcript: str, extra: str = "") -> dict:
    kwargs = dict(
        model=config.NEBIUS_MODEL,
        temperature=0,
        max_tokens=800,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT + extra},
            {"role": "user", "content": f"Transcript:\n\"\"\"\n{transcript}\n\"\"\""},
        ],
    )
    try:
        r = _get_client().chat.completions.create(response_format={"type": "json_object"}, **kwargs)
    except Exception:  # model may not support JSON mode -> plain call
        r = _get_client().chat.completions.create(**kwargs)
    text = r.choices[0].message.content.strip()
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0) if m else text)


def _enforce_quotes(raw: dict, transcript: str) -> dict:
    """Drop any non-null field whose supporting quote is missing or not verbatim in the transcript."""
    tn = _norm(transcript)
    quotes = {}
    for k, v in (raw.get("quotes") or {}).items():
        parts = v if isinstance(v, list) else [v]  # some models return a list of excerpts
        ok = [p for p in parts if isinstance(p, str) and _norm(p) and _norm(p) in tn]
        if ok:
            quotes[k] = "; ".join(ok)
    for field in ("location_name", "people_affected_est", "time_reference"):
        if raw.get(field) is not None and field not in quotes:
            raw[field] = None
    if raw.get("needs") and "needs" not in quotes:
        raw["needs"] = []
    raw["quotes"] = quotes
    return raw


HEDGES = ("not confirmed", "unconfirmed", "not sure", "maybe", "may be", "might", "hearing", "rumour", "rumor", "reportedly")


def _cap_confidence(sig: Signal, transcript: str) -> Signal:
    """Deterministic guard: LLMs over-rate their own confidence. Downgrade using plain rules."""
    order = ["low", "medium", "high"]
    level = order.index(sig.extraction_confidence)
    if any(h in transcript.lower() for h in HEDGES):
        level = min(level, 1)  # hedged language -> at most medium
    if sig.location_name is None:
        level = 0  # no place named -> low
    elif sig.people_affected_est is None and sig.hazard_type == "displacement":
        level = min(level, 1)  # displacement without a stated scale -> at most medium
    sig.extraction_confidence = order[level]
    return sig


def extract_signal(transcript: str) -> Signal:
    last_err = None
    extra = ""
    for _ in range(2):  # one retry
        try:
            raw = _enforce_quotes(_call_llm(transcript, extra), transcript)
            admin2, lat, lon = resolve_place(raw.get("location_name"))
            raw.update(admin2=admin2, lat=lat, lon=lon)
            raw = {k: v for k, v in raw.items() if v is not None or k in ("location_name", "admin2", "lat", "lon", "people_affected_est", "time_reference")}
            return _cap_confidence(Signal(**raw), transcript)
        except (ValidationError, json.JSONDecodeError, KeyError, TypeError) as e:
            last_err = e
            extra = "\n\nYour previous reply was invalid. Return ONLY one valid JSON object matching the schema."
    # Graceful fallback: a low-confidence empty signal rather than a crash
    print(f"[extract] falling back to empty signal: {last_err}")
    return Signal(extraction_confidence="low")
