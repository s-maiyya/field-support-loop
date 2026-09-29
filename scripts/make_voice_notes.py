"""Phase 2: generate the 3 demo voice notes with ElevenLabs TTS."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests

from clear import config

NOTES = {
    "strong": (
        "This is Amal, NRC coordinator in Tawila. Since last night around four hundred families "
        "have arrived from villages west of El Fasher. People say villages were burned. Main needs "
        "are shelter kits and water. We have NFI stock in the Tawila warehouse."
    ),
    "weak": (
        "Quick update from Kutum. Some traders say sorghum prices jumped a lot this week, "
        "maybe double, not confirmed yet. Just flagging."
    ),
    "ambiguous": (
        "Hearing there may be movement of people toward the border area, not sure how many "
        "or exactly where. Will update."
    ),
}

out_dir = ROOT / "data" / "voice_notes"
out_dir.mkdir(parents=True, exist_ok=True)

for name, text in NOTES.items():
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{config.ELEVENLABS_VOICE_ID}",
        headers={"xi-api-key": config.ELEVENLABS_API_KEY, "Accept": "audio/mpeg"},
        json={"text": text, "model_id": "eleven_multilingual_v2"},
        timeout=60,
    )
    if r.status_code != 200:
        print(f"FAIL {name}: {r.status_code} {r.text[:200]}")
        sys.exit(1)
    path = out_dir / f"{name}.mp3"
    path.write_bytes(r.content)
    print(f"OK   {path.relative_to(ROOT)} ({len(r.content) // 1024} KB)")
