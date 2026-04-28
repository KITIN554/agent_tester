# T002 — Pydantic-модели tester/models.py

## Цель
Реализовать все модели данных, которые будут использоваться в остальных модулях `tester/`. Это фундамент следующих тасков.

## Связанные спецификации
- 02-scenario-format.md — формат Scenario, ScenarioInput, ScenarioExpectations
- 03-metrics.md — модели ProcessMetrics, SafetyMetrics, AggregateMetrics
- 04-judge.md — RubricEvaluation, RubricVerdict
- 05-gate-logic.md — GateDecision

## Что нужно сделать

1. Создать `tester/models.py` со всеми Pydantic-моделями:
   - **Сценарий**: ScenarioCategory, ScenarioType, ConversationTurn, ScenarioInput, ToolCallExpectation, ScenarioExpectations, Scenario
   - **Трасса**: ScenarioTrace
   - **Оценка**: RubricVerdict, RubricEvaluation, ProcessMetrics, SafetyMetrics, ScenarioOutcome
   - **Корзина**: AggregateMetrics, GateDecision, RunReport
2. Все модели должны проходить `model_validate` на корректных данных
3. Невалидные данные должны выкидывать `ValidationError`
4. Создать `tests/test_models.py` с минимум 8 тестами:
   - Валидный single_turn Scenario парсится
   - Валидный multi_turn Scenario парсится
   - Scenario с невалидным ID (не подходит регэкспу `^SCN-(FIN|TRV)-\d{3}$`) падает
   - Scenario где system не соответствует префиксу ID падает
   - single_turn без user_message падает
   - multi_turn без conversation_turns падает
   - RunReport собирается из ScenarioOutcome корректно
   - AggregateMetrics принимает только значения от 0 до 1

## Acceptance criteria

- [ ] `tester/models.py` создан со всеми моделями из спек 02-05
- [ ] `from tester.models import *` импортирует все классы
- [ ] `pytest tests/test_models.py` зелёный, минимум 8 тестов
- [ ] Валидаторы (например, регэксп ID, проверка соответствия system/ID) реализованы как `field_validator` или `model_validator` Pydantic v2
- [ ] `ruff check tester/models.py` зелёный
- [ ] `mypy tester/models.py` без ошибок
- [ ] Закоммичено в main с conventional commit `feat: add tester/models.py with Pydantic data models`

## Зависимости

T001 (тесты должны работать).
