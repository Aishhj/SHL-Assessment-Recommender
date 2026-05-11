"""
Pydantic models — request/response schemas for the /chat endpoint.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class Message(BaseModel):
    """A single turn in the conversation."""
    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="Text content of the message")


class ChatRequest(BaseModel):
    """Request body for POST /chat."""
    messages: List[Message] = Field(
        ...,
        min_length=1,
        description="Full conversation history. Last message must be from 'user'.",
    )


class Recommendation(BaseModel):
    """A single SHL assessment recommendation."""
    name: str
    url: str
    test_type: str


class ChatResponse(BaseModel):
    """Response body for POST /chat."""
    reply: str
    recommendations: List[Recommendation] = []
    end_of_conversation: bool = False