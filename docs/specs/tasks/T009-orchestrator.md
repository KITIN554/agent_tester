# T009 — Оркестратор пайплайна прогона

## Цель
Реализовать `tester/orchestrator.py` — главный entry point, который связывает loader, executor, judge, metrics, gate, reporter в единый пайплайн.

## Связанные спецификации
- 01-tester-architecture.md — раздел «orchestrator.py»

## Что нужно сделать

1. Создать `tester/orchestrator.py`:
```python
   def run_basket(
       basket_dir: Path,
       output_dir: Path,
       judge_model: str | None = None,
       parallel: int = 4,
       max_scenarios: int | None = None,
       console: Console | None = None,
   ) -> RunReport
```
2. Логика:
   1. `loader.load_basket(basket_dir)` → список Scenario
   2. Если `max_scenarios` — обрезать
   3. Прогон сценариев параллельно через `asyncio.gather` (по N штук одновременно)
   4. Для каждого Scenario:
      - `executor.execute_scenario(scenario)` → ScenarioTrace
      - `judge.evaluate_all(scenario, trace)` → list[RubricEvaluation]
      - `metrics.compute_process_metrics(scenario, trace)` → ProcessMetrics
      - `metrics.compute_safety_metrics(scenario, trace)` → SafetyMetrics
      - Собрать ScenarioOutcome с `passed = (no failed critical rubrics) AND (process metrics within thresholds)`
   5. `metrics.aggregate(outcomes)` → AggregateMetrics
   6. `gate.load_baseline(output_dir, basket_name)` → baseline_report
   7. `gate.decide(report, baseline_report)` → GateResult
   8. Собрать `RunReport`
   9. `reporter.save_run_artifacts(report, output_dir)` → путь к index.html
   10. Вернуть RunReport
3. Прогресс-бар через `rich.progress` (если передан console)
4. `tests/test_orchestrator.py` с моками:
   - run_basket на мини-корзине из 2 сценариев работает end-to-end
   - При max_scenarios=1 прогоняется только один
   - RunReport собирается корректно

## Acceptance criteria

- [ ] `tester/orchestrator.py` реализует run_basket
- [ ] Параллельный прогон через asyncio работает
- [ ] Прогресс-бар отображается
- [ ] `pytest tests/test_orchestrator.py` зелёный
- [ ] `ruff check tester/orchestrator.py` зелёный
- [ ] Закоммичено: `feat: add orchestrator pipeline`

## Зависимости

T003, T004, T005, T006, T007, T008.
