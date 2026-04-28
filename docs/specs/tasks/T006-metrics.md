# T006 — Метрики и сводные показатели

## Цель
Реализовать `tester/metrics.py` — расчёт метрик процесса, безопасности и сводных RQS/PQS/RS/SS/ES.

## Связанные спецификации
- 03-metrics.md — полная спецификация метрик с формулами

## Что нужно сделать

1. Создать `tester/metrics.py`:
   - Константа `DEFAULT_THRESHOLDS` (точно как в спек 03)
   - `compute_process_metrics(scenario, trace) -> ProcessMetrics`
   - `compute_safety_metrics(scenario, trace) -> SafetyMetrics`
   - `compute_rqs(outcomes) -> float`
   - `compute_pqs(outcomes) -> float`
   - `compute_rs(outcomes) -> float`
   - `compute_ss(outcomes) -> float`
   - `compute_es(outcomes, rqs, target_cost_per_scenario=0.01) -> float`
   - `aggregate(outcomes) -> AggregateMetrics`
2. Реализация по спецификации, без отклонений от формул главы 2
3. Корректная обработка пустых списков и None-значений
4. `tests/test_metrics.py` с минимум 10 тестами:
   - все рубрики pass → RQS = 1.0
   - все рубрики fail → RQS = 0.0
   - смесь partial/pass → разумное среднее
   - PQS считается на синтетических ScenarioOutcome
   - SS обнуляется при единичном policy_violation
   - SS обнуляется при единичном pii_leakage
   - ES уменьшается при росте cost
   - aggregate на пустом списке возвращает все нули
   - aggregate на нормальном списке возвращает корректный AggregateMetrics
   - compute_process_metrics корректно работает на сценарии без required_tool_calls (возвращает None для соотв. полей)

## Acceptance criteria

- [ ] `tester/metrics.py` реализует все функции
- [ ] DEFAULT_THRESHOLDS соответствует таблице 2.4 из главы 2
- [ ] `pytest tests/test_metrics.py` зелёный, минимум 10 тестов
- [ ] `ruff check tester/metrics.py` зелёный
- [ ] `mypy tester/metrics.py` зелёный
- [ ] Закоммичено в main: `feat: add metrics computation (RQS/PQS/RS/SS/ES)`

## Зависимости

T002.
