"""
Anthropic Claude API wrapper.
Provides a reusable client with rate limiting and error handling.
"""
import json
import logging
import time
from typing import Any

import anthropic

from .config_loader import get_anthropic_api_key

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"
DEFAULT_MAX_TOKENS = 4096
DEFAULT_DELAY_SECONDS = 2.0

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    """Return a singleton Anthropic client."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=get_anthropic_api_key())
    return _client


def call_claude(
    prompt: str,
    system: str | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    delay: float = DEFAULT_DELAY_SECONDS,
    temperature: float = 0.3,
) -> str:
    """
    Send a prompt to Claude and return the text response.

    Args:
        prompt: The user message.
        system: Optional system message.
        max_tokens: Max tokens to generate.
        delay: Seconds to wait after the call (rate limiting).
        temperature: Sampling temperature.

    Returns:
        The model's text response as a string.

    Raises:
        anthropic.APIError: On API failure.
    """
    client = get_client()
    messages = [{"role": "user", "content": prompt}]

    kwargs: dict[str, Any] = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "messages": messages,
        "temperature": temperature,
    }
    if system:
        kwargs["system"] = system

    try:
        logger.debug("Calling Claude (model=%s, max_tokens=%d)", MODEL, max_tokens)
        response = client.messages.create(**kwargs)
        text = response.content[0].text
        logger.debug("Claude response received (%d chars)", len(text))
        if delay > 0:
            time.sleep(delay)
        return text
    except anthropic.RateLimitError as exc:
        logger.warning("Rate limited by Anthropic API. Waiting 30s. %s", exc)
        time.sleep(30)
        # Retry once
        response = client.messages.create(**kwargs)
        return response.content[0].text
    except anthropic.APIStatusError as exc:
        logger.error("Anthropic API error: %s", exc)
        raise
    except Exception as exc:
        logger.error("Unexpected error calling Claude: %s", exc)
        raise


def call_claude_json(
    prompt: str,
    system: str | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    delay: float = DEFAULT_DELAY_SECONDS,
) -> dict | list:
    """
    Call Claude and parse the response as JSON.

    Returns:
        Parsed JSON object or list.

    Raises:
        ValueError: If response cannot be parsed as JSON.
    """
    raw = call_claude(prompt, system=system, max_tokens=max_tokens, delay=delay)

    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove opening fence (```json or ```)
        lines = lines[1:]
        # Remove closing fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse Claude response as JSON: %s\nRaw:\n%s", exc, raw)
        raise ValueError(f"Claude returned non-JSON response: {exc}") from exc
