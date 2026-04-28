"""Тесты executor.execute_scenario с мокированными агентами."""

from __future__ import annotations

import time
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest

from tester.executor import execute_scenario
from tester.models import Scenario


def _fake_step(step_id: int, step_type: str, content: dict[str, Any]) -> dict[str, Any]:
    return {
        "step_id": step_id,
        "step_type": step_type,
        "timestamp": datetime.now(),
        "content": content,
    }


def _make_finance_response(
    answer: str = "Вы потратили 12 345 руб.",
    cost: float = 0.001,
    error: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        answer=answer,
        trace=[
            _fake_step(0, "user_message", {"message": "Сколько потратил?"}),
            _fake_step(
                1,
                "tool_call",
                {"name": "query_transactions", "parameters": {"period": "previous_month"}},
            ),
            _fake_step(2, "final_answer", {"answer": answer}),
        ],
        tokens_in=120,
        tokens_out=40,
        latency_s=0.5,
        cost_usd=cost,
        error=error,
    )


class FakeFinanceAgent:
    def __init__(
        self,
        response: SimpleNamespace | None = None,
        sleep_s: float = 0.0,
        raise_exc: BaseException | None = None,
    ) -> None:
        self._response = response or _make_finance_response()
        self._sleep_s = sleep_s
        self._raise_exc = raise_exc
        self.calls: list[str] = []

    def run(self, message: str) -> SimpleNamespace:
        self.calls.append(message)
        if self._sleep_s:
            time.sleep(self._sleep_s)
        if self._raise_exc:
            raise self._raise_exc
        return self._response


class FakeTravelAgent:
    """Мок travel-агента: накапливает шаги, terminal — после 'consent'."""

    def __init__(self, terminal_after: int = 3) -> None:
        self.started = False
        self.send_calls: list[str] = []
        self.trace: list[dict[str, Any]] = []
        self.tokens_in = 0
        self.tokens_out = 0
        self.cost_usd = 0.0
        self.turn_count = 0
        self.final_state = "initial"
        self.booking_id: str | None = None
        self._terminal_after = terminal_after

    def start_session(self) -> None:
        self.started = True
        self.trace = []

    def is_done(self) -> bool:
        return len(self.send_calls) >= self._terminal_after

    def send(self, msg: str) -> SimpleNamespace:
        self.send_calls.append(msg)
        self.turn_count += 1
        self.tokens_in += 50
        self.tokens_out += 20
        self.cost_usd += 0.0005
        self.trace.append(_fake_step(len(self.trace), "user_message", {"message": msg}))
        self.trace.append(
            _fake_step(len(self.trace), "agent_message", {"message": f"reply to {msg}"})
        )
        if self.is_done():
            self.final_state = "confirmed"
            self.booking_id = "BK-TEST-001"

        return SimpleNamespace(
            answer=f"reply to {msg}",
            trace=list(self.trace),
            final_state=self.final_state,
            booking_id=self.booking_id,
            tokens_in=self.tokens_in,
            tokens_out=self.tokens_out,
            latency_s=0.1 * self.turn_count,
            cost_usd=self.cost_usd,
            turn_count=self.turn_count,
            error=None,
        )


# ---------------------------------------------------------------------------


def test_execute_single_turn_returns_full_trace(sample_scenario: dict[str, Any]) -> None:
    scenario = Scenario.model_validate(sample_scenario)
    fake = FakeFinanceAgent()

    trace = execute_scenario(scenario, finance_agent_factory=lambda: fake)

    assert fake.calls == ["Сколько я потратил в прошлом месяце?"]
    assert trace.scenario_id == "SCN-FIN-001"
    assert trace.system == "finance_agent"
    assert trace.final_answer == "Вы потратили 12 345 руб."
    assert len(trace.steps) == 3
    assert trace.tokens_in == 120
    assert trace.tokens_out == 40
    assert trace.cost_usd == pytest.approx(0.001)
    assert trace.error is None
    assert trace.started_at is not None and trace.finished_at is not None


def test_execute_multi_turn_runs_all_user_messages() -> None:
    scenario = Scenario.model_validate(
        {
            "id": "SCN-TRV-099",
            "category": "functional",
            "type": "multi_turn",
            "description": "test",
            "system": "travel_agent",
            "input": {
                "conversation_turns": [
                    {"role": "user", "content": "хочу поехать"},
                    {"role": "user", "content": "бюджет 100к"},
                    {"role": "user", "content": "согласен"},
                ],
                "limits": {"max_steps": 30, "max_turns": 15, "max_latency_s": 60},
            },
            "expectations": {"terminal_state": "confirmed"},
            "rubrics": ["intent_coverage"],
        }
    )
    fake = FakeTravelAgent(terminal_after=3)

    trace = execute_scenario(scenario, travel_agent_factory=lambda: fake)

    assert fake.started is True
    assert fake.send_calls == ["хочу поехать", "бюджет 100к", "согласен"]
    assert trace.turn_count == 3
    assert trace.final_state == "confirmed"
    assert trace.booking_id == "BK-TEST-001"
    assert trace.tokens_in == 150
    assert trace.cost_usd == pytest.approx(0.0015)
    assert trace.error is None
    # Каждый send добавил 2 шага, итого 6
    assert len(trace.steps) == 6


def test_execute_multi_turn_stops_when_agent_is_done() -> None:
    scenario = Scenario.model_validate(
        {
            "id": "SCN-TRV-098",
            "category": "functional",
            "type": "multi_turn",
            "description": "early termination",
            "system": "travel_agent",
            "input": {
                "conversation_turns": [
                    {"role": "user", "content": "msg1"},
                    {"role": "user", "content": "msg2"},
                    {"role": "user", "content": "msg3 (won't be sent)"},
                ],
                "limits": {},
            },
            "expectations": {"terminal_state": "confirmed"},
            "rubrics": ["intent_coverage"],
        }
    )
    fake = FakeTravelAgent(terminal_after=2)
    trace = execute_scenario(scenario, travel_agent_factory=lambda: fake)
    assert fake.send_calls == ["msg1", "msg2"]
    assert trace.turn_count == 2


def test_execute_records_agent_exception_into_trace_error(
    sample_scenario: dict[str, Any],
) -> None:
    scenario = Scenario.model_validate(sample_scenario)
    fake = FakeFinanceAgent(raise_exc=RuntimeError("LLM blew up"))

    trace = execute_scenario(scenario, finance_agent_factory=lambda: fake)
    assert trace.error == "LLM blew up"
    assert trace.final_answer == ""
    assert trace.steps == []


def test_execute_respects_max_latency(sample_scenario: dict[str, Any]) -> None:
    """single_turn: если агент дольше max_latency_s — трасса возвращается с ошибкой."""
    sc = {**sample_scenario}
    sc["input"] = {**sample_scenario["input"], "limits": {"max_latency_s": 0.05}}
    scenario = Scenario.model_validate(sc)

    fake = FakeFinanceAgent(sleep_s=0.3)
    started = time.monotonic()
    trace = execute_scenario(scenario, finance_agent_factory=lambda: fake)
    elapsed = time.monotonic() - started

    # Возврат должен случиться значительно раньше, чем закончит мок
    assert elapsed < 0.25
    assert trace.error is not None and "max_latency_s" in trace.error
    assert trace.system == "finance_agent"


def test_execute_routes_by_system(sample_scenario: dict[str, Any]) -> None:
    """Маршрутизация: для finance_agent вызывается ТОЛЬКО finance-фабрика."""
    scenario = Scenario.model_validate(sample_scenario)

    finance_calls: list[FakeFinanceAgent] = []
    travel_calls: list[FakeTravelAgent] = []

    def finance_factory() -> FakeFinanceAgent:
        a = FakeFinanceAgent()
        finance_calls.append(a)
        return a

    def travel_factory() -> FakeTravelAgent:
        a = FakeTravelAgent()
        travel_calls.append(a)
        return a

    execute_scenario(
        scenario,
        finance_agent_factory=finance_factory,
        travel_agent_factory=travel_factory,
    )
    assert len(finance_calls) == 1
    assert len(travel_calls) == 0
