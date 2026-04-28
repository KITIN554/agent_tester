"""Типы данных для Finance Agent."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class StepType(str, Enum):
    """Тип шага в трассе агента."""

    USER_MESSAGE = "user_message"
    PLAN = "plan"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    FINAL_ANSWER = "final_answer"
    ERROR = "error"


class TraceStep(BaseModel):
    """Один шаг в трассе агента."""

    step_id: int
    step_type: StepType
    timestamp: datetime
    content: dict[str, Any]


class AgentResponse(BaseModel):
    """Финальный ответ агента и его метаданные."""

    answer: str
    trace: list[TraceStep]
    tokens_in: int = 0
    tokens_out: int = 0
    latency_s: float = 0.0
    cost_usd: float = 0.0
    error: str | None = None


class ToolCall(BaseModel):
    """Описание вызова инструмента (для логирования и оценки)."""

    name: str
    parameters: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None
