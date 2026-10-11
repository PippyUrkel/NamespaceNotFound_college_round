from __future__ import annotations

from pydantic import BaseModel, Field


class RetrievalRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=8, ge=1, le=20)
