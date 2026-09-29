"""Simulated federation: each node is a JSON file that enforces its OWN sharing policy before answering.

Uniform contract: Node.metadata() and Node.query(admin2, hazard, since) -> NodeResponse.
The caller never sees fields the node's policy withholds.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..models import NodeResponse

NODES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "nodes"
CONF_ORDER = ["low", "medium", "high"]
# report field -> sharing-policy key that must be present for it to leave the node
FIELD_POLICY = {
    "text": "text",
    "exact_location": "exact_location",
    "beneficiary_count": "beneficiary_count",
}


class Node:
    def __init__(self, path: Path):
        data = json.loads(path.read_text())
        self._meta = data["metadata"]
        now = datetime.now(timezone.utc)
        self._reports = []
        for r in data["reports"]:
            r = dict(r)
            r["timestamp"] = now - timedelta(hours=r.pop("hours_ago"))
            self._reports.append(r)

    def metadata(self) -> dict:
        return self._meta

    def query(self, admin2, hazard: str, since: datetime) -> NodeResponse:
        shares = set(self._meta["sharing_policy"]["shares"])
        matches = [
            r for r in self._reports
            if admin2 and r["admin2"] == admin2 and r["hazard"] == hazard and r["timestamp"] >= since
        ]
        withheld = [f for f, key in FIELD_POLICY.items() if key not in shares]

        confidence = None
        if matches and "confidence" in shares:
            confidence = max((r["confidence"] for r in matches), key=CONF_ORDER.index)
        latest = None
        if matches and "latest_report_date" in shares:
            latest = max(r["timestamp"] for r in matches).isoformat()

        # Enforcement happens here: withheld fields are never copied into the response.
        reports = None
        if matches and any(k in shares for k in FIELD_POLICY.values()):
            reports = []
            for r in sorted(matches, key=lambda x: x["timestamp"], reverse=True):
                out = {"locality": r["locality"], "date": r["timestamp"].isoformat()}
                for f, key in FIELD_POLICY.items():
                    if key in shares:
                        out[f] = r[f]
                reports.append(out)

        return NodeResponse(
            node_id=self._meta["node_id"],
            owner=self._meta["owner"],
            count=len(matches) if "count" in shares else 0,
            confidence=confidence,
            latest_report_date=latest,
            reports=reports,
            withheld_fields=withheld,
            metadata=self._meta,
        )


NRC = Node(NODES_DIR / "nrc.json")
PARTNER_B = Node(NODES_DIR / "partner_b.json")
NODES = {"nrc_node": NRC, "partner_b_node": PARTNER_B}
