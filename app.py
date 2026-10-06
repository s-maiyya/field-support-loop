"""Field Support Loop (prototype). Streamlit UI."""
import hashlib
import html
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import folium
import streamlit as st
from streamlit_folium import st_folium

from clear import brief, pipeline, playbook, store, tts
from clear.models import Alert, Decision

ROOT = Path(__file__).resolve().parent
NOTES_DIR = ROOT / "data" / "voice_notes"
CACHE_DIR = ROOT / ".cache"
(CACHE_DIR / "alerts").mkdir(parents=True, exist_ok=True)
(CACHE_DIR / "uploads").mkdir(parents=True, exist_ok=True)

DEMO_NOTES = {
    "1 · Tawila arrivals (strong)": "strong.mp3",
    "2 · Kutum sorghum prices (weak)": "weak.mp3",
    "3 · Border movement (ambiguous)": "ambiguous.mp3",
}
SOURCE_LABELS = {
    "tavily": "Web news (Tavily)",
    "firms": "NASA FIRMS satellite",
    "nrc_node": "NRC node",
    "partner_b_node": "Partner B node",
}
BAR_MAX = {"freshness": 25, "agreement": 40, "extraction": 20, "provenance": 15}
SEVERITY_LABEL = {1: "Low", 2: "Moderate", 3: "High"}

st.set_page_config(page_title="Field Support Loop", page_icon="📡", layout="centered")
st.title("Field Support Loop (prototype)")


# ---------- helpers ----------
def _file_key(name: str, data: bytes) -> str:
    return hashlib.sha1(name.encode() + data).hexdigest()[:16]


def run_or_load(audio_path: Path, key: str, live: bool) -> tuple[Alert, bool]:
    """Returns (alert, from_cache). Results are cached per file so a demo re-run is instant."""
    cache_file = CACHE_DIR / "alerts" / f"{key}.json"
    if not live and cache_file.exists():
        return Alert.model_validate_json(cache_file.read_text()), True
    with st.status("Running pipeline…", expanded=True) as status:
        labels = {
            "transcribing": "🎙️ Transcribing voice note",
            "structuring": "🧩 Structuring into a signal",
            "corroborating": "🔎 Corroborating: news · satellite · partner nodes",
            "scoring": "⚖️ Scoring trust & matching playbook",
            "briefing": "📝 Writing brief",
        }
        alert = pipeline.run(str(audio_path), on_step=lambda s: st.write(labels.get(s, s)))
        status.update(label=f"Done in {alert.latency_seconds:.1f} s", state="complete", expanded=False)
    cache_file.write_text(alert.model_dump_json())
    return alert, False


def apply_feedback(alert: Alert) -> Alert:
    """Re-choose the action with thresholds raised by this session's rejections; refresh the brief if it changes."""
    adjust = playbook.adjustments(st.session_state.get("rejects", []))
    action, escalate = playbook.choose(alert.signal, alert.trust_score, adjust)
    if action.id == (alert.action.id if alert.action else None) and escalate == alert.escalate:
        return alert
    note = f"feedback: threshold adjusted from feedback (+{playbook.ADJUSTMENT_POINTS} min trust for {alert.signal.hazard_type} after repeated rejections)"
    new = alert.model_copy(update={"action": action, "escalate": escalate, "notes": alert.notes + [note]})
    new.brief_text = brief.write_brief(new)
    return new


def highlight_transcript(transcript: str, quotes: dict) -> str:
    """HTML-escape the transcript, then mark the supporting quotes."""
    out = html.escape(transcript)
    for q in sorted({q for v in quotes.values() for q in v.split("; ")}, key=len, reverse=True):
        eq = html.escape(q)
        i = out.lower().find(eq.lower())
        if i >= 0 and "<mark" not in out[i:i + len(eq)]:
            out = out[:i] + f"<mark>{out[i:i + len(eq)]}</mark>" + out[i + len(eq):]
    return out


# ---------- sidebar ----------
with st.sidebar:
    st.header("Voice note")
    choice = st.selectbox("Demo notes", list(DEMO_NOTES))
    upload = st.file_uploader("…or upload audio", type=["mp3", "wav", "m4a", "ogg", "webm"])
    live = st.toggle("Re-run live (ignore cache)", value=False)
    if upload is not None:
        data = upload.getvalue()
        audio_path = CACHE_DIR / "uploads" / upload.name
        audio_path.write_bytes(data)
        key = _file_key(upload.name, data)
    else:
        audio_path = NOTES_DIR / DEMO_NOTES[choice]
        key = _file_key(audio_path.name, audio_path.read_bytes())
    st.audio(str(audio_path))
    run_clicked = st.button("Analyse voice note", type="primary", width="stretch")

# ---------- run ----------
if run_clicked:
    try:
        alert, cached = run_or_load(audio_path, key, live)
        alert = alert.model_copy(update={"alert_id": uuid.uuid4().hex[:8]})  # each run = a new decision item
        alert = apply_feedback(alert)
        st.session_state.update(alert=alert, cached=cached, shown_at=time.time(), audio=None, decision=None)
        try:
            st.session_state.audio = tts.synthesize(alert.brief_text)
        except Exception as e:  # noqa: BLE001 - brief text is still shown
            st.session_state.audio_error = f"Audio brief unavailable ({type(e).__name__}); showing text brief."
            st.session_state.audio = None
    except Exception as e:  # noqa: BLE001 - the demo must never crash
        st.error(f"Could not process this voice note ({type(e).__name__}: {str(e)[:120]}). Try again or pick another note.")

alert: Alert | None = st.session_state.get("alert")
if alert is None:
    st.info("Pick a demo voice note in the sidebar and press **Analyse voice note**.")
else:
    s = alert.signal

    # 2. headline metric
    st.markdown(
        f"<div style='text-align:center;padding:.6rem 0'>"
        f"<div style='font-size:.9rem;opacity:.7'>Voice note → actionable alert</div>"
        f"<div style='font-size:3.2rem;font-weight:700;line-height:1.1'>{alert.latency_seconds:.1f} s</div></div>",
        unsafe_allow_html=True,
    )
    if st.session_state.get("cached"):
        st.caption("Cached result – this is the time measured when the note was first processed live. Toggle “Re-run live” to re-measure.")
    for n in alert.notes:
        if n.startswith("feedback:"):
            st.info("🔁 " + n[len("feedback: "):].capitalize())
        else:
            st.warning(n)

    # 3. alert card
    with st.container(border=True):
        st.subheader(alert.headline)
        c1, c2 = st.columns(2)
        c1.metric("Severity", f"{s.severity}/3 · {SEVERITY_LABEL[s.severity]}")
        c2.metric("Trust score", f"{alert.trust_score}/100")
        for name, mx in BAR_MAX.items():
            v = alert.trust_breakdown.get(name, 0)
            st.progress(min(1.0, v / mx), text=f"{name.capitalize()} {v}/{mx}")
        act = alert.action
        if act and act.id == "request_info":
            st.warning("**No action recommended – trust too low.** Recommended: request more information from the coordinator.")
        elif act:
            st.success(f"**Recommended action:** {act.name}  \nCost band: €{act.cost_band_eur[0]:,}–€{act.cost_band_eur[1]:,}")
        if alert.escalate:
            st.error("⬆️ Needs country director approval (cost band above €20,000)")

    # 4. audio brief
    st.markdown("##### Audio brief")
    if st.session_state.get("audio"):
        st.audio(st.session_state.audio, format="audio/mp3")
    elif st.session_state.get("audio_error"):
        st.caption(st.session_state.audio_error)
    st.write(alert.brief_text)

    # 5. evidence
    st.markdown("##### Evidence")
    if not alert.evidence:
        st.caption("No sources were queried (no location in the voice note).")
    for e in alert.evidence:
        with st.container(border=True):
            label = SOURCE_LABELS.get(e.source, e.source)
            st.markdown(f"{'✅' if e.agrees else '❌'} **{label}**" + (" · _cached sample_" if e.cached else ""))
            if e.node_metadata and e.agrees and e.withheld_fields:
                st.markdown(f"🔒 _Details withheld by owner (sharing policy)_ — withheld: `{', '.join(e.withheld_fields)}`")
                st.caption(e.summary.split(". Details")[0] + ".")
            else:
                st.write(e.summary)
            if e.node_metadata:
                m = e.node_metadata
                st.caption(f"Owner: {m['owner']} · License: {m['license']} · Sharing policy: {m['sharing_policy']['description']}")
            if e.link:
                st.markdown(f"[source link]({e.link})")

    # 6. transcript + extracted fields
    st.markdown("##### Transcript")
    st.markdown(highlight_transcript(alert.transcript, s.quotes), unsafe_allow_html=True)
    rows = [
        ("Location", s.location_name, s.quotes.get("location_name")),
        ("Admin 2 (gazetteer)", s.admin2, None),
        ("Hazard", s.hazard_type, s.quotes.get("hazard_type")),
        ("Severity", s.severity, s.quotes.get("severity")),
        ("People affected (as stated)", s.people_affected_est, s.quotes.get("people_affected_est")),
        ("Needs", ", ".join(s.needs) or None, s.quotes.get("needs")),
        ("Time reference", s.time_reference, s.quotes.get("time_reference")),
        ("Extraction confidence", s.extraction_confidence, None),
    ]
    st.table({"Field": [r[0] for r in rows], "Value": [str(r[1]) if r[1] is not None else "—" for r in rows],
              "Supporting quote": [r[2] or "—" for r in rows]})

    # 7. map
    if s.lat is not None:
        m = folium.Map(location=[s.lat, s.lon], zoom_start=8, tiles="OpenStreetMap")
        folium.Marker([s.lat, s.lon], tooltip=f"{s.location_name} ({s.admin2})").add_to(m)
        st_folium(m, height=280, use_container_width=True, returned_objects=[])

    # 8. decision
    st.markdown("##### Decision")
    done = st.session_state.get("decision")
    if done:
        d, msg = done
        st.success(f"Decision logged: **{d.decision}** after {d.seconds_to_decision:.0f} s.")
        if msg:
            st.code(msg, language=None)
            st.caption("Simulated dispatch – nothing was actually sent.")
    else:
        reason = st.text_input("Reason (one line)", key=f"reason_{alert.alert_id}")
        b1, b2, b3 = st.columns(3)
        picked = None
        if b1.button("✅ Approve", width="stretch"):
            picked = "approve"
        if b2.button("❌ Reject", width="stretch"):
            picked = "reject"
        if b3.button("⏸️ Defer", width="stretch"):
            picked = "defer"
        if picked:
            d = Decision(
                alert_id=alert.alert_id, decision=picked, reason=reason.strip(),
                decided_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                seconds_to_decision=round(time.time() - st.session_state.shown_at, 1),
            )
            if picked == "reject":
                st.session_state.setdefault("rejects", []).append({"hazard": s.hazard_type, "reason": reason.strip()})
            try:
                store.save(d, alert)
            except Exception as e:  # noqa: BLE001
                st.error(f"Could not save decision ({type(e).__name__}).")
            msg = None
            if picked == "approve" and alert.action:
                level = "country director" if alert.escalate else "field coordinator"
                msg = playbook.render_message(alert.action, s, approver=level)
            st.session_state.decision = (d, msg)
            st.rerun()

# Lessons (feedback loop)
with st.expander("Lessons from rejections (this session)"):
    rejects = st.session_state.get("rejects", [])
    adjust = playbook.adjustments(rejects)
    if not rejects:
        st.caption("No rejections yet. After 2 rejections of the same hazard, its minimum trust threshold rises by "
                   f"{playbook.ADJUSTMENT_POINTS} points for the rest of the session.")
    else:
        by_hazard = {}
        for r in rejects:
            by_hazard.setdefault(r["hazard"], []).append(r["reason"] or "(no reason given)")
        st.table({
            "Hazard": list(by_hazard),
            "Rejections": [len(v) for v in by_hazard.values()],
            "Reasons": ["; ".join(v) for v in by_hazard.values()],
            "Threshold": [f"min trust +{adjust[h]} (adjusted from feedback)" if h in adjust else "unchanged" for h in by_hazard],
        })

# 9. decision log
st.markdown("##### Decision log")
try:
    log = store.all_decisions()
    if log.empty:
        st.caption("No decisions yet.")
    else:
        st.dataframe(log, width="stretch", hide_index=True)
except Exception as e:  # noqa: BLE001
    st.caption(f"Decision log unavailable ({type(e).__name__}).")
