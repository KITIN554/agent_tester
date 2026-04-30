"""Типы данных для Travel Agent."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class StepType(StrEnum):
    USER_MESSAGE = "user_message"
    PLAN = "plan"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    AGENT_MESSAGE = "agent_message"
    STATE_TRANSITION = "state_transition"
    FINAL_ANSWER = "final_answer"
    ERROR = "error"


class TraceStep(BaseModel):
    step_id: int
    step_type: StepType
    timestamp: datetime
    content: dict[str, Any]


class AgentResponse(BaseModel):
    answer: str
    trace: list[TraceStep]
    final_state: str
    booking_id: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    latency_s: float = 0.0
    cost_usd: float = 0.0
    turn_count: int = 0
    error: str | None = None
