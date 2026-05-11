"""
chat_handler.py — orchestrates a single /chat turn.

Flow:
  1. Security check (injection / off-topic)
  2. Intent classification
  3. Fetch catalog context (for Gemini's understanding)
  4. Build recommendations (from catalog, deterministically)
  5. Call Gemini for natural-language reply
  6. Assemble and return ChatResponse
"""

import logging
from typing import List

from models import Message, ChatResponse, Recommendation
from security import is_injection, is_off_topic, sanitize
from intent_classifier import classify_intent
from recommendation_engine import get_recommendations, get_entries_by_name
from prompt_builder import build_gemini_messages, build_catalog_context
from gemini_client import call_gemini

logger = logging.getLogger(__name__)

# ── Fallback replies (used when Gemini is unavailable) ───────────────────────
FALLBACK_RECOMMEND = (
    "Here are the SHL assessments I found for your requirements. "
    "Let me know if you'd like to refine these or need more information."
)
FALLBACK_CLARIFY = (
    "Could you tell me more about the role you're hiring for? "
    "For example: job title, seniority level, and whether you need technical or personality assessments."
)
FALLBACK_COMPARE = (
    "I couldn't reach the AI service right now. "
    "Please check the assessment details on the SHL website for a comparison."
)
FALLBACK_REFUSE = (
    "I'm here to help you find SHL assessments for your hiring needs. "
    "I can't assist with that particular request."
)
FALLBACK_END = "Thank you for using the SHL Assessment Recommender. Good luck with your hiring!"


async def handle_chat(messages: List[Message]) -> ChatResponse:
    """
    Main entry point called by the /chat endpoint.
    Stateless: all context comes from the `messages` list.
    """

    # ── 1. Sanitize & security check ─────────────────────────────────────────
    latest_msg = messages[-1]
    clean_content = sanitize(latest_msg.content)
    messages[-1] = Message(role=latest_msg.role, content=clean_content)

    if is_injection(clean_content):
        logger.warning("Injection attempt detected.")
        return ChatResponse(
            reply=(
                "I'm here to help you find SHL assessments. "
                "I noticed your message may be trying to change my behaviour — "
                "I can't do that. How can I help you with assessment selection?"
            ),
            recommendations=[],
            end_of_conversation=False,
        )

    if is_off_topic(clean_content):
        logger.info("Off-topic query detected.")
        return ChatResponse(
            reply=(
                "I'm specialised in recommending SHL assessments. "
                "I'm not able to help with that topic, but I'd be happy to assist "
                "you find the right assessments for a role!"
            ),
            recommendations=[],
            end_of_conversation=False,
        )

    # ── 2. Classify intent ────────────────────────────────────────────────────
    intent = classify_intent(messages)
    logger.info("Intent classified as: %s", intent)

    # ── NEW: Strong context guard (prevents early recommendations) ───────────
    if intent in ("RECOMMEND", "REFINE"):
        if not has_sufficient_context_for_recommendation(messages):
            intent = "CLARIFY"   # Force clarify even if classifier said recommend
            logger.info("Overriding intent to CLARIFY due to insufficient context")

    # ── 3. Build recommendations (only when we really should) ────────────────
    recommendations: List[Recommendation] = []
    catalog_entries = []

    all_user_text = " ".join(
        m.content for m in messages if m.role == "user"
    )

    if intent in ("RECOMMEND", "REFINE"):
        raw_recs = get_recommendations(all_user_text, max_results=6)  # reduced from 10
        catalog_entries = raw_recs
        recommendations = [
            Recommendation(
                name=r["name"],
                url=r["url"],
                test_type=r["test_type"],
            )
            for r in raw_recs
            if r.get("url")
        ]
    elif intent == "COMPARE":
        names = _extract_names_from_conversation(messages)
        catalog_entries = get_entries_by_name(names)

    # ── 4. Build Gemini context and call LLM ──────────────────────────────────
    catalog_ctx = build_catalog_context(
        catalog_entries if catalog_entries else _get_fallback_context(all_user_text)
    )
    gemini_messages = build_gemini_messages(messages, catalog_context=catalog_ctx)

    gemini_reply = await call_gemini(gemini_messages)

    # ── 5. Fallback replies if Gemini failed ──────────────────────────────────
    if gemini_reply is None:
        gemini_reply = _fallback_reply(intent, bool(recommendations))

    # ── 6. Assemble response ─────────────────────────────────────────────────
    end_of_conversation = intent == "END"

    # Clean up the reply: remove any accidental recommendation lists the LLM
    # might have hallucinated (we handle recommendations separately)
    reply_text = _strip_hallucinated_urls(gemini_reply)

    return ChatResponse(
        reply=reply_text,
        recommendations=recommendations if intent != "COMPARE" else [],
        end_of_conversation=end_of_conversation,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fallback_reply(intent: str, has_recs: bool) -> str:
    """Return a sensible hardcoded reply when Gemini is unreachable."""
    if intent == "END":
        return FALLBACK_END
    if intent == "REFUSE":
        return FALLBACK_REFUSE
    if intent == "COMPARE":
        return FALLBACK_COMPARE
    if intent == "CLARIFY":
        return FALLBACK_CLARIFY
    if has_recs:
        return FALLBACK_RECOMMEND
    return FALLBACK_CLARIFY


def _extract_names_from_conversation(messages: List[Message]) -> List[str]:
    """
    Heuristic: extract capitalised multi-word tokens that might be assessment names.
    This is intentionally simple — the LLM handles the actual comparison prose.
    """
    import re
    text = " ".join(m.content for m in messages)
    # Match words like "OPQ32", "Verify G+", "MQ", etc.
    candidates = re.findall(r"\b([A-Z][A-Za-z0-9+\-\.]{1,30})\b", text)
    # Deduplicate while preserving order
    seen = set()
    names = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            names.append(c)
    return names[:6]  # limit lookup


def _get_fallback_context(query: str):
    """If we have no recommendations, still give Gemini some catalog context."""
    from recommendation_engine import get_recommendations
    return get_recommendations(query, max_results=5)


def _strip_hallucinated_urls(text: str) -> str:
    """
    Remove any URLs the LLM may have invented.
    Real URLs come only from the recommendations array.
    """
    import re
    # Remove bare URLs not from shl.com that sneak in
    cleaned = re.sub(
        r"https?://(?!www\.shl\.com)[^\s)>\"']+",
        "[URL removed]",
        text,
    )
    return cleaned

def has_sufficient_context_for_recommendation(messages: List[Message]) -> bool:
    import re
    """Hard guard: only recommend when we have role + use case + some depth."""
    all_text = " ".join(m.content.lower() for m in messages if m.role == "user")
    
    has_seniority = bool(re.search(r"(cxo|director|executive|c.?suite|15 years|senior leadership|leadership)", all_text))
    has_usecase = bool(re.search(r"(selection|hiring|recruit|develop|development|feedback|benchmark|compare candidates)", all_text))
    
    # At least 2 user messages + both signals
    user_turns = sum(1 for m in messages if m.role == "user")
    
    return user_turns >= 2 and has_seniority and has_usecase