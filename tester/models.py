"""Pydantic-модели данных проекта.

Покрывает спецификации:
- 02-scenario-format: Scenario / ScenarioInput / ScenarioExpectations
- 03-metrics: ProcessMetrics / SafetyMetrics / AggregateMetrics
- 04-judge: RubricVerdict / RubricEvaluation
- 05-gate-logic: GateDecision

Никакой бизнес-логики (расчёт метрик, судья, gate) тут нет — только структуры.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Сценарий (spec 02)
# ---------------------------------------------------------------------------

SCENARIO_ID_REGEX = re.compile(r"^SCN-(FIN|TRV)-\d{3}$")
ID_PREFIX_TO_SYSTEM = {"FIN": "finance_agent", "TRV": "travel_agent"}


class ScenarioCategory(StrEnum):
    FUNCTIONAL = "functional"
    EDGE_CASE = "edge_case"
    NEGATIVE = "negative"
    SAFETY = "safety"
    STRESS = "stress"
    ROBUSTNESS = "robustness"


class ScenarioType(StrEnum):
    SINGLE_TURN = "single_turn"
    MULTI_TURN = "multi_turn"


class ConversationTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ScenarioInput(BaseModel):
    user_message: str | None = None
    conversation_turns: list[ConversationTurn] | None = None
    available_tools: list[str] = Field(default_factory=list)
    limits: dict[str, Any] = Field(default_factory=dict)


class ToolCallExpectation(BaseModel):
    name: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    optional: bool = False


class ScenarioExpectations(BaseModel):
    terminal_state: str | None = None
    refusal_expected: bool = False
    must_contain: list[str] = Field(default_factory=list)
    must_not_contain: list[str] = Field(default_factory=list)
    required_tool_calls: list[ToolCallExpectation] = Field(default_factory=list)
    forbidden_tool_calls: list[str] = Field(default_factory=list)
    entities: dict[str, Any] = Field(default_factory=dict)
    numeric_response: Literal["required", "optional", "forbidden"] = "optional"


class Scenario(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    category: ScenarioCategory
    type: ScenarioType
    description: str
    system: Literal["finance_agent", "travel_agent"]
    source: str = "manual"
    created_at: str | None = None
    author: str | None = None
    parent_id: str | None = None

    input: ScenarioInput
    expectations: ScenarioExpectations
    rubrics: list[str] = Field(default_factory=list)
    thresholds: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        if not SCENARIO_ID_REGEX.match(value):
            raise ValueError(
                f"id должен соответствовать ^SCN-(FIN|TRV)-\\d{{3}}$, получено: {value!r}"
            )
        return value

    @model_validator(mode="after")
    def _validate_system_matches_id(self) -> Scenario:
        prefix = self.id.split("-")[1]
        expected_system = ID_PREFIX_TO_SYSTEM[prefix]
        if self.system != expected_system:
            raise ValueError(
                f"system={self.system!r} не соответствует префиксу id={self.id!r} "
                f"(ожидалось {expected_system!r})"
            )
        return self

    @model_validator(mode="after")
    def _validate_input_matches_type(self) -> Scenario:
        if self.type == ScenarioType.SINGLE_TURN:
            if not self.input.user_message:
                raise ValueError("single_turn сценарий должен иметь input.user_message")
            if self.input.conversation_turns:
                raise ValueError("single_turn сценарий не должен иметь input.conversation_turns")
        else:  # multi_turn
            if not self.input.conversation_turns:
                raise ValueError("multi_turn сценарий должен иметь input.conversation_turns")
            if self.input.user_message:
                raise ValueError("multi_turn сценарий не должен иметь input.user_message")
        return self


# ---------------------------------------------------------------------------
# Трасса (формат, общий для finance/travel-агентов)
# ---------------------------------------------------------------------------


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


class ScenarioTrace(BaseModel):
    """Полная трасса прогона одного сценария.

    Что бы ни выдал агент-исполнитель (finance/travel), executor конвертирует
    его ответ в этот формат. Дальше это единственный вход для судьи и метрик.
    """

    scenario_id: str
    system: Literal["finance_agent", "travel_agent"]
    final_answer: str = ""
    final_state: str | None = None
    booking_id: str | None = None
    steps: list[TraceStep] = Field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    latency_s: float = 0.0
    cost_usd: float = 0.0
    turn_count: int = 0
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


# ---------------------------------------------------------------------------
# Оценка (specs 03-04)
# ---------------------------------------------------------------------------


class RubricVerdict(StrEnum):
    PASS = "pass"
    PARTIAL = "partial"
    FAIL = "fail"
    NA = "na"


class RubricEvaluation(BaseModel):
    """Результат оценки одной рубрики судьёй."""

    rubric: str
    verdict: RubricVerdict
    score: float | None = Field(
        default=None,
        description="Числовая оценка 1..5 для рубрики tone_compliance; None для остальных",
    )
    rationale: str = ""

    @field_validator("score")
    @classmethod
    def _validate_score_range(cls, value: float | None) -> float | None:
        if value is None:
            return value
        if not 1.0 <= value <= 5.0:
            raise ValueError(f"score должен быть в диапазоне 1..5, получено: {value}")
        return value


class ProcessMetrics(BaseModel):
    """Метрики качества процесса (spec 03, программный расчёт по трассе)."""

    step_accuracy: float | None = None
    tool_selection_accuracy: float | None = None
    parameter_extraction_accuracy: float | None = None
    tool_call_correctness: float | None = None
    scenario_completion: bool = False
    step_compliance: float | None = None


class SafetyMetrics(BaseModel):
    """Метрики безопасности (spec 03)."""

    policy_violation: bool = False
    pii_leakage: bool = False
    refusal_correct: bool | None = None


class ScenarioOutcome(BaseModel):
    """Все результаты прогона одного сценария — то, что попадает в RunReport."""

    scenario: Scenario
    trace: ScenarioTrace
    rubric_evaluations: list[RubricEvaluation] = Field(default_factory=list)
    process_metrics: ProcessMetrics
    safety_metrics: SafetyMetrics
    passed: bool = False


# ---------------------------------------------------------------------------
# Корзина и gate (spec 03 + spec 05)
# ---------------------------------------------------------------------------


class AggregateMetrics(BaseModel):
    """Сводные показатели уровня корзины (RQS / PQS / RS / SS / ES).

    Все пять чисел нормализованы в диапазон [0, 1].
    """

    rqs: float = Field(ge=0.0, le=1.0)
    pqs: float = Field(ge=0.0, le=1.0)
    rs: float = Field(ge=0.0, le=1.0)
    ss: float = Field(ge=0.0, le=1.0)
    es: float = Field(ge=0.0, le=1.0)


class GateDecision(StrEnum):
    ALLOW = "allow"
    CONDITIONAL_ALLOW = "conditional_allow"
    BLOCK = "block"


class RunReport(BaseModel):
    """Полный отчёт о прогоне одной корзины.

    Сериализуется в `reports/runs/<run_id>/report.json`. Используется как baseline
    для следующих прогонов и как вход для reporter.html и dashboard.
    """

    run_id: str
    basket: str
    started_at: datetime
    finished_at: datetime | None = None

    git_commit: str | None = None
    git_branch: str | None = None
    model_agent: str | None = None
    model_judge: str | None = None
    proxy_base_url: str | None = None
    executor_version: str = "0.1.0"
    judge_version: str = "0.1.0"

    outcomes: list[ScenarioOutcome] = Field(default_factory=list)
    aggregate_metrics: AggregateMetrics

    gate_decision: GateDecision = GateDecision.ALLOW
    gate_reasons: list[str] = Field(default_factory=list)

    total_scenarios: int = 0
    passed_count: int = 0
    failed_count: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_cost_usd: float = 0.0
    avg_latency_s: float = 0.0
    p95_latency_s: float = 0.0

    @classmethod
    def from_outcomes(
        cls,
        *,
        run_id: str,
        basket: str,
        started_at: datetime,
        outcomes: list[ScenarioOutcome],
        aggregate_metrics: AggregateMetrics,
        gate_decision: GateDecision = GateDecision.ALLOW,
        gate_reasons: list[str] | None = None,
        finished_at: datetime | None = None,
        **manifest_fields: Any,
    ) -> RunReport:
        """Собирает RunReport из списка ScenarioOutcome, считая агрегаты.

        Удобный конструктор для orchestrator/тестов: считает passed/failed и
        технические суммы, чтобы их не считать вручную.
        """
        total = len(outcomes)
        passed = sum(1 for o in outcomes if o.passed)
        tokens_in = sum(o.trace.tokens_in for o in outcomes)
        tokens_out = sum(o.trace.tokens_out for o in outcomes)
        cost = sum(o.trace.cost_usd for o in outcomes)
        latencies = [o.trace.latency_s for o in outcomes]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
        p95_latency = _percentile(latencies, 95) if latencies else 0.0

        return cls(
            run_id=run_id,
            basket=basket,
            started_at=started_at,
            finished_at=finished_at,
            outcomes=outcomes,
            aggregate_metrics=aggregate_metrics,
            gate_decision=gate_decision,
            gate_reasons=gate_reasons or [],
            total_scenarios=total,
            passed_count=passed,
            failed_count=total - passed,
            total_tokens_in=tokens_in,
            total_tokens_out=tokens_out,
            total_cost_usd=round(cost, 6),
            avg_latency_s=round(avg_latency, 3),
            p95_latency_s=round(p95_latency, 3),
            **manifest_fields,
        )


def _percentile(values: list[float], p: float) -> float:
    """Простой 95-й перцентиль через сортировку без numpy.

    Если значений меньше двух — возвращаем максимум (или 0 для пустого списка).
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (p / 100.0) * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


__all__ = [
    "ScenarioCategory",
    "ScenarioType",
    "ConversationTurn",
    "ScenarioInput",
    "ToolCallExpectation",
    "ScenarioExpectations",
    "Scenario",
    "StepType",
    "TraceStep",
    "ScenarioTrace",
    "RubricVerdict",
    "RubricEvaluation",
    "ProcessMetrics",
    "SafetyMetrics",
    "ScenarioOutcome",
    "AggregateMetrics",
    "GateDecision",
    "RunReport",
    "SCENARIO_ID_REGEX",
    "ID_PREFIX_TO_SYSTEM",
]
