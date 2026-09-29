"""ElevenLabs speech-to-text (Scribe)."""
import requests

from . import config


def transcribe(audio_path: str) -> str:
    with open(audio_path, "rb") as f:
        r = requests.post(
            "https://api.elevenlabs.io/v1/speech-to-text",
            headers={"xi-api-key": config.ELEVENLABS_API_KEY},
            data={"model_id": "scribe_v1"},
            files={"file": f},
            timeout=config.TIMEOUT,
        )
    r.raise_for_status()
    return r.json()["text"].strip()
