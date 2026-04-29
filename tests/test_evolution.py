"""Тесты эволюционного цикла (tester/evolution.py) с моками LLM."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from tester import evolution
from tester.models import (
    AggregateMetrics,
    GateDecision,
    ProcessMetrics,
    RubricEvaluation,
    RubricVerdict,
    RunReport,
    SafetyMetrics,
    Scenario,
    ScenarioOutcome,
    ScenarioTrace,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _generated_scenario_dict(idx: int = 1) -> dict[str, Any]:
    return {
        "category": "functional",
        "type": "single_turn",
        "description": f"Тестовый сценарий {idx}",
        "system": "finance_agent",
        "input": {
            "user_message": f"вопрос {idx}",
            "available_tools": ["query_transactions"],
        },
        "expectations": {
            "required_tool_calls": [
                {
                    "name": "query_transactions",
                    "parameters": {
                        "period": "previous_month",
                        "aggregation": "sum",
                    },
                }
            ],
        },
        "rubrics": ["intent_coverage"],
    }


def _queue_scenarios_response(mock_proxy_client: Any, scenarios: list[dict[str, Any]]) -> None:
    mock_proxy_client.queue_response(content=json.dumps({"scenarios": scenarios}))


def _make_basket_with_scenario(basket_dir: Path, scn_id: str) -> Path:
    basket_dir.mkdir(parents=True, exist_ok=True)
    body = {
        "id": scn_id,
        "category": "functional",
        "type": "single_turn",
        "description": "уже существует",
        "system": "finance_agent",
        "input": {"user_message": "test", "available_tools": ["query_transactions"]},
        "expectations": {},
        "rubrics": ["intent_coverage"],
    }
    (basket_dir / f"{scn_id}.yaml").write_text(
        yaml.safe_dump(body, allow_unicode=True), encoding="utf-8"
    )
    return basket_dir


@pytest.fixture(autouse=True)
def _stub_subagent_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Кладём в .claude/agents/ временные стабы и переключаем константы модуля."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "scenario-generator.md").write_text(
        "---\nname: scenario-generator\n---\nТы — генератор сценариев.",
        encoding="utf-8",
    )
    (agents_dir / "metric-analyzer.md").write_text(
        "---\nname: metric-analyzer\n---\nТы — анализатор метрик.",
        encoding="utf-8",
    )
    monkeypatch.setattr(evolution, "_SUBAGENTS_DIR", agents_dir)
    monkeypatch.setattr(evolution, "_SYSTEMS_DIR", tmp_path / "systems_stub")
    return agents_dir


# ---------------------------------------------------------------------------
# invoke_scenario_generator
# ---------------------------------------------------------------------------


def test_generator_returns_valid_scenarios(tmp_path: Path, mock_proxy_client: Any) -> None:
    basket = tmp_path / "baskets" / "finance_agent"
    _queue_scenarios_response(
        mock_proxy_client,
        [_generated_scenario_dict(1), _generated_scenario_dict(2)],
    )

    saved = evolution.invoke_scenario_generator(
        system="finance_agent",
        target_count=2,
        client=mock_proxy_client,
        model="test-model",
        basket_dir=basket,
    )

    assert len(saved) == 2
    assert all(isinstance(s, Scenario) for s in saved)
    # IDs последовательные начиная с 001
    assert [s.id for s in saved] == ["SCN-FIN-001", "SCN-FIN-002"]
    # На диск тоже легло
    assert (basket / "SCN-FIN-001.yaml").exists()
    assert (basket / "SCN-FIN-002.yaml").exists()


def test_generator_assigns_next_id_after_existing(tmp_path: Path, mock_proxy_client: Any) -> None:
    basket = tmp_path / "baskets" / "finance_agent"
    _make_basket_with_scenario(basket, "SCN-FIN-016")
    _queue_scenarios_response(mock_proxy_client, [_generated_scenario_dict(1)])

    saved = evolution.invoke_scenario_generator(
        system="finance_agent",
        target_count=1,
        client=mock_proxy_client,
        model="test-model",
        basket_dir=basket,
    )
    assert [s.id for s in saved] == ["SCN-FIN-017"]


def test_generator_skips_invalid_scenarios(tmp_path: Path, mock_proxy_client: Any) -> None:
    """Из 3 кандидатов один невалидный — он пропускается, остальные сохраняются."""
    bad = {"category": "functional"}  # пропущены обязательные поля
    _queue_scenarios_response(
        mock_proxy_client,
        [_generated_scenario_dict(1), bad, _generated_scenario_dict(2)],
    )

    saved = evolution.invoke_scenario_generator(
        system="finance_agent",
        target_count=3,
        client=mock_proxy_client,
        model="test-model",
        basket_dir=tmp_path / "basket",
    )
    assert len(saved) == 2


def test_generator_returns_empty_on_llm_error(tmp_path: Path, mock_proxy_client: Any) -> None:
    def boom(**kwargs: Any) -> Any:
        raise ConnectionError("simulated network failure")

    mock_proxy_client.chat.completions.create = boom
    saved = evolution.invoke_scenario_generator(
        system="finance_agent",
        target_count=2,
        client=mock_proxy_client,
        model="test-model",
        basket_dir=tmp_path / "basket",
    )
    assert saved == []


def test_generator_returns_empty_on_garbage_json(tmp_path: Path, mock_proxy_client: Any) -> None:
    mock_proxy_client.queue_response(content="not a json {{{")
    saved = evolution.invoke_scenario_generator(
        system="finance_agent",
        target_count=2,
        client=mock_proxy_client,
        model="test-model",
        basket_dir=tmp_path / "basket",
    )
    assert saved == []


# ---------------------------------------------------------------------------
# invoke_metric_analyzer
# ---------------------------------------------------------------------------


def _write_run_report(reports_dir: Path, run_id: str = "20260428-150000-finance_agent") -> Path:
    scenario = Scenario.model_validate(_generated_scenario_dict(1) | {"id": "SCN-FIN-001"})
    outcome = ScenarioOutcome(
        scenario=scenario,
        trace=ScenarioTrace(scenario_id=scenario.id, system="finance_agent"),
        rubric_evaluations=[RubricEvaluation(rubric="intent_coverage", verdict=RubricVerdict.PASS)],
        process_metrics=ProcessMetrics(scenario_completion=True),
        safety_metrics=SafetyMetrics(),
        passed=True,
    )
    report = RunReport(
        run_id=run_id,
        basket="finance_agent",
        started_at=datetime(2026, 4, 28, 15, 0),
        outcomes=[outcome],
        aggregate_metrics=AggregateMetrics(rqs=0.9, pqs=0.9, rs=1.0, ss=1.0, es=0.9),
        gate_decision=GateDecision.ALLOW,
        total_scenarios=1,
        passed_count=1,
    )
    run_dir = reports_dir / run_id
    run_dir.mkdir(parents=True)
    path = run_dir / "report.json"
    path.write_text(report.model_dump_json(), encoding="utf-8")
    return path


def test_analyzer_returns_structured_dict(tmp_path: Path, mock_proxy_client: Any) -> None:
    reports_dir = tmp_path / "reports"
    _write_run_report(reports_dir)

    mock_proxy_client.queue_response(
        content=json.dumps(
            {
                "run_id": "20260428-150000-finance_agent",
                "regressions": [],
                "improvements": ["intent_coverage улучшилось"],
                "patterns": [],
                "recommendations": ["ничего не делать"],
            }
        )
    )

    result = evolution.invoke_metric_analyzer(
        run_id="20260428-150000-finance_agent",
        client=mock_proxy_client,
        model="test-model",
        reports_dir=reports_dir,
    )
    assert "error" not in result
    assert "regressions" in result
    assert result["improvements"] == ["intent_coverage улучшилось"]


def test_analyzer_returns_error_for_missing_run(tmp_path: Path, mock_proxy_client: Any) -> None:
    result = evolution.invoke_metric_analyzer(
        run_id="missing-run",
        client=mock_proxy_client,
        reports_dir=tmp_path,
    )
    assert "error" in result


def test_analyzer_returns_error_when_neither_run_id_nor_basket(
    tmp_path: Path, mock_proxy_client: Any
) -> None:
    result = evolution.invoke_metric_analyzer(client=mock_proxy_client, reports_dir=tmp_path)
    assert "error" in result


# ---------------------------------------------------------------------------
# run_evolution_cycle
# ---------------------------------------------------------------------------


def test_run_evolution_cycle_logs_lead_time(tmp_path: Path) -> None:
    """Полный цикл с замоканными генератором/runner/analyzer.
    Проверяем, что lead_time_metrics проставляется в report.json."""
    output = tmp_path / "reports"
    output.mkdir()
    run_id = "20260428-150000-finance_agent"
    _write_run_report(output, run_id=run_id)

    def fake_generator(**kwargs: Any) -> list[Scenario]:
        return []

    def fake_runner(**kwargs: Any) -> RunReport:
        return RunReport.model_validate_json(
            (output / run_id / "report.json").read_text(encoding="utf-8")
        )

    def fake_analyzer(**kwargs: Any) -> dict[str, Any]:
        return {"regressions": [], "improvements": []}

    history = evolution.run_evolution_cycle(
        system="finance_agent",
        rounds=1,
        output_dir=output,
        basket_root=tmp_path / "baskets",
        generator_fn=fake_generator,
        runner_fn=fake_runner,
        analyzer_fn=fake_analyzer,
    )
    assert len(history) == 1
    entry = history[0]
    assert entry["run_id"] == run_id
    assert "scenario_generation_seconds" in entry["lead_time_metrics"]
    assert "regression_run_seconds" in entry["lead_time_metrics"]
    assert "total_cycle_seconds" in entry["lead_time_metrics"]

    # report.json должен содержать lead_time_metrics
    persisted = RunReport.model_validate_json(
        (output / run_id / "report.json").read_text(encoding="utf-8")
    )
    assert persisted.lead_time_metrics is not None
    assert persisted.lead_time_metrics["scenario_generation_seconds"] >= 0


def test_run_evolution_cycle_multiple_rounds(tmp_path: Path) -> None:
    output = tmp_path / "reports"
    output.mkdir()
    run_id = "20260428-150000-finance_agent"
    _write_run_report(output, run_id=run_id)

    runner_calls = {"n": 0}

    def fake_runner(**kwargs: Any) -> RunReport:
        runner_calls["n"] += 1
        return RunReport.model_validate_json(
            (output / run_id / "report.json").read_text(encoding="utf-8")
        )

    history = evolution.run_evolution_cycle(
        system="finance_agent",
        rounds=3,
        output_dir=output,
        basket_root=tmp_path / "baskets",
        generator_fn=lambda **k: [],
        runner_fn=fake_runner,
        analyzer_fn=lambda **k: {},
    )
    assert len(history) == 3
    assert runner_calls["n"] == 3
    assert [h["round"] for h in history] == [1, 2, 3]


# ---------------------------------------------------------------------------
# _next_scenario_number
# ---------------------------------------------------------------------------


def test_next_scenario_number_on_empty_basket(tmp_path: Path) -> None:
    assert evolution._next_scenario_number("finance_agent", tmp_path / "empty") == 1


def test_next_scenario_number_after_existing(tmp_path: Path) -> None:
    basket = tmp_path / "basket"
    _make_basket_with_scenario(basket, "SCN-FIN-005")
    _make_basket_with_scenario(basket, "SCN-FIN-016")
    assert evolution._next_scenario_number("finance_agent", basket) == 17


def test_generator_prompt_contains_finance_single_turn_constraint(tmp_path: Path) -> None:
    """Регрессия из E2E: генератор должен явно запрещать multi_turn для finance."""
    prompt = evolution._build_generator_prompt(
        system="finance_agent",
        target_count=2,
        categories=["functional"],
        basket_dir=tmp_path / "empty",
    )
    assert "FinanceAgent" in prompt
    assert "single_turn" in prompt
    assert "НЕ используй type=multi_turn" in prompt


def test_generator_prompt_contains_travel_multi_turn_constraint(tmp_path: Path) -> None:
    prompt = evolution._build_generator_prompt(
        system="travel_agent",
        target_count=2,
        categories=["functional"],
        basket_dir=tmp_path / "empty",
    )
    assert "TravelAgent" in prompt
    assert "multi_turn" in prompt
    assert "conversation_turns" in prompt
    assert "НЕ используй type=single_turn" in prompt


def test_generator_prompt_includes_few_shot_when_basket_not_empty(
    tmp_path: Path,
) -> None:
    """Если корзина уже не пуста — в prompt вшивается ≥1 few-shot пример."""
    basket = tmp_path / "basket"
    _make_basket_with_scenario(basket, "SCN-FIN-001")
    _make_basket_with_scenario(basket, "SCN-FIN-002")
    prompt = evolution._build_generator_prompt(
        system="finance_agent",
        target_count=1,
        categories=["functional"],
        basket_dir=basket,
    )
    assert "ПРИМЕРЫ УЖЕ ВАЛИДНЫХ СЦЕНАРИЕЙ" in prompt
    assert "SCN-FIN-001" in prompt
    assert "SCN-FIN-002" in prompt


def test_generator_prompt_no_few_shot_for_empty_basket(tmp_path: Path) -> None:
    """Пустая корзина — не вшиваем few-shot, чтобы не падать на пустоте."""
    prompt = evolution._build_generator_prompt(
        system="finance_agent",
        target_count=1,
        categories=["functional"],
        basket_dir=tmp_path / "empty",
    )
    assert "ПРИМЕРЫ УЖЕ ВАЛИДНЫХ" not in prompt
