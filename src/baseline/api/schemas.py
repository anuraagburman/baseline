"""Request and response models for the FastAPI endpoints."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel


class OnboardRequest(BaseModel):
    user_id: str
    name: str | None = None
    age: int
    sex: str
    weight_kg: float
    goal: str
    delivery_pref: str = "evening"
    backfill_days: int = 45


class InsightResponse(BaseModel):
    user_id: str
    date: date
    message: str
    route: str
    evidence_citations: list[str]
    generated_at: datetime


class OnboardResponse(BaseModel):
    user_id: str
    first_insight: InsightResponse


class DailyInsightResponse(BaseModel):
    user_id: str
    date: date
    message: str
    route: str
    evidence_citations: list[str]


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


class HistoryResponse(BaseModel):
    user_id: str
    metrics: list[dict[str, Any]]
