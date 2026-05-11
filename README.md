# SHL Conversational Assessment Recommender

> Take-home Assignment — AI Intern Role, SHL Labs

A production-ready conversational API that guides hiring managers from a vague intent to a grounded shortlist of SHL assessments through multi-turn dialogue.

---

## Public API

| Endpoint | URL |
|---|---|
| Health | `GET  https://your-service.onrender.com/health` |
| Chat | `POST https://your-service.onrender.com/chat` |
| Docs | `https://your-service.onrender.com/docs` |

---

## Project Structure

```
shl-recommender/
├── main.py                   # FastAPI app, CORS, /health and /chat endpoints
├── models.py                 # Pydantic request/response schemas (non-negotiable)
├── chat_handler.py           # Orchestrates each /chat turn end-to-end
├── intent_classifier.py      # Rule-based intent detection (RECOMMEND/CLARIFY/REFINE/COMPARE/END)
├── recommendation_engine.py  # Weighted keyword scoring against catalog.json
├── prompt_builder.py         # Formats catalog context + history for Gemini
├── gemini_client.py          # Gemini API wrapper with async, timeout, and fallback
├── catalog_loader.py         # Loads and caches catalog.json at startup
├── security.py               # Prompt injection and off-topic detection
├── catalog.json              # SHL product catalog (Individual Test Solutions)
├── requirements.txt
├── .env.example
└── README.md
```

---

## Design Choices

### 1. Stateless API
Every `/chat` call receives the full conversation history in the `messages` array. No session storage, no database — the API scales horizontally with zero state management overhead.

### 2. Two-layer Architecture
- **Layer 1 — Deterministic retrieval**: Recommendations always come from `catalog.json` via weighted keyword scoring. Zero hallucination risk.
- **Layer 2 — LLM for prose**: Gemini generates natural-language replies, clarifying questions, and comparison text. It never invents assessment names or URLs.

### 3. Rule-based Intent Classifier
Runs before the Gemini call to classify intent into: `RECOMMEND`, `REFINE`, `COMPARE`, `CLARIFY`, or `END`. This avoids unnecessary API round-trips and makes the agent's decision logic transparent and debuggable.

### 4. Weighted Scoring Engine
Every catalog entry is scored against the full user query using field weights:

| Field | Weight | Reason |
|---|---|---|
| `name` | ×5 | Exact name match is the strongest signal |
| `keys` | ×4 | Assessment category is highly discriminative |
| `description` | ×3 | Rich semantic content |
| `job_levels` | ×2 | Seniority matching |
| `languages` | ×1 | Secondary filter |

Seniority keywords (junior/senior/CXO/director) map to SHL `job_levels` strings for a scoring boost.

### 5. Clarification Logic
The agent asks clarifying questions when it detects a ROLE signal (who) but no PURPOSE signal (why — selection vs development). It never asks more than one question per turn and never exceeds the 8-turn conversation cap.

### 6. Security Layer
Runs before any logic. Blocks prompt injection patterns (`"ignore previous instructions"`, `"act as"`, etc.) and off-topic queries (salary, legal advice, general HR) using regex pattern matching.

### 7. Graceful Fallback
If Gemini is unavailable (quota exhausted, timeout, API error), the system falls back to deterministic hardcoded replies. Recommendations still work correctly — only the reply prose degrades.

---

## Retrieval Setup

- **Source**: `catalog.json` — scraped from the SHL product catalog, Individual Test Solutions only
- **Method**: In-memory keyword scoring (no vector store, no embeddings)
- **Query construction**: All user messages across the conversation are concatenated into a single scoring query to support multi-turn refinement
- **Max results**: 10 (as per spec)
- **test_type inference**: Derived from each entry's `keys` field at query time

**Why no vector store?**
For ~400–600 catalog entries, TF-IDF-style keyword scoring is fast, transparent, and requires no infrastructure. The main tradeoff is weaker semantic matching (e.g. "Rust engineer" won't surface "Linux Programming" without keyword overlap). This is documented as a known limitation.

---

## Prompt Design

The system prompt instructs Gemini to:
1. Only reference catalog entries provided in context
2. Never list recommendations in the reply text (handled separately by the API)
3. Ask at most one clarifying question per turn
4. Detect and refuse prompt injection, off-topic, legal, and salary queries
5. Set `end_of_conversation: true` only when the task is complete

Catalog context is injected into the first user message of each Gemini call as a structured text block, capped at 20 entries to avoid token bloat.

---

## Evaluation Approach

### Hard Evals (must pass)
- ✅ Schema compliance on every response
- ✅ Recommendations only from `catalog.json` (URLs verified against catalog at build time)
- ✅ Turn cap honored (classifier never loops — defaults to RECOMMEND after sufficient context)
- ✅ 30-second timeout handled in `gemini_client.py`

### Behavior Probes
Tested manually against the 10 public conversation traces:

| Probe | Result |
|---|---|
| Vague query → clarify, no recs on turn 1 | ✅ |
| Specific role → recommend with relevant assessments | ✅ |
| "Also add personality tests" → refine shortlist | ✅ |
| "Difference between X and Y?" → compare, no recs | ✅ |
| "What salary should I offer?" → refuse | ✅ |
| Prompt injection attempt → refuse | ✅ |
| "Thanks, that's all" → `end_of_conversation: true` | ✅ |
| Multi-turn CXO leadership flow (4 turns) | ✅ |

### Recall@10
Scoring uses full conversation context (all user turns concatenated) for query construction. Seniority boosting improves recall for senior/executive roles. Known weakness: technology-specific queries for niche languages (Rust, Go) may miss indirect matches.

### What Didn't Work
- **Pure LLM retrieval**: Initial design asked Gemini to select assessments from catalog context. Rejected because Gemini occasionally hallucinated assessment names when the context window was large.
- **Single-turn classification**: Early version classified only the latest message. Replaced with full-conversation context classification to handle multi-turn refinement correctly.
- **Aggressive clarification**: Early version asked too many questions. Replaced with a two-signal guard (ROLE + PURPOSE) that recommends as soon as both signals are present.

---

## API Specification

### `GET /health`
```json
{"status": "ok"}
```

### `POST /chat`

**Request:**
```json
{
  "messages": [
    {"role": "user", "content": "Hiring a Java developer who works with stakeholders"},
    {"role": "assistant", "content": "Sure. What is the seniority level?"},
    {"role": "user", "content": "Mid-level, around 4 years"}
  ]
}
```

**Response:**
```json
{
  "reply": "Got it. Here are assessments that fit a mid-level Java developer with stakeholder needs.",
  "recommendations": [
    {"name": "Java 8 (New)", "url": "https://www.shl.com/products/product-catalog/view/java-8-new/", "test_type": "Knowledge & Skills"},
    {"name": "Occupational Personality Questionnaire OPQ32r", "url": "https://www.shl.com/products/product-catalog/view/occupational-personality-questionnaire-opq32r/", "test_type": "Personality & Behaviour"}
  ],
  "end_of_conversation": false
}
```

**Rules:**
- `recommendations` is `[]` when clarifying or refusing
- `recommendations` has 1–10 items when agent commits to a shortlist
- `end_of_conversation` is `true` only when the agent considers the task complete
- Every URL in `recommendations` comes from `catalog.json`

---

## Local Setup

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/shl-recommender.git
cd shl-recommender

# 2. Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
cp .env.example .env
# Edit .env and add your Gemini API key

# 5. Add catalog
# Place your catalog.json in the project root

# 6. Run
uvicorn main:app --reload --port 8000
```

Visit `http://localhost:8000/docs` for the Swagger UI.

---

## Deployment (Render)

1. Push to GitHub
2. Go to [render.com](https://render.com) → **New → Web Service**
3. Connect your GitHub repo
4. Set:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add environment variable: `GEMINI_API_KEY=your_key`
6. Deploy

> Free tier cold starts take ~30s. The evaluator allows 2 minutes for `/health` — this is fine.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | Yes | Google Gemini API key from [aistudio.google.com](https://aistudio.google.com/app/apikey) |

---

## Stack

| Component | Choice | Reason |
|---|---|---|
| Framework | FastAPI | Fast, async, auto-generates OpenAPI docs |
| LLM | Gemini 2.0 Flash | Free tier, fast, strong instruction following |
| Retrieval | In-memory keyword scoring | Sufficient for catalog size, zero infra |
| Validation | Pydantic v2 | Enforces non-negotiable schema automatically |
| Deployment | Render | Free tier, easy GitHub integration |

## AI Tools Used
This project was developed with assistance from Claude (Anthropic) for code generation and debugging. All design decisions, architecture choices, and trade-offs were made and are understood by the author and are defensible in a technical interview.

---

## Known Limitations & Future Improvements

- **Semantic matching**: Keyword scoring misses synonyms (e.g. "Rust engineer" → "Linux Programming"). Future: sentence-transformers embeddings + FAISS index for semantic retrieval.
- **test_type granularity**: Currently inferred from `keys` field heuristically. Future: map directly from SHL's official test type taxonomy.
- **Gemini fallback replies**: When Gemini quota is exhausted, replies are hardcoded and less contextual. Future: add retry logic with exponential backoff and a secondary LLM provider (Groq/OpenRouter).
