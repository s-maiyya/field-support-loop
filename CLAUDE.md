# CLEAR Field Loop – Hackathon Build Spec

You (Claude Code) are building a 4-hour hackathon prototype. Scope discipline matters more than polish.
Build phases IN ORDER. After each phase, stop, run the phase's check, and report to me before continuing.
If something takes more than 20 minutes to get working, use the listed fallback and move on.

## What we're building (one sentence)
A field coordinator in Sudan sends a voice note → it becomes a structured signal → it is corroborated
against web news, satellite fire data and two simulated partner-organisation nodes → the system
recommends ONE pre-approved action and reads a short audio brief → a human approves, rejects or defers,
and that decision is logged.

**Headline metric shown on screen:** seconds from voice note upload to actionable alert.

## Non-goals (do NOT build)
Auth/login, real database server, Kubernetes, Grafana, embeddings/RAG, anomaly detection on time
series, ACLED, Earth Engine/CHIRPS, precision/recall evaluation, multi-user, background workers.

## Stack
- Python 3.11, Streamlit (single app), `openai` SDK, `tavily-python`, `elevenlabs` SDK, `requests`,
  `pandas`, `folium` + `streamlit-folium`, `python-dotenv`, `pydantic`.
- Storage: SQLite file `data/decisions.db` + JSON fixture files. Nothing else.
- Deploy: Docker container on a Nebius CPU VM (Phase 7).

## Environment (.env – never commit it; create .env.example with blank values)
```
NEBIUS_API_KEY=
NEBIUS_BASE_URL=https://api.tokenfactory.nebius.com/v1/
NEBIUS_MODEL=            # fill after Phase 1 model check
TAVILY_API_KEY=
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=     # pick any stock voice in Phase 1
FIRMS_MAP_KEY=           # optional; if blank, use fixture
```

## Repo layout
```
app.py                  # Streamlit UI
clear/
  config.py             # env loading
  stt.py                # ElevenLabs speech-to-text
  tts.py                # ElevenLabs text-to-speech
  extract.py            # Token Factory: transcript -> Signal JSON
  corroborate.py        # runs all sources, returns Evidence list
  sources/
    tavily_news.py
    firms.py
    partner_nodes.py    # simulated federation
  score.py              # trust score (rules, no ML)
  playbook.py           # pre-approved actions + matching rules
  brief.py              # alert text + audio brief script
  store.py              # SQLite decision log
  models.py             # pydantic models
data/
  playbook.json
  places.json           # locality -> lat/lon/admin2 lookup
  nodes/nrc.json
  nodes/partner_b.json
  fixtures/firms_sample.csv
  voice_notes/          # 3 demo audio files
scripts/
  check_keys.py
  make_voice_notes.py
Dockerfile
README.md
```

## Data models (pydantic)
- **Signal**: `location_name`, `admin2`, `lat`, `lon`, `hazard_type` (one of: `displacement`,
  `armed_clash`, `fire_burning`, `flood`, `market_shock`, `disease`, `other`), `severity` (1–3),
  `people_affected_est` (int or null), `needs` (list[str]), `time_reference` (str),
  `extraction_confidence` (low/medium/high), `quotes` (dict field -> exact transcript excerpt).
- **Evidence**: `source` (tavily/firms/nrc_node/partner_b_node), `agrees` (bool), `summary` (str),
  `timestamp`, `link` (str or null), `withheld_fields` (list[str]).
- **Alert**: `signal`, `evidence`, `trust_score` (0–100), `trust_breakdown` (dict), `action`
  (playbook item or null), `escalate` (bool), `brief_text`, `latency_seconds`.
- **Decision**: `alert_id`, `decision` (approve/reject/defer), `reason`, `decided_at`,
  `seconds_to_decision`.

## Git
- In Phase 1, run `git init` (if not already a repo) and create `.gitignore` BEFORE the first commit,
  containing at least: `.env`, `.venv/`, `__pycache__/`, `*.pyc`, `data/decisions.db`, `.cache/`,
  `.streamlit/secrets.toml`, `.DS_Store`.
- Before every commit, run `git status` and confirm `.env` is not staged. Never commit secrets,
  API keys or tokens, including in README examples or logs.
- Commit after each phase's check passes, one commit per phase, message format:
  `phase N: <what now works>` (e.g. `phase 3: voice note -> validated Signal JSON`).
- Small fixes within a phase can be separate commits (`fix: ...`). Don't bundle unrelated changes.
- Commit the demo voice notes and JSON fixtures (the demo depends on them).
- Do not push, add remotes, create branches or rewrite history unless I ask. If I ask to push to
  GitHub, first confirm the repo visibility with me.
- If a phase goes badly, suggest `git restore` / reverting to the last phase commit rather than
  patching on top of a broken state.

## Phase 1 – Setup & key check (target 20 min)
- `git init` + `.gitignore` (see Git section), first commit of the scaffold.
- Scaffold repo, requirements.txt, .env.example, config.py.
- `scripts/check_keys.py`: (a) call `GET {NEBIUS_BASE_URL}models`, print text models;
  (b) one tiny Tavily search; (c) list ElevenLabs voices; (d) FIRMS ping if key present.
- Pick a Token Factory instruct model that handles JSON output well (prefer a Llama 3.3 70B,
  Qwen 2.5/3 72B-class, or similar from the list). Tell me which and why; I'll set NEBIUS_MODEL.
- **Check:** script prints OK for each service.

## Phase 2 – Demo voice notes (target 15 min)
`scripts/make_voice_notes.py` generates 3 notes via ElevenLabs TTS (I may replace with my own recordings):
1. **strong.mp3** – "This is Amal, NRC coordinator in Tawila. Since last night around four hundred
   families have arrived from villages west of El Fasher. People say villages were burned. Main needs
   are shelter kits and water. We have NFI stock in the Tawila warehouse."
2. **weak.mp3** – "Quick update from Kutum. Some traders say sorghum prices jumped a lot this week,
   maybe double, not confirmed yet. Just flagging."
3. **ambiguous.mp3** – "Hearing there may be movement of people toward the border area, not sure
   how many or exactly where. Will update."

Scenario design: #1 should end up corroborated (high trust → action), #2 medium (defer),
#3 too vague (no action, request info). Make the fixtures below support that.

## Phase 3 – Core pipeline, no UI (target 45 min)
- `stt.py`: ElevenLabs speech-to-text (current Scribe model) → transcript text.
- `extract.py`: Token Factory chat completion, temperature 0, JSON mode if the model supports it,
  else strict "return only JSON" + pydantic validation with one retry. Rules in the system prompt:
  never invent facts, null if not stated, every non-null field needs a supporting quote.
  Resolve lat/lon/admin2 from `data/places.json` (include Tawila, El Fasher, Kutum, Kabkabiya,
  Mellit, Nyala, Adre, Geneina + a few more North/West/South Darfur localities). Unknown → null.
- `pipeline.run(audio_path) -> Alert` (corroboration/scoring stubbed for now).
- **Check:** CLI `python -m clear.pipeline data/voice_notes/strong.mp3` prints a valid Signal.

## Phase 4 – Corroboration, federation, scoring, playbook (target 60 min)
**Tavily** (`tavily_news.py`): search news from the last 7–14 days for
`"{location} {hazard} Sudan"`; ask the LLM for a one-line agree/disagree judgement per result;
keep top 3 with links.

**FIRMS** (`firms.py`): only for hazard `fire_burning` / `armed_clash` / `displacement`. Query the
FIRMS area API (VIIRS NRT, bbox ±0.5° around lat/lon, last 3–7 days) if FIRMS_MAP_KEY set; else read
`data/fixtures/firms_sample.csv` (create ~10 plausible hotspot rows near El Fasher/Tawila, and
label the UI "cached sample"). Evidence = count of hotspots in bbox.

**Simulated federation** (`partner_nodes.py`) – this must look deliberate:
- Each node = a JSON file with `metadata` (owner org, license, sharing_policy) and `reports`
  (8–12 fake field reports with locality, hazard, date, text, beneficiary_count).
- Uniform contract per node: `query(admin2, hazard, since) -> NodeResponse` and `metadata()`.
- Sharing policy is enforced INSIDE the node before returning:
  - `nrc` node: full sharing (count + summaries).
  - `partner_b` node: count + confidence only; text, exact location and beneficiary counts
    withheld → set `withheld_fields`.
- Fixtures: both nodes have 1–2 matching reports for Tawila displacement; partner_b has 1 unconfirmed
  price report for Kutum; nothing for the ambiguous note.

**Trust score** (`score.py`, simple and explainable, return the breakdown):
- Freshness 0–25 (newest agreeing evidence ≤48h = 25, ≤7d = 15, else 5)
- Agreement 0–40 (number of independent agreeing sources × 10, capped at 40 over tavily/firms/nrc/partner_b)
- Extraction quality 0–20 (high=20, medium=10, low=0; −10 if location unresolved)
- Provenance 0–15 (share of evidence items with a link or node metadata)

**Playbook** (`data/playbook.json`, 5 actions), each with: `id`, `name`, `hazards`, `min_trust`,
`min_severity`, `cost_band_eur`, `approver_level` (field / country_director), `message_template`.
Examples: release pre-positioned NFI/shelter kits; emergency multipurpose cash top-up; send SMS early
warning to community focal points; request market monitoring visit; request verification mission.
Matching: highest-value action whose conditions pass. `escalate = true` if cost band upper bound
> €20,000 → UI shows "needs country director approval". If trust < 40 → action "request more
information" and no audio action recommendation.

**Brief** (`brief.py`): LLM writes ≤60 words: what, where, how confident, recommended action, cost band.
No new facts beyond Signal + Evidence.

- **Check:** all 3 notes produce the intended outcomes (act / defer / request info). Show me the three Alerts.

## Phase 5 – Streamlit UI (target 45 min)
Single page, mobile-friendly widths.
1. Top bar: title "CLEAR Field Loop – Sudan (prototype)"; sidebar selector of the 3 demo notes + file upload.
2. Big timer metric: "Voice note → actionable alert: XX s".
3. Alert card: one-line headline, severity, trust score with the breakdown as small bars,
   recommended action + cost band, escalation badge if needed.
4. Audio player with the TTS brief.
5. Evidence panel: one row per source with agree/disagree icon, summary, link; partner_b row shows
   "details withheld by owner (sharing policy)" plus its metadata. This is the federation moment.
6. Transcript with extracted fields highlighted/listed next to their supporting quotes.
7. Folium map with one pin (skip if short on time).
8. Buttons: Approve / Reject / Defer + one-line reason → saved to SQLite; show confirmation with the
   templated action message (e.g. the SMS text) as "simulated dispatch".
9. Small "Decision log" table at the bottom with seconds-to-decision per alert.

Show progress steps while running (transcribing → structuring → corroborating → scoring).
Cache results per file so a re-run in the demo is instant; add a "re-run live" toggle.

## Phase 6 – Feedback loop (target 15 min)
- On reject, reason is stored. Add a "Lessons" expander: counts of rejects per hazard + reasons.
- One visible rule: if ≥2 rejections for a hazard, that hazard's `min_trust` in the playbook is raised
  by 10 for the session (show "threshold adjusted from feedback"). Keep it simple and honest.

## Phase 7 – Deploy on Nebius (target 30 min)
- Dockerfile (python:3.11-slim, streamlit on 0.0.0.0:8501, healthcheck).
- README section "Deploy to Nebius VM": steps for me to create a small CPU VM, install Docker,
  copy repo + .env, `docker build` / `docker run -p 8501:8501 --env-file .env`, open the port.
  I'll run the Nebius console steps myself; you write the commands.
- Fallback: if deployment isn't working by the 3:30 mark, demo locally.

## Phase 8 – Demo assets (target 15 min)
- README: problem, user, decision, metric, architecture diagram (Mermaid), what's simulated vs real,
  what's next (real CLEAR federation layer, Arabic briefs, WhatsApp channel, ACLED/HDX/IOM DTM feeds,
  precision/recall on historical windows).
- `DEMO.md`: 3-minute script – strong note (approve), weak note (defer), ambiguous note
  (system asks for more info rather than guessing).

## Cut order if behind schedule
1. Map  2. Feedback-loop threshold rule (keep logging)  3. FIRMS live (use fixture)
4. TTS audio (show text brief)  5. Nebius deploy (demo locally).
Never cut: extraction with quotes, evidence panel with the withheld partner row, approve/reject/defer + log, latency metric.

## Coding conventions
- Every external call: timeout 20 s, try/except, graceful fallback message in the UI – the demo must never crash.
- Log each pipeline step's duration.
- No secrets in code or logs.
