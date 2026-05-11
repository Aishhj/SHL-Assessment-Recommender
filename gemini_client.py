"""
gemini_client.py — thin wrapper around google-generativeai.

Handles:
  • API key loading from environment
  • Sending conversation history to gemini-2.0-flash
  • Parsing the response text
  • Graceful fallback if the API is unavailable
"""

import logging
import os
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Lazy import so the app starts even without the package installed
try:            
    import google.generativeai as genai
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False
    logger.warning("google-generativeai not installed. Gemini calls will be skipped.")

MODEL_NAME = "gemini-2.0-flash"


def _get_client():
    """Configure and return the Gemini GenerativeModel."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY environment variable is not set. "
            "Add it to your .env file or Render environment variables."
        )
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(
        model_name=MODEL_NAME,
        system_instruction=_SYSTEM_PROMPT_IMPORT(),
    )


def _SYSTEM_PROMPT_IMPORT() -> str:
    """Import system prompt here to avoid circular imports."""
    from prompt_builder import SYSTEM_PROMPT
    return SYSTEM_PROMPT


async def call_gemini(
    messages: List[Dict[str, str]],
    timeout: int = 25,
) -> Optional[str]:
    """
    Send `messages` to Gemini and return the text response.

    Args:
        messages: List of {"role": "user"|"model", "parts": str} dicts.
        timeout: Seconds before we give up (keep under 30s API timeout).

    Returns:
        The model's text reply, or None on failure.
    """
    if not _GENAI_AVAILABLE:
        logger.warning("Gemini unavailable — returning None for fallback.")
        return None

    try:
        model = _get_client()

        # Build chat history (all but the last message)
        history = messages[:-1] if len(messages) > 1 else []
        last_msg = messages[-1]["parts"] if messages else ""

        chat = model.start_chat(history=history)

        # Gemini's SDK is synchronous; run in executor to avoid blocking
        import asyncio
        loop = asyncio.get_event_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: chat.send_message(last_msg)),
            timeout=timeout,
        )

        text = response.text.strip()
        logger.info("Gemini responded (%d chars)", len(text))
        return text

    except asyncio.TimeoutError:
        logger.error("Gemini call timed out after %ds", timeout)
        return None
    except Exception as exc:
        logger.error("Gemini error: %s", exc)
        return None
