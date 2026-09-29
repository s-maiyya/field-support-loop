"""NASA FIRMS (VIIRS NRT) hotspot count near the signal location. Falls back to a cached sample."""
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

from .. import config
from ..models import Evidence, Signal

FIXTURE = Path(__file__).resolve().parent.parent.parent / "data" / "fixtures" / "firms_sample.csv"
HAZARDS = {"fire_burning", "armed_clash", "displacement"}
DAYS = 5  # FIRMS area API accepts a 1-5 day range
BOX = 0.5  # degrees


def _live(lat: float, lon: float) -> pd.DataFrame:
    bbox = f"{lon - BOX},{lat - BOX},{lon + BOX},{lat + BOX}"
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{config.FIRMS_MAP_KEY}/VIIRS_SNPP_NRT/{bbox}/{DAYS}"
    r = requests.get(url, timeout=config.TIMEOUT)
    r.raise_for_status()
    df = pd.read_csv(StringIO(r.text))
    if "latitude" not in df.columns:  # API returns plain-text errors with HTTP 200
        raise RuntimeError(r.text.strip()[:120])
    return df


def _fixture(lat: float, lon: float) -> pd.DataFrame:
    df = pd.read_csv(FIXTURE, dtype={"acq_time": str})
    # rebase dates so the newest sample row is 1 day old: the demo stays "fresh" on any day
    dates = pd.to_datetime(df["acq_date"])
    shift = (datetime.now(timezone.utc).date() - timedelta(days=1)) - dates.max().date()
    df["acq_date"] = (dates + pd.Timedelta(days=shift.days)).dt.strftime("%Y-%m-%d")
    return df[(df.latitude.sub(lat).abs() <= BOX) & (df.longitude.sub(lon).abs() <= BOX)]


def query(signal: Signal):
    """Returns (Evidence | None, note | None). None evidence = not applicable to this hazard/location."""
    if signal.hazard_type not in HAZARDS or signal.lat is None or signal.lon is None:
        return None, None

    note, cached = None, False
    try:
        if not config.FIRMS_MAP_KEY:
            raise RuntimeError("no FIRMS_MAP_KEY")
        df = _live(signal.lat, signal.lon)
    except Exception as e:  # noqa: BLE001 - never crash the demo
        cached = True
        if config.FIRMS_MAP_KEY:
            note = f"FIRMS live query failed ({type(e).__name__}); using cached sample"
        df = _fixture(signal.lat, signal.lon)

    n = len(df)
    ts = None
    if n:
        t = df["acq_time"].astype(str).str.zfill(4)
        ts = max(datetime.strptime(f"{d} {hm}", "%Y-%m-%d %H%M").replace(tzinfo=timezone.utc) for d, hm in zip(df["acq_date"], t)).isoformat()
    where = signal.location_name or "the reported location"
    summary = (
        f"{n} VIIRS thermal hotspot(s) within ±{BOX}° of {where} in the last {DAYS} days"
        if n else f"No VIIRS thermal hotspots within ±{BOX}° of {where} in the last {DAYS} days"
    )
    if cached:
        summary += " (cached sample)"
    return Evidence(
        source="firms",
        agrees=n > 0,
        summary=summary,
        timestamp=ts,
        link="https://firms.modaps.eosdis.nasa.gov/map/",
        cached=cached,
    ), note
