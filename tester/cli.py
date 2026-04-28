"""CLI агента-тестировщика (spec 08).

Точка входа: команда `tester` (через [project.scripts] в pyproject.toml).
Группа команд: run / validate / baseline / report / compare.

Exit codes (для встраивания в CI):
- 0 — gate ALLOW (или штатное завершение для не-run команд)
- 1 — gate CONDITIONAL_ALLOW (для run) или ошибка валидации
- 2 — gate BLOCK
- 3 — внутренняя ошибка
"""

from __future__ import annotations

import json
import webbrowser
from collections import Counter
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from .gate import load_baseline as load_baseline_report
from .loader import load_basket
from .models import GateDecision, RunReport
from .orchestrator import run_basket

console = Console()

_GATE_COLOR = {
    GateDecision.ALLOW: "green",
    GateDecision.CONDITIONAL_ALLOW: "yellow",
    GateDecision.BLOCK: "red",
}
_GATE_EXIT_CODE = {
    GateDecision.ALLOW: 0,
    GateDecision.CONDITIONAL_ALLOW: 1,
    GateDecision.BLOCK: 2,
}


@click.group()
@click.version_option("0.1.0", prog_name="tester")
def main() -> None:
    """Agent Tester — методология тестирования агентских систем."""


# ---------------------------------------------------------------------------
# tester run
# ---------------------------------------------------------------------------


@main.command()
@click.option(
    "--basket",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="Каталог корзины со сценариями YAML.",
)
@click.option(
    "--output",
    default=Path("reports/runs"),
    type=click.Path(path_type=Path),
    help="Куда писать <run_id>/... (по умолчанию reports/runs).",
)
@click.option("--judge-model", default=None, help="Переопределение модели судьи.")
@click.option("--parallel", default=4, type=int, help="Сколько сценариев параллельно.")
@click.option(
    "--max-scenarios",
    default=None,
    type=int,
    help="Ограничить корзину первыми N сценариями (для отладки).",
)
def run(
    basket: Path,
    output: Path,
    judge_model: str | None,
    parallel: int,
    max_scenarios: int | None,
) -> None:
    """Запустить прогон корзины и сохранить артефакты."""
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
    except Exception as exc:  # noqa: BLE001 — last resort, отчёт о любой ошибке
        console.print(f"[red]Ошибка прогона: {exc}[/red]")
        raise click.exceptions.Exit(3) from exc

    _print_run_summary(report, output)
    raise click.exceptions.Exit(_GATE_EXIT_CODE[report.gate_decision])


def _print_run_summary(report: RunReport, output: Path) -> None:
    console.rule("[bold]Сводка прогона")
    console.print(f"Run ID:    {report.run_id}")
    console.print(f"Basket:    {report.basket}")
    console.print(
        f"Сценариев: {report.total_scenarios}, "
        f"прошло: {report.passed_count}, "
        f"провалов: {report.failed_count}"
    )
    if report.total_scenarios > 0:
        rate = report.passed_count / report.total_scenarios
        console.print(f"Pass rate: {rate:.2%}")

    console.print()
    a = report.aggregate_metrics
    console.print(f"RQS: {a.rqs:.3f}")
    console.print(f"PQS: {a.pqs:.3f}")
    console.print(f"RS:  {a.rs:.3f}")
    console.print(f"SS:  {a.ss:.3f}")
    console.print(f"ES:  {a.es:.3f}")
    console.print()

    color = _GATE_COLOR[report.gate_decision]
    console.print(f"GATE: [{color}]{report.gate_decision.value.upper()}[/{color}]")
    if report.gate_reasons:
        console.print("Обоснование:")
        for reason in report.gate_reasons:
            console.print(f"  - {reason}")

    html_path = output / report.run_id / "index.html"
    console.print(f"\nHTML-отчёт: file://{html_path.absolute()}")


# ---------------------------------------------------------------------------
# tester validate
# ---------------------------------------------------------------------------


@main.command()
@click.option(
    "--basket",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
)
def validate(basket: Path) -> None:
    """Проверить YAML-сценарии корзины (без запуска)."""
    try:
        scenarios = load_basket(basket)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Ошибка загрузки: {exc}[/red]")
        raise click.exceptions.Exit(1) from exc

    if not scenarios:
        console.print(f"[red]✗ Корзина {basket} не содержит ни одного валидного сценария[/red]")
        raise click.exceptions.Exit(1)

    console.print(f"[green]✓ Загружено сценариев: {len(scenarios)}[/green]")
    by_category = Counter(s.category.value for s in scenarios)
    by_type = Counter(s.type.value for s in scenarios)

    console.print("\nПо категориям:")
    for cat, count in sorted(by_category.items(), key=lambda x: (-x[1], x[0])):
        console.print(f"  {cat:15s} {count:3d}")

    console.print("\nПо типам:")
    for t, count in sorted(by_type.items()):
        console.print(f"  {t:15s} {count:3d}")


# ---------------------------------------------------------------------------
# tester baseline
# ---------------------------------------------------------------------------


@main.command()
@click.option("--basket", required=True, help="Имя корзины (например, finance_agent).")
@click.option("--set", "set_run_id", default=None, help="run_id, который сделать baseline.")
@click.option(
    "--reports-dir",
    default=Path("reports/runs"),
    type=click.Path(path_type=Path),
)
def baseline(
    basket: str,
    set_run_id: str | None,
    reports_dir: Path,
) -> None:
    """Показать или установить baseline для корзины."""
    if set_run_id is not None:
        target = reports_dir / set_run_id
        if not target.exists():
            console.print(f"[red]Прогон не найден: {target}[/red]")
            raise click.exceptions.Exit(1)
        link = reports_dir / f"baseline_{basket}"
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(target.resolve())
        console.print(f"[green]✓ baseline для {basket} → {set_run_id}[/green]")
        return

    # Show mode: ищем последний non-block прогон
    report = load_baseline_report(reports_dir, basket)
    if report is None:
        console.print(f"[yellow]Нет baseline для корзины {basket}[/yellow]")
        raise click.exceptions.Exit(1)
    console.print(f"Baseline для {basket}: [bold]{report.run_id}[/bold]")
    console.print(f"  gate: {report.gate_decision.value}")
    console.print(f"  RQS={report.aggregate_metrics.rqs:.3f}")
    console.print(f"  PQS={report.aggregate_metrics.pqs:.3f}")
    console.print(f"  RS ={report.aggregate_metrics.rs:.3f}")
    console.print(f"  SS ={report.aggregate_metrics.ss:.3f}")
    console.print(f"  ES ={report.aggregate_metrics.es:.3f}")


# ---------------------------------------------------------------------------
# tester report
# ---------------------------------------------------------------------------


@main.command()
@click.argument("run_id", required=False)
@click.option("--latest", is_flag=True, help="Открыть последний прогон корзины.")
@click.option("--basket", default=None, help="Имя корзины (для --latest).")
@click.option(
    "--reports-dir",
    default=Path("reports/runs"),
    type=click.Path(path_type=Path),
)
@click.option(
    "--no-browser",
    is_flag=True,
    help="Не открывать браузер, только напечатать путь.",
)
def report(
    run_id: str | None,
    latest: bool,
    basket: str | None,
    reports_dir: Path,
    no_browser: bool,
) -> None:
    """Открыть HTML-отчёт прогона в браузере."""
    if latest:
        if not basket:
            console.print("[red]При --latest укажи --basket NAME[/red]")
            raise click.exceptions.Exit(1)
        run_id = _find_latest_run(reports_dir, basket)
        if run_id is None:
            console.print(f"[red]Нет прогонов для корзины {basket}[/red]")
            raise click.exceptions.Exit(1)
    elif not run_id:
        console.print("[red]Укажи RUN_ID или --latest --basket NAME[/red]")
        raise click.exceptions.Exit(1)

    path = reports_dir / run_id / "index.html"
    if not path.exists():
        console.print(f"[red]Отчёт не найден: {path}[/red]")
        raise click.exceptions.Exit(1)

    if not no_browser:
        webbrowser.open(f"file://{path.absolute()}")
    console.print(f"Открыт: {path}")


def _find_latest_run(reports_dir: Path, basket: str) -> str | None:
    if not reports_dir.exists():
        return None
    candidates = sorted(
        (d.name for d in reports_dir.iterdir() if d.is_dir() and d.name.endswith(f"-{basket}")),
        reverse=True,
    )
    return candidates[0] if candidates else None


# ---------------------------------------------------------------------------
# tester compare
# ---------------------------------------------------------------------------


@main.command()
@click.argument("run_a")
@click.argument("run_b")
@click.option(
    "--reports-dir",
    default=Path("reports/runs"),
    type=click.Path(path_type=Path),
)
def compare(run_a: str, run_b: str, reports_dir: Path) -> None:
    """Сравнение двух прогонов: таблица RQS/PQS/RS/SS/ES + Δ."""
    try:
        a = _load_report(reports_dir / run_a / "report.json")
        b = _load_report(reports_dir / run_b / "report.json")
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise click.exceptions.Exit(1) from exc

    table = Table(title=f"{run_a} vs {run_b}")
    table.add_column("Метрика")
    table.add_column(run_a, justify="right")
    table.add_column(run_b, justify="right")
    table.add_column("Δ", justify="right")

    for metric in ("rqs", "pqs", "rs", "ss", "es"):
        v_a = float(getattr(a.aggregate_metrics, metric))
        v_b = float(getattr(b.aggregate_metrics, metric))
        delta = v_b - v_a
        sign = "+" if delta >= 0 else ""
        color = "green" if delta >= 0 else "red"
        table.add_row(
            metric.upper(),
            f"{v_a:.3f}",
            f"{v_b:.3f}",
            f"[{color}]{sign}{delta:.3f}[/{color}]",
        )
    console.print(table)


def _load_report(path: Path) -> RunReport:
    if not path.exists():
        raise FileNotFoundError(f"Отчёт не найден: {path}")
    return RunReport.model_validate(json.loads(path.read_text(encoding="utf-8")))


# ---------------------------------------------------------------------------
# tester evolve (group)
# ---------------------------------------------------------------------------


@main.group()
def evolve() -> None:
    """Эволюционный цикл: generate / analyze / cycle (spec 10)."""


@evolve.command(name="generate")
@click.option("--system", required=True, help="Имя системы (finance_agent / travel_agent).")
@click.option("--target-count", default=10, type=int, help="Сколько сценариев сгенерировать.")
@click.option(
    "--categories",
    default=None,
    help="Список категорий через запятую (по умолчанию все).",
)
@click.option(
    "--basket-dir",
    default=None,
    type=click.Path(path_type=Path),
    help="Куда писать YAML (по умолчанию baskets/<system>).",
)
def evolve_generate(
    system: str,
    target_count: int,
    categories: str | None,
    basket_dir: Path | None,
) -> None:
    """Сгенерировать N новых сценариев через scenario-generator sub-agent."""
    from .evolution import invoke_scenario_generator

    cats = [c.strip() for c in categories.split(",")] if categories else None
    saved = invoke_scenario_generator(
        system=system,
        target_count=target_count,
        categories=cats,
        basket_dir=basket_dir,
    )
    if not saved:
        console.print("[yellow]Не удалось сгенерировать ни одного сценария.[/yellow]")
        raise click.exceptions.Exit(1)
    console.print(f"[green]✓ Сохранено сценариев: {len(saved)}[/green]")
    for s in saved:
        console.print(f"  {s.id} \\[{s.category.value}] — {s.description}")


@evolve.command(name="analyze")
@click.option("--basket", default=None, help="Имя корзины (для последнего non-block прогона).")
@click.option("--run-id", default=None, help="Конкретный run_id для анализа.")
@click.option(
    "--reports-dir",
    default=Path("reports/runs"),
    type=click.Path(path_type=Path),
)
def evolve_analyze(
    basket: str | None,
    run_id: str | None,
    reports_dir: Path,
) -> None:
    """Анализ прогона через metric-analyzer sub-agent."""
    from .evolution import invoke_metric_analyzer

    if not basket and not run_id:
        console.print("[red]Укажи --basket или --run-id[/red]")
        raise click.exceptions.Exit(1)

    result = invoke_metric_analyzer(run_id=run_id, basket=basket, reports_dir=reports_dir)
    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
        raise click.exceptions.Exit(1)

    console.print_json(data=result)


@evolve.command(name="cycle")
@click.option("--system", required=True)
@click.option("--rounds", default=1, type=int, help="Сколько раундов цикла прогнать.")
@click.option("--target-count", default=3, type=int)
@click.option(
    "--output",
    default=Path("reports/runs"),
    type=click.Path(path_type=Path),
)
def evolve_cycle(
    system: str,
    rounds: int,
    target_count: int,
    output: Path,
) -> None:
    """Полный эволюционный цикл: generate → run → analyze (× rounds)."""
    from .evolution import run_evolution_cycle

    history = run_evolution_cycle(
        system=system,
        rounds=rounds,
        target_count=target_count,
        output_dir=output,
    )
    if not history:
        console.print("[red]Цикл не сделал ни одного раунда.[/red]")
        raise click.exceptions.Exit(1)

    console.rule("[bold]История эволюционного цикла")
    for entry in history:
        console.print(
            f"Round {entry['round']}: scenarios={entry['scenario_count']}, run_id={entry['run_id']}"
        )
        lt = entry["lead_time_metrics"]
        console.print(
            f"  generation: {lt['scenario_generation_seconds']}s, "
            f"run: {lt['regression_run_seconds']}s, "
            f"analysis: {lt['analysis_seconds']}s, "
            f"total: {lt['total_cycle_seconds']}s"
        )


if __name__ == "__main__":  # pragma: no cover
    main()
