"""Pydantic models shared across the pipeline."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

HazardType = Literal[
    "displacement", "armed_clash", "fire_burning", "flood", "market_shock", "disease", "other"
]


class Signal(BaseModel):
    location_name: Optional[str] = None
    admin2: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    hazard_type: HazardType = "other"
    severity: int = Field(1, ge=1, le=3)
    people_affected_est: Optional[int] = None
    needs: list[str] = Field(default_factory=list)
    time_reference: Optional[str] = None
    extraction_confidence: Literal["low", "medium", "high"] = "low"
    quotes: dict[str, str] = Field(default_factory=dict)  # field -> exact transcript excerpt


class Evidence(BaseModel):
    source: Literal["tavily", "firms", "nrc_node", "partner_b_node"]
    agrees: bool
    summary: str
    timestamp: Optional[str] = None
    link: Optional[str] = None
    withheld_fields: list[str] = Field(default_factory=list)
    node_metadata: Optional[dict] = None  # owner org / license / sharing policy for federated nodes
    cached: bool = False  # True when built from a cached sample instead of a live call


class NodeResponse(BaseModel):
    """What a federated node returns AFTER applying its own sharing policy."""

    node_id: str
    owner: str
    count: int
    confidence: Optional[str] = None
    latest_report_date: Optional[str] = None
    reports: Optional[list[dict]] = None  # None when the policy withholds report contents
    withheld_fields: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class PlaybookAction(BaseModel):
    id: str
    name: str
    hazards: list[str]
    min_trust: int
    min_severity: int
    cost_band_eur: list[int]  # [low, high]
    approver_level: Literal["field", "country_director"]
    message_template: str


class Alert(BaseModel):
    alert_id: str = ""
    transcript: str = ""
    signal: Signal
    evidence: list[Evidence] = Field(default_factory=list)
    trust_score: int = 0
    trust_breakdown: dict[str, int] = Field(default_factory=dict)
    action: Optional[PlaybookAction] = None
    escalate: bool = False
    headline: str = ""
    brief_text: str = ""
    notes: list[str] = Field(default_factory=list)  # warnings, e.g. a source that timed out
    latency_seconds: float = 0.0
    step_timings: dict[str, float] = Field(default_factory=dict)


class Decision(BaseModel):
    alert_id: str
    decision: Literal["approve", "reject", "defer"]
    reason: str = ""
    decided_at: str
    seconds_to_decision: float
