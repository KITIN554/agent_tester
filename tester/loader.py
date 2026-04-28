"""Загрузчик YAML-сценариев из корзины (spec 02)."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError
from rich.console import Console

from .models import Scenario

_console = Console(stderr=True)


def load_scenario(path: Path) -> Scenario:
    """Загружает один YAML-файл и валидирует его как Scenario.

    Pydantic-модель `Scenario` уже проверяет регэксп ID, соответствие
    system/префикса и инварианты single_turn/multi_turn. Здесь мы только
    оборачиваем ошибки в ValueError с указанием пути к файлу.

    Raises:
        ValueError: при ошибке чтения, парсинга YAML или валидации Pydantic.
    """
    if not path.exists():
        raise ValueError(f"Файл сценария не найден: {path}")

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ValueError(f"Не удалось прочитать {path}: {e}") from e

    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as e:
        raise ValueError(f"Невалидный YAML в {path}: {e}") from e

    if not isinstance(data, dict):
        raise ValueError(
            f"Ожидался YAML-объект на верхнем уровне в {path}, получено: {type(data).__name__}"
        )

    try:
        return Scenario.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"Сценарий в {path} не прошёл валидацию: {e}") from e


def load_basket(basket_dir: Path) -> list[Scenario]:
    """Загружает все *.yaml-сценарии из директории корзины.

    Файлы обрабатываются в алфавитном порядке. Невалидные пропускаются с
    предупреждением в stderr; возвращаются только успешно загруженные.
    """
    if not basket_dir.exists() or not basket_dir.is_dir():
        raise ValueError(f"Директория корзины не найдена: {basket_dir}")

    scenarios: list[Scenario] = []
    for path in sorted(basket_dir.glob("*.yaml")):
        try:
            scenarios.append(load_scenario(path))
        except ValueError as e:
            _console.print(f"[yellow]⚠ Пропуск {path.name}: {e}[/yellow]")
            continue
    return scenarios


__all__ = ["load_scenario", "load_basket"]
