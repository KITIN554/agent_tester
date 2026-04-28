# T005 — Судья (LLM-as-a-Judge)

## Цель
Реализовать `tester/judge.py` — оценщик трасс по 4 базовым рубрикам.

## Связанные спецификации
- 04-judge.md — полная спецификация судьи
- 02-scenario-format.md — какие рубрики могут быть в сценарии

## Что нужно сделать

1. Создать `tester/judge.py` с:
   - Константа `RUBRIC_DEFINITIONS` (4 рубрики из спек)
   - Константа `JUDGE_SYSTEM_PROMPT` (текст из спек)
   - Класс `LLMJudge`:
     - `__init__(api_key, base_url, model)` — все опциональные, по умолчанию из env
     - `evaluate_rubric(rubric, scenario, trace) -> RubricEvaluation`
     - `evaluate_all(scenario, trace) -> list[RubricEvaluation]`
     - `evaluate_multi_turn(scenario, trace) -> list[RubricEvaluation]` — для multi_turn передаёт полную трассу
2. Все LLM-вызовы:
   - JSON-mode (`response_format={"type": "json_object"}`)
   - `temperature=0.0`
   - `max_tokens=300`
   - Обёрнуты в `@retry(stop_after_attempt(3), wait_exponential(min=1, max=10))`
3. При невалидном JSON в ответе или после 3 retry — вернуть `RubricEvaluation(verdict=NA, rationale="parse error" / "API error")` вместо исключения
4. Шаблоны user-сообщений:
   - Для каждой рубрики — динамическое формирование с учётом её `inputs` (см. спек 04)
5. `tests/test_judge.py` с моками:
   - Тест на каждую рубрику возвращает корректный RubricEvaluation
   - evaluate_all вызывает evaluate_rubric для каждой рубрики из scenario.rubrics
   - Невалидный JSON-ответ → verdict=NA
   - 3 неудачных retry → verdict=NA, не выкидывает исключение
   - tone_compliance принимает score=4.5 и сохраняет

## Acceptance criteria

- [ ] `tester/judge.py` реализует все три метода
- [ ] Все LLM-вызовы используют JSON-mode и temperature=0.0
- [ ] Все LLM-вызовы обёрнуты в @retry
- [ ] При ошибках — gracefully возвращает NA, не падает
- [ ] `pytest tests/test_judge.py` зелёный, минимум 6 тестов
- [ ] В коде есть TODO-комментарий: «известное ограничение: судья и агент могут быть на одной модели — self-preference bias, в первой итерации не контролируется»
- [ ] `ruff check tester/judge.py` зелёный
- [ ] Закоммичено в main: `feat: add LLM-as-a-Judge with 4 base rubrics`

## Зависимости

T002.
