# T007 — Gate-логика

## Цель
Реализовать `tester/gate.py` — правила приёмки релиза.

## Связанные спецификации
- 05-gate-logic.md — полная спецификация

## Что нужно сделать

1. Создать `tester/gate.py`:
   - dataclass `GateResult` (decision, reasons)
   - функция `decide(report, baseline_report=None, regression_threshold=0.05) -> GateResult`
   - приватные функции `_check_zero_tolerance`, `_check_critical_thresholds`, `_check_regressions`
   - функция `load_baseline(reports_dir, basket_name) -> RunReport | None`
2. Логика принятия решения:
   - Любое нарушение zero_tolerance → BLOCK
   - Иначе любое нарушение critical thresholds → BLOCK
   - Иначе регрессии (vs baseline > 5%) или падение сводных показателей → CONDITIONAL_ALLOW
   - Иначе → ALLOW
3. reasons на русском, читаемые
4. `tests/test_gate.py` с минимум 7 тестами:
   - PII leakage → BLOCK
   - Policy violation → BLOCK
   - step_accuracy < 0.85 → BLOCK
   - Чистый прогон без baseline → ALLOW
   - Чистый прогон с baseline и стабильными метриками → ALLOW
   - tone_compliance падение > 5% → CONDITIONAL_ALLOW
   - load_baseline корректно находит последний non-block прогон

## Acceptance criteria

- [ ] `tester/gate.py` реализует decide и load_baseline
- [ ] `pytest tests/test_gate.py` зелёный, минимум 7 тестов
- [ ] reasons читаемы на русском
- [ ] `ruff check tester/gate.py` зелёный
- [ ] Закоммичено: `feat: add release gate logic with 4 conditions`

## Зависимости

T002, T006.
