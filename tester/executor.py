"""Запуск сценариев на тестируемых агентах (spec 01)."""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime
from typing import Any

from .models import Scenario, ScenarioTrace, TraceStep


def _build_finance_agent() -> Any:
    from systems.finance_agent.agent import FinanceAgent

    return FinanceAgent()


def _build_travel_agent() -> Any:
    from systems.travel_agent.agent import TravelAgent

    return TravelAgent()


def execute_scenario(
    scenario: Scenario,
    *,
    finance_agent_factory: Callable[[], Any] = _build_finance_agent,
    travel_agent_factory: Callable[[], Any] = _build_travel_agent,
) -> ScenarioTrace:
    """Запускает scenario на соответствующем агенте и возвращает ScenarioTrace.

    Маршрутизация по `scenario.system`. Лимиты `max_latency_s` и `max_cost_usd`
    из `scenario.input.limits` соблюдаются:
    - для single_turn агент исполняется в отдельном потоке с timeout;
    - для multi_turn между ходами проверяются накопленные latency и стоимость.
    Любое исключение агента конвертируется в ScenarioTrace.error.

    Фабрики агентов вынесены в параметры, чтобы тесты могли подставлять моки.
    """
    started_at = datetime.now()

    if scenario.system == "finance_agent":
        if not scenario.input.user_message:
            raise ValueError(
                f"Scenario {scenario.id}: для finance_agent требуется input.user_message"
            )
        return _execute_single_turn(scenario, finance_agent_factory(), started_at)

    if scenario.system == "travel_agent":
        if not scenario.input.conversation_turns:
            raise ValueError(
                f"Scenario {scenario.id}: для travel_agent требуется input.conversation_turns"
            )
        return _execute_multi_turn(scenario, travel_agent_factory(), started_at)

    raise ValueError(f"Неизвестная система: {scenario.system!r}")


def _execute_single_turn(
    scenario: Scenario,
    agent: Any,
    started_at: datetime,
) -> ScenarioTrace:
    user_msg = scenario.input.user_message or ""
    max_latency = _float_limit(scenario.input.limits, "max_latency_s")
    t0 = time.monotonic()

    try:
        if max_latency is not None:
            response = _run_with_timeout(lambda: agent.run(user_msg), max_latency)
        else:
            response = agent.run(user_msg)
    except FutureTimeoutError:
        return _error_trace(
            scenario,
            f"Превышен лимит max_latency_s={max_latency}",
            started_at=started_at,
            elapsed=time.monotonic() - t0,
        )
    except Exception as exc:  # noqa: BLE001 — конвертируем в trace.error по контракту
        return _error_trace(
            scenario,
            str(exc),
            started_at=started_at,
            elapsed=time.monotonic() - t0,
        )

    trace = _build_trace_from_response(scenario, response, started_at)
    _enforce_post_run_cost_limit(trace, scenario)
    return trace


def _execute_multi_turn(
    scenario: Scenario,
    agent: Any,
    started_at: datetime,
) -> ScenarioTrace:
    user_messages = [
        turn.content for turn in (scenario.input.conversation_turns or []) if turn.role == "user"
    ]
    max_latency = _float_limit(scenario.input.limits, "max_latency_s")
    max_cost = _float_limit(scenario.input.limits, "max_cost_usd")

    agent.start_session()
    last_response: Any = None
    early_exit_reason: str | None = None
    t0 = time.monotonic()

    try:
        for msg in user_messages:
            if max_latency is not None and (time.monotonic() - t0) > max_latency:
                early_exit_reason = f"Превышен лимит max_latency_s={max_latency}"
                break
            if max_cost is not None and last_response is not None:
                cur_cost = float(getattr(last_response, "cost_usd", 0.0) or 0.0)
                if cur_cost > max_cost:
                    early_exit_reason = f"Превышен лимит max_cost_usd={max_cost}"
                    break

            last_response = agent.send(msg)

            if agent.is_done():
                break
    except Exception as exc:  # noqa: BLE001
        return _error_trace(
            scenario,
            str(exc),
            started_at=started_at,
            elapsed=time.monotonic() - t0,
            partial=last_response,
        )

    if last_response is None:
        return _error_trace(
            scenario,
            "Не удалось собрать ни одной реплики (пустой список user-сообщений)",
            started_at=started_at,
            elapsed=time.monotonic() - t0,
        )

    return _build_trace_from_response(scenario, last_response, started_at, error=early_exit_reason)


def _run_with_timeout(fn: Callable[[], Any], timeout_s: float) -> Any:
    """Запускает sync-функцию в отдельном потоке с timeout.

    Если timeout сработал, потоковой пул закрывается без ожидания фоновой
    задачи (она досидит свой sleep как daemon в фоне).
    """
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(fn)
        return future.result(timeout=timeout_s)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _build_trace_from_response(
    scenario: Scenario,
    response: Any,
    started_at: datetime,
    error: str | None = None,
) -> ScenarioTrace:
    raw_steps = getattr(response, "trace", []) or []
    steps: list[TraceStep] = []
    for raw in raw_steps:
        if isinstance(raw, TraceStep):
            steps.append(raw)
        elif hasattr(raw, "model_dump"):
            steps.append(TraceStep.model_validate(raw.model_dump()))
        elif isinstance(raw, dict):
            steps.append(TraceStep.model_validate(raw))
        # иначе — игнорируем непригодный шаг

    final_error = error if error is not None else getattr(response, "error", None)

    return ScenarioTrace(
        scenario_id=scenario.id,
        system=scenario.system,
        final_answer=getattr(response, "answer", "") or "",
        final_state=getattr(response, "final_state", None),
        booking_id=getattr(response, "booking_id", None),
        steps=steps,
        tokens_in=int(getattr(response, "tokens_in", 0) or 0),
        tokens_out=int(getattr(response, "tokens_out", 0) or 0),
        latency_s=float(getattr(response, "latency_s", 0.0) or 0.0),
        cost_usd=float(getattr(response, "cost_usd", 0.0) or 0.0),
        turn_count=int(getattr(response, "turn_count", 0) or 0),
        error=final_error,
        started_at=started_at,
        finished_at=datetime.now(),
    )


def _error_trace(
    scenario: Scenario,
    error: str,
    *,
    started_at: datetime,
    elapsed: float,
    partial: Any = None,
) -> ScenarioTrace:
    if partial is not None:
        return _build_trace_from_response(scenario, partial, started_at, error=error)
    return ScenarioTrace(
        scenario_id=scenario.id,
        system=scenario.system,
        error=error,
        latency_s=round(elapsed, 3),
        started_at=started_at,
        finished_at=datetime.now(),
    )


def _enforce_post_run_cost_limit(trace: ScenarioTrace, scenario: Scenario) -> None:
    """Single_turn: запрос уже выполнен, но если стоимость выше лимита —
    помечаем трассу ошибкой (пост-фактум: неинвазивно, без изменения других полей)."""
    max_cost = _float_limit(scenario.input.limits, "max_cost_usd")
    if max_cost is None:
        return
    if trace.cost_usd > max_cost and not trace.error:
        trace.error = f"Превышен лимит max_cost_usd={max_cost}"


def _float_limit(limits: dict[str, Any], key: str) -> float | None:
    raw = limits.get(key)
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


__all__ = ["execute_scenario"]
