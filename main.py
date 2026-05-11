"""
SHL Conversational Assessment Recommender - Main Application
FastAPI backend with /health and /chat endpoints
"""

import logging
from dotenv import load_dotenv
load_dotenv()  # Load .env file before anything else

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from fastapi.responses import RedirectResponse

from models import ChatRequest, ChatResponse
from chat_handler import handle_chat

# ── Logging setup ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── App init ─────────────────────────────────────────────────────────────────
app = FastAPI(
    title="SHL Assessment Recommender",
    description="Conversational API that recommends SHL assessments from the product catalog.",
    version="1.0.0",
)

# Allow all origins (adjust for production if needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", include_in_schema=False)
def root():
    """Redirect root to Swagger docs."""
    return RedirectResponse(url="/docs")

# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
def health_check():
    """Simple liveness probe."""
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(request: ChatRequest):
    """
    Conversational endpoint.
    Accepts a messages array (full history) and returns a reply,
    optional recommendations from the SHL catalog, and an end-of-conversation flag.
    """
    logger.info("POST /chat — %d message(s) in history", len(request.messages))
    try:
        response = await handle_chat(request.messages)
        return response
    except Exception as exc:
        logger.exception("Unhandled error in /chat")
        raise HTTPException(status_code=500, detail=str(exc))