# 08. CLI агента-тестировщика

## Цель
Дать единый интерфейс командной строки для запуска регрессионных прогонов, генерации отчётов и проверки корзин.

## Связь с диссертацией
- Раздел 2.2.5 — Протокол регрессионного эксперимента (CLI — entry point этого протокола)
- Раздел 1.3, требование «применимость в CI/CD» — CLI должен быть встраиваем в скрипты и GitHub Actions

## Команды

Точка входа: `tester` (через `[project.scripts]` в `pyproject.toml`).

### `tester run`

Главная команда — запуск прогона корзины.

```bash
tester run --basket baskets/finance_agent [--output reports/runs] [--judge-model MODEL] [--parallel 4] [--max-scenarios N]
```

Параметры:
- `--basket` (обязательный) — путь к директории корзины
- `--output` (по умолчанию `reports/runs`) — куда писать отчёты
- `--judge-model` (опционально) — переопределить модель судьи
- `--parallel` (по умолчанию 4) — сколько сценариев гнать параллельно через asyncio
- `--max-scenarios` (опционально) — ограничить число сценариев (для отладки)

Выход:
- Печатает в терминал прогресс-бар через `rich.progress`
- Сохраняет артефакты через `reporter.save_run_artifacts`
- В конце печатает сводку: gate decision, RQS/PQS/RS/SS/ES, путь к HTML-отчёту
- Exit code:
  - 0 если gate ALLOW
  - 1 если CONDITIONAL_ALLOW
  - 2 если BLOCK
  - 3 если внутренняя ошибка

### `tester validate`

Проверка корзины без запуска (быстро).

```bash
tester validate --basket baskets/finance_agent
```

Что делает:
- Загружает все YAML, валидирует через Pydantic
- Печатает количество сценариев по категориям
- Выводит ошибки валидации с указанием файла и проблемы
- Exit code 0 если все валидны, 1 если ошибки

### `tester baseline`

Показать или установить baseline.

```bash
# Показать текущий baseline
tester baseline --basket finance_agent

# Установить указанный прогон как baseline (создаёт симлинк)
tester baseline --basket finance_agent --set 20260428-153012-finance_agent
```

Симлинк `reports/runs/baseline_<basket>` указывает на каталог baseline-прогона. Используется в orchestrator при автоматическом сравнении.

### `tester report`

Открыть HTML-отчёт прогона (через `webbrowser.open`).

```bash
tester report 20260428-153012-finance_agent
# или последний:
tester report --latest --basket finance_agent
```

### `tester compare`

Краткое сравнение двух прогонов в терминале.

```bash
tester compare 20260427-103045-finance_agent 20260428-153012-finance_agent
```

Выводит таблицу: метрика | прогон 1 | прогон 2 | дельта.

## Реализация

```python
# tester/cli.py
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

console = Console()


@click.group()
@click.version_option("0.1.0")
def main():
    """Agent Tester — методология тестирования агентских систем."""


@main.command()
@click.option("--basket", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--output", default="reports/runs", type=click.Path(path_type=Path))
@click.option("--judge-model", default=None)
@click.option("--parallel", default=4, type=int)
@click.option("--max-scenarios", default=None, type=int)
def run(basket: Path, output: Path, judge_model: str | None, parallel: int, max_scenarios: int | None):
    """Запустить прогон корзины."""
    from .orchestrator import run_basket
    from .gate import GateDecision

    output.mkdir(parents=True, exist_ok=True)

    try:
        report = run_basket(
            basket_dir=basket,
            output_dir=output,
            judge_model=judge_model,
            parallel=parallel,
            max_scenarios=max_scenarios,
            console=console,
        )
    except Exception as e:
        console.print(f"[red]Ошибка прогона: {e}[/red]")
        sys.exit(3)

    # Сводка
    console.rule("[bold]Сводка прогона")
    console.print(f"Run ID:    {report.run_id}")
    console.print(f"Basket:    {report.basket}")
    console.print(f"Сценариев: {report.total_scenarios}, прошло: {report.passed_count}, провалов: {report.failed_count}")
    console.print(f"Pass rate: {report.pass_rate:.2%}")
    console.print()
    console.print(f"RQS: {report.aggregate_metrics.rqs:.3f}")
    console.print(f"PQS: {report.aggregate_metrics.pqs:.3f}")
    console.print(f"RS:  {report.aggregate_metrics.rs:.3f}")
    console.print(f"SS:  {report.aggregate_metrics.ss:.3f}")
    console.print(f"ES:  {report.aggregate_metrics.es:.3f}")
    console.print()

    decision_color = {"allow": "green", "conditional_allow": "yellow", "block": "red"}[report.gate_decision]
    console.print(f"GATE: [{decision_color}]{report.gate_decision.upper()}[/{decision_color}]")

    if report.gate_reasons:
        console.print("Обоснование:")
        for r in report.gate_reasons:
            console.print(f"  - {r}")

    html_path = output / report.run_id / "index.html"
    console.print(f"\nHTML-отчёт: file://{html_path.absolute()}")

    if report.gate_decision == "allow":
        sys.exit(0)
    elif report.gate_decision == "conditional_allow":
        sys.exit(1)
    else:
        sys.exit(2)


@main.command()
@click.option("--basket", required=True, type=click.Path(exists=True, path_type=Path))
def validate(basket: Path):
    """Проверить YAML-сценарии корзины."""
    from .loader import load_basket
    from collections import Counter

    try:
        scenarios = load_basket(basket)
    except Exception as e:
        console.print(f"[red]Ошибка загрузки: {e}[/red]")
        sys.exit(1)

    console.print(f"[green]✓ Загружено сценариев: {len(scenarios)}[/green]")
    by_category = Counter(s.category.value for s in scenarios)
    by_type = Counter(s.type.value for s in scenarios)

    console.print("\nПо категориям:")
    for cat, count in sorted(by_category.items(), key=lambda x: -x[1]):
        console.print(f"  {cat:15s} {count:3d}")
    console.print("\nПо типам:")
    for t, count in by_type.items():
        console.print(f"  {t:15s} {count:3d}")


@main.command()
@click.argument("run_id", required=False)
@click.option("--latest", is_flag=True)
@click.option("--basket", default=None)
def report(run_id: str | None, latest: bool, basket: str | None):
    """Открыть HTML-отчёт прогона."""
    import webbrowser

    if latest and basket:
        # найти последний прогон по корзине
        from dashboard.data_loader import list_runs
        runs = list_runs(basket=basket)
        if not runs:
            console.print(f"[red]Нет прогонов для корзины {basket}[/red]")
            sys.exit(1)
        run_id = runs[0]["run_id"]
    elif not run_id:
        console.print("[red]Укажи run_id или --latest --basket NAME[/red]")
        sys.exit(1)

    path = Path("reports/runs") / run_id / "index.html"
    if not path.exists():
        console.print(f"[red]Отчёт не найден: {path}[/red]")
        sys.exit(1)

    webbrowser.open(f"file://{path.absolute()}")
    console.print(f"Открыт: {path}")


@main.command()
@click.argument("run_a")
@click.argument("run_b")
def compare(run_a: str, run_b: str):
    """Сравнение двух прогонов в терминале."""
    from rich.table import Table
    from .models import RunReport

    a = RunReport.model_validate_json(Path(f"reports/runs/{run_a}/report.json").read_text())
    b = RunReport.model_validate_json(Path(f"reports/runs/{run_b}/report.json").read_text())

    table = Table(title=f"{run_a} vs {run_b}")
    table.add_column("Метрика")
    table.add_column(run_a, justify="right")
    table.add_column(run_b, justify="right")
    table.add_column("Δ", justify="right")

    for m in ["rqs", "pqs", "rs", "ss", "es"]:
        v_a = getattr(a.aggregate_metrics, m)
        v_b = getattr(b.aggregate_metrics, m)
        delta = v_b - v_a
        sign = "+" if delta >= 0 else ""
        color = "green" if delta >= 0 else "red"
        table.add_row(m.upper(), f"{v_a:.3f}", f"{v_b:.3f}", f"[{color}]{sign}{delta:.3f}[/{color}]")

    console.print(table)


if __name__ == "__main__":
    main()
```

## Регистрация в pyproject.toml

Уже есть в текущем `pyproject.toml`:

```toml
[project.scripts]
tester = "tester.cli:main"
```

После `pip install -e .` команда `tester` доступна глобально в окружении.

## Acceptance criteria

- [ ] `tester --help` показывает все команды (run, validate, report, compare, baseline)
- [ ] `tester run --basket baskets/finance_agent` прогоняет корзину и сохраняет отчёт
- [ ] `tester validate --basket baskets/finance_agent` валидирует все сценарии
- [ ] `tester report --latest --basket finance_agent` открывает HTML в браузере
- [ ] `tester compare RUN_A RUN_B` показывает таблицу дельт
- [ ] Exit codes: 0 (allow), 1 (conditional), 2 (block), 3 (error)
- [ ] Прогресс-бар через rich виден во время run
- [ ] `pytest tests/test_cli.py` зелёный (через `click.testing.CliRunner`)
- [ ] `ruff check tester/cli.py` зелёный

## Не-цели

- Команды `tester evolve` (генерация сценариев) — это spec 10
- Интерактивный режим (как в `claude`) — не нужен
- Команды для работы с baseline через GitHub Actions API — отдельная задача
