"""Тесты YAML-загрузчика сценариев (tester/loader.py)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from tester.loader import load_basket, load_scenario
from tester.models import ScenarioCategory, ScenarioType

REPO_ROOT = Path(__file__).resolve().parents[1]
FINANCE_BASKET = REPO_ROOT / "baskets" / "finance_agent"
TRAVEL_BASKET = REPO_ROOT / "baskets" / "travel_agent"


def _write_yaml(path: Path, data: dict[str, Any]) -> Path:
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def test_load_scenario_valid(tmp_path: Path, sample_scenario: dict[str, Any]) -> None:
    path = _write_yaml(tmp_path / "SCN-FIN-001.yaml", sample_scenario)
    scenario = load_scenario(path)
    assert scenario.id == "SCN-FIN-001"
    assert scenario.type is ScenarioType.SINGLE_TURN
    assert scenario.category is ScenarioCategory.FUNCTIONAL


def test_load_scenario_invalid_id_raises(tmp_path: Path, sample_scenario: dict[str, Any]) -> None:
    bad = {**sample_scenario, "id": "FIN-001"}  # неправильный префикс
    path = _write_yaml(tmp_path / "bad.yaml", bad)

    with pytest.raises(ValueError) as exc:
        load_scenario(path)
    assert "bad.yaml" in str(exc.value)
    assert "не прошёл валидацию" in str(exc.value)


def test_load_scenario_malformed_yaml_raises(tmp_path: Path) -> None:
    path = tmp_path / "broken.yaml"
    path.write_text("id: SCN-FIN-001\n  bad indent: [", encoding="utf-8")

    with pytest.raises(ValueError, match="Невалидный YAML"):
        load_scenario(path)


def test_load_basket_three_scenarios(tmp_path: Path, sample_scenario: dict[str, Any]) -> None:
    _write_yaml(tmp_path / "SCN-FIN-001.yaml", sample_scenario)
    _write_yaml(tmp_path / "SCN-FIN-002.yaml", {**sample_scenario, "id": "SCN-FIN-002"})
    _write_yaml(tmp_path / "SCN-FIN-003.yaml", {**sample_scenario, "id": "SCN-FIN-003"})

    scenarios = load_basket(tmp_path)
    assert [s.id for s in scenarios] == ["SCN-FIN-001", "SCN-FIN-002", "SCN-FIN-003"]


def test_load_basket_skips_invalid_files(tmp_path: Path, sample_scenario: dict[str, Any]) -> None:
    _write_yaml(tmp_path / "SCN-FIN-001.yaml", sample_scenario)
    # Файл с невалидным id — должен быть пропущен с предупреждением
    _write_yaml(tmp_path / "SCN-FIN-bad.yaml", {**sample_scenario, "id": "FIN-002"})
    _write_yaml(tmp_path / "SCN-FIN-003.yaml", {**sample_scenario, "id": "SCN-FIN-003"})

    scenarios = load_basket(tmp_path)
    assert [s.id for s in scenarios] == ["SCN-FIN-001", "SCN-FIN-003"]


def test_load_basket_missing_directory_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="не найдена"):
        load_basket(tmp_path / "nonexistent")


def test_example_baskets_are_valid() -> None:
    """Каждая корзина должна содержать ≥ 15 валидных сценариев с покрытием категорий."""
    finance = load_basket(FINANCE_BASKET)
    travel = load_basket(TRAVEL_BASKET)

    assert len(finance) >= 15, f"Корзина finance_agent: {len(finance)} сценариев < 15"
    assert len(travel) >= 15, f"Корзина travel_agent: {len(travel)} сценариев < 15"

    for basket_name, scenarios in (("finance_agent", finance), ("travel_agent", travel)):
        cats = {s.category for s in scenarios}
        assert ScenarioCategory.FUNCTIONAL in cats, f"{basket_name}: нет functional"
        assert ScenarioCategory.NEGATIVE in cats, f"{basket_name}: нет negative"
        assert ScenarioCategory.SAFETY in cats, f"{basket_name}: нет safety"
        assert ScenarioCategory.EDGE_CASE in cats, f"{basket_name}: нет edge_case"

        # Negative-сценарии должны иметь refusal_expected=True и forbidden_tool_calls
        for s in scenarios:
            if s.category is ScenarioCategory.NEGATIVE:
                assert s.expectations.refusal_expected is True, (
                    f"{s.id}: refusal_expected должен быть True для negative"
                )
                assert s.expectations.forbidden_tool_calls, (
                    f"{s.id}: forbidden_tool_calls обязателен для negative"
                )

    # Базовые инварианты на якорных сценариях
    by_id = {s.id: s for s in [*finance, *travel]}
    assert by_id["SCN-FIN-001"].type is ScenarioType.SINGLE_TURN
    assert by_id["SCN-FIN-001"].category is ScenarioCategory.FUNCTIONAL
    assert by_id["SCN-TRV-001"].type is ScenarioType.MULTI_TURN
    assert by_id["SCN-TRV-001"].category is ScenarioCategory.FUNCTIONAL
