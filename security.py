"""
security.py — lightweight safety checks before the query reaches the LLM.

Detects:
  • Prompt injection / jailbreak attempts
  • Clearly off-topic requests (legal, salary, general HR advice, etc.)
"""

import re
import logging

logger = logging.getLogger(__name__)

# ── Prompt-injection / jailbreak patterns ─────────────────────────────────────
INJECTION_PATTERNS = [
    r"ignore (previous|all|your) (instructions?|prompts?|rules?)",
    r"forget (everything|what you were told|your instructions)",
    r"you are now",
    r"act as (a |an )?(different|new|unrestricted|evil|dan)",
    r"pretend (you are|to be|you're)",
    r"jailbreak",
    r"do anything now",
    r"disregard (your |all )?(previous )?instructions",
    r"override (your )?(safety|guidelines|instructions)",
    r"system prompt",
    r"reveal (your |the )?(system )?prompt",
    r"what (are|were) your instructions",
]

# ── Off-topic / refusal triggers ──────────────────────────────────────────────
OFF_TOPIC_PATTERNS = [
    r"\b(salary|compensation|pay|wage|remuneration)\b",
    r"\b(legal advice|discrimination|lawsuit|sue|litigation)\b",
    r"\b(visa|immigration|work permit)\b",
    r"\b(weather|recipe|sports|movie|music|game)\b",
    r"\b(crypto|bitcoin|invest|stock market)\b",
    r"\b(write (me )?(a |an )?(essay|poem|story|code))\b",
    r"\b(who (is|was) (the )?(president|prime minister|ceo))\b",
]


def is_injection(text: str) -> bool:
    """Return True if text looks like a prompt injection attempt."""
    lower = text.lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, lower):
            logger.warning("Injection pattern matched: %s", pattern)
            return True
    return False


def is_off_topic(text: str) -> bool:
    """Return True if text is clearly unrelated to SHL assessment selection."""
    lower = text.lower()
    for pattern in OFF_TOPIC_PATTERNS:
        if re.search(pattern, lower):
            logger.info("Off-topic pattern matched: %s", pattern)
            return True
    return False


def sanitize(text: str) -> str:
    """Basic sanitization — strip leading/trailing whitespace, cap length."""
    return text.strip()[:2000]