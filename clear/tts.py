"""ElevenLabs text-to-speech for the audio brief. Cached on disk by text hash (.cache/ is gitignored)."""
import hashlib
from pathlib import Path

import requests

from . import config

CACHE = Path(__file__).resolve().parent.parent / ".cache" / "audio"


def synthesize(text: str) -> bytes:
    """Returns MP3 bytes. Raises on failure - the caller shows the text brief instead."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{hashlib.sha1(text.encode()).hexdigest()}.mp3"
    if path.exists():
        return path.read_bytes()
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{config.ELEVENLABS_VOICE_ID}",
        headers={"xi-api-key": config.ELEVENLABS_API_KEY, "Accept": "audio/mpeg"},
        json={"text": text, "model_id": "eleven_multilingual_v2"},
        timeout=config.TIMEOUT,
    )
    r.raise_for_status()
    path.write_bytes(r.content)
    return r.content
