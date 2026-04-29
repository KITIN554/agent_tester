"""Эволюционный цикл (spec 10): генератор сценариев + анализатор прогонов.

Использует те же proxyapi.ru-вызовы, что и судья, чтобы не плодить SDK.
Промпт sub-agent'а берётся из тела .claude/agents/<name>.md (frontmatter
парсится отдельно, тело используется как system-сообщение для LLM).

Защита ядра (spec 10): эта функциональность создаёт только новые YAML
в `baskets/<system>/` и читает `systems/<system>/`. Никаких записей в
`tester/metrics.py | gate.py | judge.py | models.py` модуль не делает.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console

from .models import RunReport, Scenario

_console = Console(stderr=True)

_SUBAGENTS_DIR = Path(".claude/agents")
_SYSTEMS_DIR = Path("systems")
_BASKETS_DIR = Path("baskets")
_REPORTS_DIR = Path("reports/runs")

_SYSTEM_PREFIX = {"finance_agent": "FIN", "travel_agent": "TRV"}
_DEFAULT_CATEGORIES = ("functional", "edge_case", "negative", "safety")


# ---------------------------------------------------------------------------
# Sub-agent loading
# ---------------------------------------------------------------------------


def _parse_subagent(path: Path) -> tuple[dict[str, Any], str]:
    """Разделяет .claude/agents/<name>.md на frontmatter и тело."""
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if not match:
        return {}, text
    frontmatter = yaml.safe_load(match.group(1)) or {}
    body = match.group(2).strip()
    return frontmatter, body


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _next_scenario_number(system: str, basket_dir: Path) -> int:
    prefix = _SYSTEM_PREFIX.get(system)
    if prefix is None:
        raise ValueError(f"Неизвестная система: {system}")
    if not basket_dir.exists():
        return 1
    existing: list[int] = []
    for path in basket_dir.glob(f"SCN-{prefix}-*.yaml"):
        m = re.match(rf"SCN-{prefix}-(\d{{3}})$", path.stem)
        if m:
            existing.append(int(m.group(1)))
    return max(existing, default=0) + 1


def _build_default_client() -> Any:
    """Создаёт OpenAI-клиент через proxyapi (как везде в проекте)."""
    from openai import OpenAI

    return OpenAI(
        api_key=os.environ["PROXY_API_KEY"],
        base_url=os.environ.get("PROXY_BASE_URL", "https://api.proxyapi.ru/openrouter/v1"),
    )


def _build_system_context(system: str, systems_dir: Path = _SYSTEMS_DIR) -> str:
    """Собирает компактный контекст: tools.py / prompts.py / agent.py системы."""
    sys_dir = systems_dir / system
    parts: list[str] = []
    for fname in ("tools.py", "prompts.py", "agent.py"):
        path = sys_dir / fname
        if path.exists():
            parts.append(f"### {fname}\n```python\n{path.read_text(encoding='utf-8')}\n```")
    return "\n\n".join(parts) if parts else "(код системы недоступен)"


def _existing_scenario_summary(basket_dir: Path) -> str:
    """Текст со списком существующих ID и описаний для дедупликации."""
    if not basket_dir.exists():
        return "(пусто)"
    lines: list[str] = []
    for path in sorted(basket_dir.glob("SCN-*-*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if isinstance(data, dict):
            lines.append(f"- {data.get('id', path.stem)}: {data.get('description', '')}")
    return "\n".join(lines) if lines else "(пусто)"


# ---------------------------------------------------------------------------
# invoke_scenario_generator
# ---------------------------------------------------------------------------


def invoke_scenario_generator(
    system: str,
    target_count: int,
    categories: list[str] | None = None,
    *,
    client: Any = None,
    model: str | None = None,
    basket_dir: Path | None = None,
) -> list[Scenario]:
    """Программный вызов scenario-generator: LLM-вызов + сохранение YAML.

    Возвращает список валидных Scenario. Невалидные пропускаются с warning.
    Любая ошибка LLM/парсинга → пустой список (наружу не пробрасываем).
    """
    if categories is None:
        categories = list(_DEFAULT_CATEGORIES)
    if basket_dir is None:
        basket_dir = _BASKETS_DIR / system

    try:
        _, agent_body = _parse_subagent(_SUBAGENTS_DIR / "scenario-generator.md")
    except FileNotFoundError:
        _console.print("[red]Не найден .claude/agents/scenario-generator.md[/red]")
        return []

    if client is None:
        try:
            client = _build_default_client()
        except KeyError:
            _console.print("[red]PROXY_API_KEY не установлен[/red]")
            return []

    if model is None:
        model = os.environ.get("LLM_MODEL", "mistralai/mistral-medium-3.1")

    user_prompt = _build_generator_prompt(
        system=system,
        target_count=target_count,
        categories=categories,
        basket_dir=basket_dir,
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": agent_body},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=4000,
        )
    except Exception as exc:  # noqa: BLE001
        _console.print(f"[red]Ошибка LLM (генератор): {exc}[/red]")
        return []

    raw_content = response.choices[0].message.content or "{}"
    try:
        data = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        _console.print(f"[red]Невалидный JSON генератора: {exc}[/red]")
        return []

    raw_scenarios = data.get("scenarios", []) if isinstance(data, dict) else []
    if not isinstance(raw_scenarios, list):
        return []

    return _save_generated_scenarios(system, basket_dir, raw_scenarios)


_SYSTEM_TYPE_CONSTRAINT: dict[str, str] = {
    "finance_agent": (
        "АРХИТЕКТУРНОЕ ОГРАНИЧЕНИЕ: FinanceAgent поддерживает ТОЛЬКО single_turn. "
        "Все сценарии должны иметь type=single_turn и input.user_message; "
        "НЕ используй type=multi_turn и input.conversation_turns."
    ),
    "travel_agent": (
        "АРХИТЕКТУРНОЕ ОГРАНИЧЕНИЕ: TravelAgent поддерживает ТОЛЬКО multi_turn. "
        "Все сценарии должны иметь type=multi_turn и input.conversation_turns "
        "(минимум 2 user-реплики); НЕ используй type=single_turn."
    ),
}


def _build_generator_prompt(
    *, system: str, target_count: int, categories: list[str], basket_dir: Path
) -> str:
    context = _build_system_context(system)
    existing = _existing_scenario_summary(basket_dir)
    few_shot = _load_few_shot_examples(basket_dir)
    type_rule = _SYSTEM_TYPE_CONSTRAINT.get(system, "")
    is_multi_turn = system == "travel_agent"
    example_type = "multi_turn" if is_multi_turn else "single_turn"
    example_input: dict[str, Any] = (
        {
            "conversation_turns": [
                {"role": "user", "content": "первая реплика"},
                {"role": "user", "content": "вторая реплика"},
            ],
            "available_tools": ["имя_инструмента"],
        }
        if is_multi_turn
        else {
            "user_message": "Реплика пользователя",
            "available_tools": ["имя_инструмента"],
        }
    )
    skeleton = json.dumps(
        {
            "scenarios": [
                {
                    "category": "functional",
                    "type": example_type,
                    "description": "Краткое описание на русском",
                    "system": system,
                    "input": {
                        **example_input,
                        "limits": {
                            "max_steps": 5,
                            "max_latency_s": 10,
                            "max_cost_usd": 0.10,
                        },
                    },
                    "expectations": {
                        "must_contain": ["подстрока"],
                        "required_tool_calls": [
                            {
                                "name": "имя_инструмента",
                                "parameters": {"key": "value"},
                                "optional": False,
                            }
                        ],
                        "forbidden_tool_calls": [],
                        "numeric_response": "required",
                    },
                    "rubrics": [
                        "factual_correctness",
                        "intent_coverage",
                        "groundedness",
                        "tone_compliance",
                    ],
                    "thresholds": {
                        "factual_correctness": "correct",
                        "groundedness": "pass",
                        "intent_coverage": "full",
                        "tone_compliance": 4.0,
                    },
                }
            ]
        },
        ensure_ascii=False,
        indent=2,
    )
    type_section = f"\n{type_rule}\n\n" if type_rule else "\n"
    return (
        f"Сгенерируй {target_count} новых тест-сценариев для системы {system}.\n\n"
        f"Категории на выбор: {', '.join(categories)}.\n"
        f"{type_section}"
        f"СУЩЕСТВУЮЩИЕ СЦЕНАРИИ (НЕ дублируй описания и сути):\n{existing}\n\n"
        f"КОД ТЕСТИРУЕМОЙ СИСТЕМЫ:\n{context}\n\n"
        "ОБЯЗАТЕЛЬНО соблюдай схему из примера:\n"
        "- rubrics — это СПИСОК строк (например, "
        '["factual_correctness", "intent_coverage"]), а не словарь\n'
        "- thresholds — словарь, отдельное поле от rubrics\n"
        "- для negative-сценариев expectations.refusal_expected = true И "
        "forbidden_tool_calls — непустой список\n"
        "- numeric_response — одно из {required, optional, forbidden}, "
        "никаких других значений\n"
        "- для multi_turn вместо input.user_message используй "
        'input.conversation_turns: [{"role": "user", "content": "..."}, ...]\n\n'
        "Верни СТРОГО JSON-объект ровно по этому шаблону:\n"
        f"{skeleton}\n\n"
        f"{few_shot}\n"
        "ID не указывай — стенд проставит сам. Никакого текста вне JSON."
    )


def _load_few_shot_examples(basket_dir: Path) -> str:
    """Берёт до 2 уже валидных YAML из корзины как few-shot.

    Если корзина пустая — возвращает пустую строку. Сценарии передаются
    как сырой YAML-текст (LLM хорошо его понимает) с пометкой «как пример,
    не копируй дословно».
    """
    if not basket_dir.exists():
        return ""
    paths = sorted(basket_dir.glob("SCN-*-*.yaml"))[:2]
    if not paths:
        return ""
    blocks: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8").strip()
        blocks.append(f"--- {path.name} ---\n{text}")
    joined = "\n\n".join(blocks)
    return (
        "ПРИМЕРЫ УЖЕ ВАЛИДНЫХ СЦЕНАРИЕЙ из этой корзины (для структуры, "
        "НЕ копируй дословно — придумывай новые ситуации):\n\n"
        f"{joined}\n"
    )


def _save_generated_scenarios(
    system: str, basket_dir: Path, raw_scenarios: list[Any]
) -> list[Scenario]:
    basket_dir.mkdir(parents=True, exist_ok=True)
    next_n = _next_scenario_number(system, basket_dir)
    prefix = _SYSTEM_PREFIX[system]
    saved: list[Scenario] = []

    for raw in raw_scenarios:
        if not isinstance(raw, dict):
            continue
        candidate = {
            **raw,
            "id": f"SCN-{prefix}-{next_n:03d}",
            "system": system,
        }
        try:
            scenario = Scenario.model_validate(candidate)
        except Exception as exc:  # noqa: BLE001 — мусор просто пропускаем
            _console.print(f"[yellow]Невалидный сценарий пропущен: {exc}[/yellow]")
            continue

        path = basket_dir / f"{scenario.id}.yaml"
        path.write_text(
            yaml.safe_dump(
                scenario.model_dump(mode="json"),
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        saved.append(scenario)
        next_n += 1

    return saved


# ---------------------------------------------------------------------------
# invoke_metric_analyzer
# ---------------------------------------------------------------------------


_ANALYSIS_DIR = Path("reports/analysis")


def invoke_metric_analyzer(
    run_id: str | None = None,
    basket: str | None = None,
    *,
    client: Any = None,
    model: str | None = None,
    reports_dir: Path = _REPORTS_DIR,
    save_to: Path | None = _ANALYSIS_DIR,
) -> dict[str, Any]:
    """Анализирует прогон, возвращает структурированный словарь.

    Если run_id не задан — берёт последний non-block прогон по basket.
    При любой ошибке возвращает {"error": ...}, исключение не пробрасывает.
    Если задан save_to — после получения результата кладёт `<run_id>.json`
    и `<run_id>.md` в этот каталог (создаёт его при необходимости).
    """
    report_path = _resolve_report_path(run_id, basket, reports_dir)
    if isinstance(report_path, dict):
        return report_path  # содержит ключ "error"

    try:
        _, agent_body = _parse_subagent(_SUBAGENTS_DIR / "metric-analyzer.md")
    except FileNotFoundError:
        return {"error": "metric-analyzer.md не найден"}

    if client is None:
        try:
            client = _build_default_client()
        except KeyError:
            return {"error": "PROXY_API_KEY не установлен"}

    if model is None:
        model = os.environ.get("LLM_MODEL", "mistralai/mistral-medium-3.1")

    report_text = report_path.read_text(encoding="utf-8")
    user_prompt = (
        "Проанализируй результаты прогона.\n\n"
        f"REPORT.JSON:\n{report_text}\n\n"
        "Верни СТРОГО JSON со структурой:\n"
        '{ "run_id": "...", '
        '"regressions": [{"scenario_id": "...", "rubric": "...", '
        '"root_cause": "...", "suggested_fix": "..."}], '
        '"improvements": [...], '
        '"patterns": [...], '
        '"recommendations": [...] }\n\n'
        "Никакого текста вне JSON."
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": agent_body},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=2000,
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": f"LLM error: {exc}"}

    raw_content = response.choices[0].message.content or "{}"
    try:
        result = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        return {"error": f"parse error: {exc}"}

    if save_to is not None:
        _persist_analysis(result, run_id=report_path.parent.name, save_to=save_to)
    return result


def _persist_analysis(result: dict[str, Any], *, run_id: str, save_to: Path) -> None:
    """Кладёт <run_id>.json и <run_id>.md в save_to."""
    save_to.mkdir(parents=True, exist_ok=True)
    (save_to / f"{run_id}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (save_to / f"{run_id}.md").write_text(
        _render_analysis_markdown(result, run_id),
        encoding="utf-8",
    )


def _render_analysis_markdown(result: dict[str, Any], run_id: str) -> str:
    if "error" in result:
        return f"# Анализ прогона {run_id}\n\nОшибка анализа: {result['error']}\n"

    lines = [f"# Анализ прогона {run_id}", ""]
    for section, title in (
        ("regressions", "Регрессии"),
        ("improvements", "Улучшения"),
        ("patterns", "Паттерны"),
        ("recommendations", "Рекомендации"),
    ):
        items = result.get(section) or []
        lines.append(f"## {title}")
        if not items:
            lines.append("— ничего не выявлено.")
        else:
            for item in items:
                if isinstance(item, dict):
                    head = item.get("scenario_id") or item.get("name") or "запись"
                    rubric = item.get("rubric")
                    cause = item.get("root_cause") or item.get("cause") or ""
                    fix = item.get("suggested_fix") or item.get("fix") or ""
                    lines.append(f"- **{head}**" + (f" / {rubric}" if rubric else ""))
                    if cause:
                        lines.append(f"  - причина: {cause}")
                    if fix:
                        lines.append(f"  - предложено: {fix}")
                else:
                    lines.append(f"- {item}")
        lines.append("")
    return "\n".join(lines)


def _resolve_report_path(
    run_id: str | None, basket: str | None, reports_dir: Path
) -> Path | dict[str, str]:
    if run_id:
        path = reports_dir / run_id / "report.json"
        if not path.exists():
            return {"error": f"Прогон {run_id} не найден"}
        return path
    if basket:
        # Берём последний прогон корзины ЛЮБОГО гейта: block-прогоны
        # содержат самую ценную диагностику, отбрасывать их нельзя.
        latest = _latest_run_path(reports_dir, basket)
        if latest is None:
            return {"error": f"Нет прогонов для корзины {basket}"}
        return latest
    return {"error": "Укажи run_id или basket"}


def _latest_run_path(reports_dir: Path, basket: str) -> Path | None:
    """Возвращает report.json самого свежего прогона корзины (без фильтра по gate).

    run_id содержит таймстамп в начале имени, поэтому простая лексикографическая
    сортировка убывания даёт правильный «новые сверху». Мусорные / нечитаемые
    отчёты пропускаются.
    """
    if not reports_dir.exists():
        return None
    for run_path in sorted(reports_dir.glob("*/report.json"), reverse=True):
        try:
            report = RunReport.model_validate_json(run_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if report.basket == basket:
            return run_path
    return None


# ---------------------------------------------------------------------------
# run_evolution_cycle
# ---------------------------------------------------------------------------


def run_evolution_cycle(
    system: str,
    rounds: int = 1,
    *,
    target_count: int = 3,
    categories: list[str] | None = None,
    output_dir: Path = _REPORTS_DIR,
    basket_root: Path = _BASKETS_DIR,
    generator_fn: Callable[..., list[Scenario]] | None = None,
    analyzer_fn: Callable[..., dict[str, Any]] | None = None,
    runner_fn: Callable[..., RunReport] | None = None,
) -> list[dict[str, Any]]:
    """Полный эволюционный цикл (spec 10).

    Шаги (повторить N раз):
        1) generate — добавить новые сценарии в корзину
        2) run — прогнать корзину через orchestrator
        3) analyze — получить структурированные рекомендации
        4) залогировать lead_time_metrics в report.json

    Возвращает list[dict] с историей циклов: scenario_count, run_id,
    lead_time_metrics, analysis. DI-фабрики для тестов.
    """
    if generator_fn is None:
        generator_fn = invoke_scenario_generator
    if analyzer_fn is None:
        analyzer_fn = invoke_metric_analyzer
    if runner_fn is None:
        from .orchestrator import run_basket as default_runner

        runner_fn = default_runner

    basket_dir = basket_root / system
    history: list[dict[str, Any]] = []

    for round_idx in range(rounds):
        gen_start = time.monotonic()
        new_scenarios = generator_fn(
            system=system,
            target_count=target_count,
            categories=categories,
            basket_dir=basket_dir,
        )
        gen_seconds = time.monotonic() - gen_start

        run_start = time.monotonic()
        report = runner_fn(basket_dir=basket_dir, output_dir=output_dir)
        run_seconds = time.monotonic() - run_start

        analysis_start = time.monotonic()
        analysis = analyzer_fn(run_id=report.run_id, reports_dir=output_dir)
        analysis_seconds = time.monotonic() - analysis_start

        lead_time = {
            "scenario_generation_seconds": round(gen_seconds, 2),
            "regression_run_seconds": round(run_seconds, 2),
            "analysis_seconds": round(analysis_seconds, 2),
            "total_cycle_seconds": round(gen_seconds + run_seconds + analysis_seconds, 2),
        }
        _persist_lead_time(report, output_dir, lead_time)

        history.append(
            {
                "round": round_idx + 1,
                "scenario_count": len(new_scenarios),
                "run_id": report.run_id,
                "lead_time_metrics": lead_time,
                "analysis": analysis,
            }
        )

    return history


def _persist_lead_time(
    report: RunReport,
    output_dir: Path,
    metrics: dict[str, float],
) -> None:
    """Перезаписывает report.json новой копией с заполненным lead_time_metrics."""
    updated = report.model_copy(update={"lead_time_metrics": metrics})
    path = output_dir / report.run_id / "report.json"
    if path.exists():
        path.write_text(updated.model_dump_json(indent=2), encoding="utf-8")


__all__ = [
    "invoke_scenario_generator",
    "invoke_metric_analyzer",
    "run_evolution_cycle",
]
