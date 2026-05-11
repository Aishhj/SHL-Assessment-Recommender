"""
recommendation_engine.py

Scores every catalog entry against a parsed user query using
keyword matching and weighted field scoring.

NO external AI calls here — recommendations are always 100% deterministic
and sourced from catalog.json.
"""

import logging
import re
from typing import List, Dict, Any, Optional

from catalog_loader import load_catalog

logger = logging.getLogger(__name__)

# ── Field weights (higher = matters more) ────────────────────────────────────
WEIGHTS = {
    "name": 5,
    "description": 3,
    "keys": 4,
    "job_levels": 2,
    "languages": 1,
}

# ── Seniority keyword mapping ────────────────────────────────────────────────
SENIORITY_MAP = {
    "junior": ["Graduate", "Entry Level", "General Population"],
    "mid": ["Mid-Professional", "Professional Individual Contributor"],
    "senior": ["Manager", "Director", "Executive", "Senior Manager"],
    "manager": ["Manager", "Director", "Senior Manager"],
    "executive": ["Executive", "Director", "C-Suite"],
    "graduate": ["Graduate", "Entry Level"],
    "entry": ["Graduate", "Entry Level", "General Population"],
}

# ── Personality / soft-skill trigger keywords ─────────────────────────────────
PERSONALITY_KEYWORDS = {
    "personality", "behaviour", "behavior", "soft skill", "leadership",
    "teamwork", "collaboration", "communication", "motivation", "culture",
    "opq", "traits", "competency", "competencies", "interpersonal",
}

# ── Technical / knowledge trigger keywords ────────────────────────────────────
TECHNICAL_KEYWORDS = {
    "java", "python", "sql", ".net", "javascript", "typescript", "c++",
    "c#", "react", "angular", "node", "aws", "azure", "cloud", "devops",
    "data", "analytics", "machine learning", "ml", "ai", "testing", "qa",
    "automation", "framework", "programming", "developer", "engineer",
    "coding", "software", "database", "backend", "frontend", "fullstack",
}


def _tokenize(text: str) -> List[str]:
    """Lowercase and split into tokens, stripping punctuation."""
    return re.findall(r"[a-z0-9#.+]+", text.lower())


def _field_text(entry: Dict[str, Any], field: str) -> str:
    """Safely extract a field as a flat string."""
    value = entry.get(field, "")
    if isinstance(value, list):
        return " ".join(str(v) for v in value)
    return str(value)


def _score_entry(entry: Dict[str, Any], query_tokens: List[str]) -> float:
    """Return a relevance score for a single catalog entry."""
    score = 0.0
    for field, weight in WEIGHTS.items():
        field_tokens = _tokenize(_field_text(entry, field))
        matches = sum(1 for qt in query_tokens if qt in field_tokens)
        score += matches * weight
    return score


def _seniority_boost(entry: Dict[str, Any], seniority_hints: List[str]) -> float:
    """Add bonus score when job_levels match detected seniority."""
    if not seniority_hints:
        return 0.0
    job_levels = _field_text(entry, "job_levels").lower()
    return sum(
        2.0 for hint in seniority_hints
        if hint.lower() in job_levels
    )


def _detect_seniority(query_lower: str) -> List[str]:
    """Return matching job_level strings for detected seniority words."""
    hints: List[str] = []
    for keyword, levels in SENIORITY_MAP.items():
        if keyword in query_lower:
            hints.extend(levels)
    return list(set(hints))


def _detect_test_type(entry: Dict[str, Any]) -> str:
    """
    Infer a human-friendly test_type label from the catalog entry's 'keys' field.
    Falls back to 'Assessment'.
    """
    keys_text = _field_text(entry, "keys").lower()
    if any(k in keys_text for k in ("personality", "behaviour", "behavioral", "opq")):
        return "Personality & Behaviour"
    if any(k in keys_text for k in ("knowledge", "skill", "technical", "ability")):
        return "Knowledge & Skills"
    if "cognitive" in keys_text or "reasoning" in keys_text:
        return "Cognitive Ability"
    if "situational" in keys_text or "sjt" in keys_text:
        return "Situational Judgement"
    if "language" in keys_text or "verbal" in keys_text:
        return "Language & Verbal"
    return "Assessment"


def get_recommendations(
    query: str,
    max_results: int = 10,
    exclude_names: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Score all catalog entries against `query` and return the top results.

    Args:
        query: Free-text query describing what the user needs.
        max_results: Cap on returned recommendations (never > 10).
        exclude_names: Optional list of assessment names to skip
                       (e.g., already shown ones).

    Returns:
        List of dicts with keys: name, url, test_type, score (internal use).
    """
    catalog = load_catalog()
    exclude_names = [n.lower() for n in (exclude_names or [])]
    query_lower = query.lower()
    query_tokens = _tokenize(query_lower)
    seniority_hints = _detect_seniority(query_lower)

    scored: List[Dict[str, Any]] = []

    for entry in catalog:
        name = entry.get("name", "")
        if name.lower() in exclude_names:
            continue

        base_score = _score_entry(entry, query_tokens)
        boost = _seniority_boost(entry, seniority_hints)
        total = base_score + boost

        if total > 0:
            scored.append({
                "name": name,
                "url": entry.get("link", ""),
                "test_type": _detect_test_type(entry),
                "_score": total,
            })

    # Sort descending by score, then alphabetically for ties
    scored.sort(key=lambda x: (-x["_score"], x["name"]))

    # Remove internal score before returning
    results = scored[: min(max_results, 10)]
    for r in results:
        r.pop("_score", None)

    logger.info("Recommendations for query '%s': %d results", query[:60], len(results))
    return results


def get_entries_by_name(names: List[str]) -> List[Dict[str, Any]]:
    """
    Fetch full catalog entries by exact name (case-insensitive).
    Used for comparison requests.
    """
    catalog = load_catalog()
    name_set = {n.lower() for n in names}
    return [e for e in catalog if e.get("name", "").lower() in name_set]