# 01. Архитектура агента-тестировщика

## Цель
Определить модули `tester/`, их обязанности и взаимодействие.

## Связь с диссертацией
- Глава 2, раздел 2.2.5 — Протокол регрессионного эксперимента (7 этапов)
- Таблица 2.8 — артефакты и контрольные точки этапов

Архитектура реализует именно эти 7 этапов: фиксация манифеста → прогон корзины → автоматическая оценка → агрегация → сравнение с эталоном → принятие решения → архивирование.

## Файловая структура
tester/
├── init.py
├── models.py        # Pydantic-модели (Scenario, Trace, Outcome, RunReport)
├── loader.py        # Загрузка YAML-сценариев из корзины
├── executor.py      # Запуск сценария на тестируемой системе
├── judge.py         # LLM-as-a-Judge / Agent-as-a-Judge
├── metrics.py       # Расчёт RQS, PQS, RS, SS, ES
├── gate.py          # Правила приёмки релиза
├── reporter.py      # Генерация HTML-отчёта
├── orchestrator.py  # Главный пайплайн: связывает всё вместе
└── cli.py           # CLI-интерфейс (click)

## Поток данных
[YAML-сценарии корзины]
↓ loader.load_basket()
[список Scenario]
↓ orchestrator
│
├── для каждого Scenario:
│     ├── executor.execute_scenario() → ScenarioTrace
│     ├── judge.evaluate() → list[RubricEvaluation]
│     ├── metrics.compute_process_metrics() → ProcessMetrics
│     └── собираем ScenarioOutcome
│
├── metrics.aggregate() → AggregateMetrics (RQS, PQS, RS, SS, ES)
├── gate.decide() → GateDecision
├── reporter.generate_html() → reports/runs/<run_id>/index.html
└── сохраняем RunReport в reports/runs/<run_id>/report.json

## Интерфейсы модулей

### loader.py
```python
def load_scenario(path: Path) -> Scenario: ...
def load_basket(basket_dir: Path) -> list[Scenario]: ...
```

### executor.py
```python
def execute_scenario(scenario: Scenario) -> ScenarioTrace: ...
```
- Маршрутизирует по `scenario.system` ("finance_agent" или "travel_agent")
- Возвращает полную трассу с финальным ответом, токенами, latency, стоимостью

### judge.py
```python
class LLMJudge:
    def __init__(self, model: str | None = None): ...
    def evaluate_rubric(
        self, rubric: str, scenario: Scenario, trace: ScenarioTrace
    ) -> RubricEvaluation: ...
    def evaluate_all(
        self, scenario: Scenario, trace: ScenarioTrace
    ) -> list[RubricEvaluation]: ...
```
- Поддерживает 4 базовые рубрики: factual_correctness, intent_coverage, groundedness, tone_compliance
- Для multi-turn сценариев использует Agent-as-a-Judge (см. spec 04)

### metrics.py
```python
def compute_process_metrics(scenario: Scenario, trace: ScenarioTrace) -> ProcessMetrics: ...
def compute_safety_metrics(scenario: Scenario, trace: ScenarioTrace) -> SafetyMetrics: ...
def aggregate(outcomes: list[ScenarioOutcome]) -> AggregateMetrics: ...
```
- Process-метрики считаются программно (по ожиданиям из сценария)
- Aggregate возвращает RQS, PQS, RS, SS, ES

### gate.py
```python
def decide(report: RunReport) -> GateDecision: ...
```
- Возвращает один из: "allow" / "conditional_allow" / "block"
- Основание решения: пороги из spec 03 + правила нулевой терпимости

### reporter.py
```python
def generate_html_report(report: RunReport, output_dir: Path) -> Path: ...
def save_json_report(report: RunReport, output_dir: Path) -> Path: ...
```

### orchestrator.py
```python
def run_basket(
    basket_dir: Path,
    output_dir: Path,
    judge_model: str | None = None,
    parallel: int = 4,
) -> RunReport: ...
```
- Главный entrypoint. Связывает все модули.
- `parallel` — количество одновременных прогонов сценариев (через `asyncio.gather`)

### cli.py
```python
@click.group()
def main(): ...

@main.command()
@click.option("--basket", required=True, type=click.Path(exists=True))
@click.option("--output", default="reports/runs")
def run(basket: str, output: str): ...
```

## Зависимости между модулями
cli → orchestrator → {loader, executor, judge, metrics, gate, reporter}
loader, executor, judge, metrics, gate, reporter → models

Никаких циклических зависимостей.

## Acceptance criteria

- [ ] Все 9 модулей в `tester/` созданы и импортируются без ошибок
- [ ] `from tester.models import Scenario, ScenarioTrace, RunReport` работает
- [ ] `pytest tests/test_imports.py` проходит (тест на импорты)
- [ ] `tester --help` показывает команду `run`
- [ ] `ruff check tester/` проходит чисто
- [ ] `mypy tester/` проходит чисто (с разумными `# type: ignore` для сторонних либ)

## Не-цели

- Эта спецификация НЕ включает реализацию модулей — только их интерфейсы и расположение
- Конкретная реализация каждого модуля будет в задачах T002, T003, ...
- Эволюционный генератор (`scenario-generator`) НЕ часть `tester/` — он живёт в `.claude/agents/` (см. spec 10)

## Порядок реализации модулей

Когда дойдём до конкретных задач, порядок такой (соответствует зависимостям):

1. `models.py` (T002)
2. `loader.py` (T003)
3. `executor.py` (T004)
4. `judge.py` (T005)
5. `metrics.py` (T006)
6. `gate.py` (T007)
7. `reporter.py` (T008)
8. `orchestrator.py` (T009)
9. `cli.py` (T010)