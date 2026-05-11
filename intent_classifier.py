import re
from typing import List
from models import Message

# Patterns
VAGUE_PATTERNS = [
    r"we need a solution", r"i need an assessment", r"assessment please",
    r"help|hello|hi|hey", r"looking for (a |an )?solution"
]

REFINE_PATTERNS = [
    r"\b(add|include|also|additionally|but|instead|however|more|focus|narrow|"
    r"broaden|update|change|filter|adjust|refine|modify|remove|exclude)\b"
]

COMPARE_PATTERNS = [
    r"\b(compare|difference|versus|vs\.?|which is better|how .* differ)\b"
]

END_PATTERNS = [
    r"\b(thank(s| you)|bye|goodbye|perfect|that's what we need|exactly what|"
    r"looks good|that works|done|no more)\b"
]

ROLE_SIGNALS = re.compile(
    r"\b(senior|junior|mid.?level|director|cxo|c.?suite|executive|vp|leadership|"
    r"developer|engineer|manager|analyst)\b", re.I
)

PURPOSE_SIGNALS = re.compile(
    r"\b(selection|hiring|recruit|develop|development|feedback|benchmark|"
    r"compare candidates|assess candidates|succession|onboard|promotion)\b", re.I
)

def has_sufficient_context(all_user_text: str) -> bool:
    text = all_user_text.lower()
    has_role = bool(ROLE_SIGNALS.search(text))
    has_purpose = bool(PURPOSE_SIGNALS.search(text))
    has_experience = bool(re.search(r"\b(\d{1,2}\+?\s*years?|15 years?|senior|executive|cxo)\b", text))
    
    # Need role + (purpose OR strong experience)
    return has_role and (has_purpose or has_experience)


def classify_intent(messages: List[Message]) -> str:
    if not messages:
        return "CLARIFY"
    
    latest_msg = messages[-1].content.lower().strip()
    all_user_text = " ".join(m.content.lower() for m in messages if m.role == "user")

    # Priority order (most specific first)
    if any(re.search(p, latest_msg) for p in END_PATTERNS):
        return "END"
    
    if any(re.search(p, latest_msg) for p in COMPARE_PATTERNS):
        return "COMPARE"
    
    # Strong refine signals
    if len(messages) > 2 and any(re.search(p, latest_msg) for p in REFINE_PATTERNS):
        return "REFINE"

    # Very first vague message
    if len([m for m in messages if m.role == "user"]) == 1:
        if any(re.search(p, latest_msg) for p in VAGUE_PATTERNS):
            return "CLARIFY"

    # Core logic - be conservative
    if has_sufficient_context(all_user_text):
        return "RECOMMEND"
    
    # We know something about the role/level but not enough yet
    if ROLE_SIGNALS.search(all_user_text):
        return "CLARIFY"

    # Default
    return "CLARIFY"