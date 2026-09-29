"""Environment loading. Never log values."""
import os

from dotenv import load_dotenv

load_dotenv()

TIMEOUT = 20

NEBIUS_API_KEY = os.getenv("NEBIUS_API_KEY", "")
NEBIUS_BASE_URL = os.getenv("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/")
NEBIUS_MODEL = os.getenv("NEBIUS_MODEL", "")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "")
FIRMS_MAP_KEY = os.getenv("FIRMS_MAP_KEY", "")
