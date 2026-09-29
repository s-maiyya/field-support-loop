"""Phase 1 key check: prints OK/FAIL per service. Never prints key values."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from clear import config

results = {}


def check(name):
    def deco(fn):
        try:
            print(f"\n== {name} ==")
            msg = fn()
            print(f"OK   {name}: {msg}")
            results[name] = True
        except Exception as e:  # noqa: BLE001 - report any failure, keep going
            print(f"FAIL {name}: {type(e).__name__}: {str(e)[:300]}")
            results[name] = False
        return fn

    return deco


@check("Nebius Token Factory")
def _nebius():
    if not config.NEBIUS_API_KEY:
        raise RuntimeError("NEBIUS_API_KEY is blank")
    url = config.NEBIUS_BASE_URL.rstrip("/") + "/models"
    r = requests.get(
        url,
        headers={"Authorization": f"Bearer {config.NEBIUS_API_KEY}"},
        params={"verbose": "true"},
        timeout=config.TIMEOUT,
    )
    r.raise_for_status()
    models = r.json().get("data", [])
    ids = sorted(m["id"] for m in models)
    # Heuristic: drop obvious non-text models
    skip = ("embed", "flux", "stable", "sdxl", "image", "whisper", "bge", "e5")
    text = [i for i in ids if not any(s in i.lower() for s in skip)]
    for i in text:
        print("   ", i)
    return f"{len(text)} text models ({len(ids)} total)"


@check("Tavily")
def _tavily():
    if not config.TAVILY_API_KEY:
        raise RuntimeError("TAVILY_API_KEY is blank")
    from tavily import TavilyClient

    res = TavilyClient(api_key=config.TAVILY_API_KEY).search(
        "Tawila displacement Sudan", max_results=1, topic="news", days=14
    )
    return f"{len(res.get('results', []))} result(s)"


@check("ElevenLabs")
def _eleven():
    if not config.ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY is blank")
    r = requests.get(
        "https://api.elevenlabs.io/v1/voices",
        headers={"xi-api-key": config.ELEVENLABS_API_KEY},
        timeout=config.TIMEOUT,
    )
    r.raise_for_status()
    voices = r.json().get("voices", [])
    for v in voices[:15]:
        labels = v.get("labels", {})
        print("   ", v["voice_id"], "-", v.get("name"), "|", labels.get("accent", ""), labels.get("gender", ""))
    return f"{len(voices)} voices"


@check("NASA FIRMS")
def _firms():
    if not config.FIRMS_MAP_KEY:
        return "key blank - fixture will be used (skipped)"
    r = requests.get(
        "https://firms.modaps.eosdis.nasa.gov/mapserver/mapkey_status/",
        params={"MAP_KEY": config.FIRMS_MAP_KEY},
        timeout=config.TIMEOUT,
    )
    r.raise_for_status()
    return f"status {r.status_code}: {r.text.strip()[:120]}"


print("\n== Summary ==")
for k, v in results.items():
    print(("OK   " if v else "FAIL ") + k)
sys.exit(0 if all(results.values()) else 1)
