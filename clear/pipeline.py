"""End-to-end pipeline: audio -> transcript -> Signal -> evidence -> trust -> action -> brief."""
import sys
import time
import uuid

from . import brief, playbook
from .corroborate import corroborate
from .extract import extract_signal
from .models import Alert
from .score import score
from .stt import transcribe


def run(audio_path: str, min_trust_adjust: dict | None = None, on_step=None) -> Alert:
    """on_step(name) is called as each stage starts (used by the UI progress display)."""
    t0 = time.time()
    timings = {}

    def step(name):
        if on_step:
            on_step(name)

    def timed(name, fn):
        t = time.time()
        out = fn()
        timings[name] = round(time.time() - t, 2)
        print(f"[pipeline] {name} {timings[name]}s")
        return out

    step("transcribing")
    transcript = timed("transcribe", lambda: transcribe(audio_path))
    step("structuring")
    signal = timed("extract", lambda: extract_signal(transcript))
    step("corroborating")
    evidence, notes, src_timings = timed("corroborate", lambda: corroborate(signal))
    step("scoring")
    trust, breakdown = score(signal, evidence)
    action, escalate = playbook.choose(signal, trust, min_trust_adjust)

    alert = Alert(
        alert_id=uuid.uuid4().hex[:8],
        transcript=transcript,
        signal=signal,
        evidence=evidence,
        trust_score=trust,
        trust_breakdown=breakdown,
        action=action,
        escalate=escalate,
        notes=notes,
    )
    alert.headline = brief.headline(alert)
    step("briefing")
    alert.brief_text = timed("brief", lambda: brief.write_brief(alert))
    alert.latency_seconds = round(time.time() - t0, 2)
    alert.step_timings = {**timings, **{f"src:{k}": v for k, v in src_timings.items()}}
    return alert


def print_alert(a: Alert) -> None:
    s = a.signal
    print(f"\nHEADLINE : {a.headline}")
    print(f"SIGNAL   : {s.location_name}/{s.admin2} | {s.hazard_type} | sev {s.severity} | people {s.people_affected_est} | conf {s.extraction_confidence}")
    print(f"TRUST    : {a.trust_score}/100  {a.trust_breakdown}")
    for e in a.evidence:
        mark = "AGREES " if e.agrees else "no     "
        w = f"  [withheld: {', '.join(e.withheld_fields)}]" if e.withheld_fields and e.agrees else ""
        print(f"  {e.source:15s} {mark} {e.summary[:150]}{w}")
    act = a.action
    if act:
        print(f"ACTION   : {act.name}  cost €{act.cost_band_eur[0]}-{act.cost_band_eur[1]}  escalate={a.escalate}")
    print(f"BRIEF    : {a.brief_text}  ({len(a.brief_text.split())} words)")
    for n in a.notes:
        print(f"NOTE     : {n}")
    print(f"LATENCY  : {a.latency_seconds}s  {a.step_timings}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python -m clear.pipeline <audio_path>")
    alert = run(sys.argv[1])
    print_alert(alert)
