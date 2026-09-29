"""Tavily news search (last 14 days) + one LLM call judging whether each result supports the signal."""
import re
from email.utils import parsedate_to_datetime

from tavily import TavilyClient

from .. import config, llm
from ..models import Evidence, Signal

HAZARD_TERMS = {
    "displacement": "displacement",
    "armed_clash": "armed clash attack",
    "fire_burning": "fire burning villages",
    "flood": "flood",
    "market_shock": "food prices market",
    "disease": "disease outbreak",
    "other": "",
}

JUDGE_PROMPT = """You check whether news articles corroborate a field report from Sudan.
For each article decide:
- relevant: true only if the article is about the SAME place and the same kind of event
- agrees: true ONLY if the article explicitly reports the same kind of event at that place. A general mention of the place, of the wider Sudan crisis, or of funding/politics is NOT agreement. false if it contradicts the field report.
- summary: ONE short sentence stating what the article says. Use only facts in the article text.
Return ONLY JSON: {"results": [{"i": <index>, "relevant": bool, "agrees": bool, "summary": "..."}]}"""


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]", "", t.lower())


def _mentions(article: dict, names: list) -> bool:
    """Hard guard against the LLM judge: the article must actually name the place."""
    text = _norm((article.get("title") or "") + " " + (article.get("content") or ""))
    return any(_norm(n) in text for n in names if n)


def _iso(pub):
    try:
        return parsedate_to_datetime(pub).isoformat()
    except Exception:  # noqa: BLE001
        return None


def query(signal: Signal):
    """Returns (list[Evidence], note | None)."""
    place = signal.location_name
    if not place:
        return [], None
    q = f"{place} {HAZARD_TERMS.get(signal.hazard_type, '')} Sudan".replace("  ", " ")
    res = TavilyClient(api_key=config.TAVILY_API_KEY).search(
        q, topic="news", days=14, max_results=5, timeout=config.TIMEOUT
    ).get("results", [])
    if not res:
        return [Evidence(source="tavily", agrees=False, summary=f"No news found in the last 14 days for “{q}”")], None

    quote = signal.quotes.get("hazard_type") or signal.quotes.get("location_name") or ""
    report = f"Field report: {signal.hazard_type} at {place}. Coordinator said: \"{quote}\""
    arts = "\n\n".join(
        f"[{i}] {r.get('title','')} ({r.get('published_date','')})\n{(r.get('content') or '')[:500]}"
        for i, r in enumerate(res)
    )
    note = None
    try:
        verdicts = {v["i"]: v for v in llm.chat_json(JUDGE_PROMPT, f"{report}\n\nArticles:\n{arts}", max_tokens=700)["results"]}
    except Exception as e:  # noqa: BLE001 - keep the links, mark judgement unavailable
        verdicts, note = {}, f"News judgement unavailable ({type(e).__name__})"

    ev = []
    order = sorted(range(len(res)), key=lambda i: res[i].get("score", 0), reverse=True)
    for idx in order:
        r, v = res[idx], verdicts.get(idx)
        if v is None or not v.get("relevant") or not _mentions(r, [place, signal.admin2]):
            continue
        ev.append(Evidence(
            source="tavily",
            agrees=bool(v.get("agrees")),
            summary=f"{r.get('title','').strip()} — {v.get('summary','').strip()}",
            timestamp=_iso(r.get("published_date")),
            link=r.get("url"),
        ))
        if len(ev) == 3:
            break
    if not ev:
        ev = [Evidence(source="tavily", agrees=False, summary=f"No relevant recent news found for “{q}”")]
    return ev, note
