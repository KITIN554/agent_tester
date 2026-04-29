# T016 — Усиление промптов finance_agent и travel_agent (v1)

## Приоритет: КРИТИЧНО (#1, ~1 час)

## Цель
Закрыть конкретные провалы из E2E-прогона: для finance_agent — отказы на
out-of-scope запросах (`refusal_accuracy 0.5` при пороге 0.98); для
travel_agent — `intent_coverage 0.188`, `refusal_accuracy 0.0`, `SS 0.000`.

## Источники провалов

Из `reports/runs/20260428-193646-finance_agent/report.json` и
`reports/runs/20260428-193701-travel_agent/report.json`.

### finance_agent
- `policy_violation`: 1/17 — где-то агент дёрнул запретный инструмент.
- `refusal_accuracy: 0.500` — на 2 negative-сценариях из 2 половина провалов.
- `intent_coverage: 0.647` — почти треть ответов не покрывает запрос.
- `step_accuracy: 0.769`, `parameter_extraction_accuracy: 0.756` —
  агент путает параметры `period`/`category`/`aggregation`.

### travel_agent
- `SS: 0.000` — был хотя бы один PII leakage / policy violation.
- `intent_coverage: 0.188` — 13/16 ответов не довели диалог до намерения.
- `refusal_accuracy: 0.000` — на обоих negative-сценариях агент не отказал.
- `scenario_completion: 0.500` — половина диалогов не достигли terminal_state.

## Что нужно сделать

1. **Прочитать `systems/finance_agent/prompts.py` и `systems/travel_agent/prompts.py`**
   и сравнить с failure-модами выше.
2. **Усилить FinanceAgent prompt:**
   - Явный список «вне компетенции»: погода, перевод денег, чужие данные.
   - Шаблон отказа: «Я не могу — я работаю только с твоими личными финансами».
   - Жёсткое правило: «не вызывай query_transactions, если запрос не про
     транзакции пользователя».
   - Чек-лист параметров: как мапить «прошлый месяц» → `previous_month`,
     «март 2026» → `month:2026-03`, «последние 30 дней» → `last_30_days`.
3. **Усилить TravelAgent prompt:**
   - Жёсткая последовательность: search_destinations → calculate_price →
     validate_pii → request_pii_consent → create_booking. Никогда
     create_booking без предшествующего request_pii_consent.
   - Ответы на out-of-scope (погода, рестораны): «Я только бронирую
     путешествия — не могу помочь с …».
   - Если пользователь отказывается давать согласие — переход в
     terminal_state=cancelled, никаких create_booking.
   - При невалидных датах/email — попросить уточнить, не угадывать.
4. **Smoke-проверка локально:**
   `pytest` зелёный (промпты — обычная строка, не ломают unit-тесты).
5. **Не трогать ядро методологии:** `tester/*` остаётся как есть.

## Acceptance criteria

- [ ] `systems/finance_agent/prompts.py` содержит явный список out-of-scope
  тем и шаблон отказа.
- [ ] `systems/travel_agent/prompts.py` фиксирует обязательную последовательность
  consent → booking, отказы на out-of-scope, поведение при отказе от ПДн.
- [ ] `pytest` зелёный (110+ тестов).
- [ ] Закоммичено в main: `feat(prompts): tighten agent prompts to close E2E failures`

## Зависимости
T015 (E2E-результаты для целеуказания).
