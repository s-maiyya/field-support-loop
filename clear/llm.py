"""Shared Token Factory client + helpers."""
import json
import re

import openai
from openai import OpenAI

from . import config

_client = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=config.NEBIUS_API_KEY, base_url=config.NEBIUS_BASE_URL, timeout=config.TIMEOUT)
    return _client


def chat(system: str, user: str, max_tokens: int = 600, json_mode: bool = False) -> str:
    kwargs = dict(
        model=config.NEBIUS_MODEL,
        temperature=0,
        max_tokens=max_tokens,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    if json_mode:
        try:
            r = get_client().chat.completions.create(response_format={"type": "json_object"}, **kwargs)
        except openai.APIStatusError as e:  # model rejects JSON mode -> plain call (never on timeouts)
            if e.status_code not in (400, 422):
                raise
            r = get_client().chat.completions.create(**kwargs)
    else:
        r = get_client().chat.completions.create(**kwargs)
    return r.choices[0].message.content.strip()


def chat_json(system: str, user: str, max_tokens: int = 600) -> dict:
    text = chat(system, user, max_tokens=max_tokens, json_mode=True)
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0) if m else text)
