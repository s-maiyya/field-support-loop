"""Run all evidence sources in parallel; a failing source becomes a warning, never a crash."""
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from .models import Evidence, NodeResponse, Signal
from .sources import firms, tavily_news
from .sources.partner_nodes import NODES

WINDOW_DAYS = 14


def _node_evidence(resp: NodeResponse, signal: Signal) -> Evidence:
    where = signal.location_name
    if resp.count == 0:
        summary = f"No matching {signal.hazard_type} reports for {where} in the last {WINDOW_DAYS} days"
        return Evidence(source=resp.node_id, agrees=False, summary=summary,
                        withheld_fields=resp.withheld_fields, node_metadata=resp.metadata)
    if resp.reports:  # policy allows report contents
        texts = " | ".join(r["text"] for r in resp.reports if "text" in r)
        summary = f"{resp.count} matching report(s) (confidence: {resp.confidence}). {texts}"
    else:
        summary = f"{resp.count} matching report(s) (confidence: {resp.confidence}). Details withheld by owner (sharing policy)."
    return Evidence(source=resp.node_id, agrees=True, summary=summary, timestamp=resp.latest_report_date,
                    withheld_fields=resp.withheld_fields, node_metadata=resp.metadata)


def corroborate(signal: Signal):
    """Returns (evidence list, notes list, per-source timings)."""
    if not signal.location_name:  # nothing to check without a place
        return [], ["No location in the voice note - corroboration skipped."], {}

    since = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
    timings, notes = {}, []

    def timed(name, fn):
        t = time.time()
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            notes.append(f"{name} unavailable ({type(e).__name__}: {str(e)[:80]})")
            return None
        finally:
            timings[name] = round(time.time() - t, 2)

    def news():
        ev, note = tavily_news.query(signal)
        if note:
            notes.append(note)
        return ev

    def sat():
        ev, note = firms.query(signal)
        if note:
            notes.append(note)
        return [ev] if ev else []

    def node(key):
        return lambda: [_node_evidence(NODES[key].query(signal.admin2, signal.hazard_type, since), signal)]

    jobs = {"tavily": news, "firms": sat, "nrc_node": node("nrc_node"), "partner_b_node": node("partner_b_node")}
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {name: pool.submit(timed, name, fn) for name, fn in jobs.items()}
        evidence = []
        for name in jobs:  # stable order in the UI
            evidence += futures[name].result() or []
    return evidence, notes, timings
