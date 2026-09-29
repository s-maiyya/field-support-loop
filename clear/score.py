"""Trust score: simple, rule-based, explainable. Returns (total, breakdown)."""
from datetime import datetime, timedelta, timezone

from .models import Evidence, Signal

CONF_POINTS = {"high": 20, "medium": 10, "low": 0}


def _freshness(evidence: list[Evidence]) -> int:
    agreeing = [e for e in evidence if e.agrees]
    if not agreeing:
        return 0
    stamps = []
    for e in agreeing:
        if e.timestamp:
            try:
                stamps.append(datetime.fromisoformat(e.timestamp))
            except ValueError:
                pass
    if not stamps:
        return 5
    age = datetime.now(timezone.utc) - max(stamps)
    if age <= timedelta(hours=48):
        return 25
    if age <= timedelta(days=7):
        return 15
    return 5


def score(signal: Signal, evidence: list[Evidence]):
    agreeing_sources = {e.source for e in evidence if e.agrees}
    extraction = CONF_POINTS[signal.extraction_confidence]
    if signal.lat is None:  # location unresolved
        extraction -= 10
    provenance = 0
    if evidence:
        with_prov = sum(1 for e in evidence if e.link or e.node_metadata)
        provenance = round(15 * with_prov / len(evidence))
    breakdown = {
        "freshness": _freshness(evidence),
        "agreement": min(40, 10 * len(agreeing_sources)),
        "extraction": max(0, extraction),
        "provenance": provenance,
    }
    return min(100, sum(breakdown.values())), breakdown
