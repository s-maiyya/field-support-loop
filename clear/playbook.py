"""Pre-approved actions + matching. Order in playbook.json = preference (first passing action wins)."""
import json
from pathlib import Path

from .models import PlaybookAction, Signal

PLAYBOOK_PATH = Path(__file__).resolve().parent.parent / "data" / "playbook.json"
ESCALATION_EUR = 20000
REQUEST_INFO_BELOW = 40

REQUEST_INFO = PlaybookAction(
    id="request_info",
    name="Request more information",
    hazards=[],
    min_trust=0,
    min_severity=1,
    cost_band_eur=[0, 0],
    approver_level="field",
    message_template="REQUEST to field coordinator: please send exact location, number of people affected and time frame ({hazard}).",
)


def load() -> list[PlaybookAction]:
    return [PlaybookAction(**a) for a in json.loads(PLAYBOOK_PATH.read_text())]


def choose(signal: Signal, trust: int, min_trust_adjust: dict | None = None):
    """Returns (action, escalate). min_trust_adjust: {hazard: +points} learned from rejections (Phase 6)."""
    if trust < REQUEST_INFO_BELOW:
        return REQUEST_INFO, False
    adjust = (min_trust_adjust or {}).get(signal.hazard_type, 0)
    for a in load():
        if signal.hazard_type in a.hazards and signal.severity >= a.min_severity and trust >= a.min_trust + adjust:
            return a, a.cost_band_eur[1] > ESCALATION_EUR
    return REQUEST_INFO, False  # nothing in the playbook is safe to recommend at this trust level


def render_message(action: PlaybookAction, signal: Signal, approver: str = "field coordinator") -> str:
    """Fill the action's message template (used as the 'simulated dispatch' text)."""
    return action.message_template.format(
        location=signal.location_name or "the reported area",
        admin2=signal.admin2 or "unknown",
        hazard=signal.hazard_type.replace("_", " "),
        people=signal.people_affected_est if signal.people_affected_est is not None else "not stated",
        needs=", ".join(signal.needs) or "not stated",
        approver=approver,
    )
