# T018 — Усиление scenario-generator (few-shot + system-aware правила)

## Приоритет: КРИТИЧНО (#3, ~30 мин)

## Цель
Доработать `.claude/agents/scenario-generator.md` и `tester/evolution.py`
так, чтобы LLM выдавал валидные сценарии стабильно (в T015 один из двух
кандидатов отбракован валидатором, в T014 — оба).

## Что нужно сделать

1. Дополнить `.claude/agents/scenario-generator.md`:
   - Раздел **Few-shot examples**: 3–4 готовых валидных YAML из текущей
     корзины (single_turn finance + multi_turn travel + negative + safety).
     Конкретные строки, не «такого формата».
   - Явное правило: «`numeric_response` принимает РОВНО одно из:
     `required`, `optional`, `forbidden`. Других значений нет».
   - Правило архитектуры (уже частично в `_SYSTEM_TYPE_CONSTRAINT`):
     «finance_agent → ТОЛЬКО single_turn; travel_agent → ТОЛЬКО multi_turn».
   - Правило для negative: `refusal_expected: true` И `forbidden_tool_calls`
     непустой.
2. В `tester/evolution.py::_build_generator_prompt`:
   - Подгружать тело sub-agent'а целиком как system-prompt (уже делается).
   - Дополнительно — вшивать одну few-shot пару (input → expected scenario)
     прямо в user-сообщение.
3. Опционально: сохранять «отбракованные кандидаты» в
   `reports/evolution/<timestamp>/rejected.json` для диагностики
   качества генератора.

## Acceptance criteria

- [ ] `.claude/agents/scenario-generator.md` содержит few-shot примеры
  и явные правила (numeric_response, type per system, negative).
- [ ] `_build_generator_prompt` встраивает в user-сообщение хотя бы один
  few-shot пример (можно из существующих SCN-FIN-001 и SCN-TRV-001).
- [ ] Существующие тесты `tests/test_evolution.py` зелёные.
- [ ] Новый тест: prompt содержит хотя бы один few-shot пример.
- [ ] Закоммичено: `feat(evolve): few-shot examples + tighter rules in scenario-generator`

## Зависимости
T015 (понимание реальных провалов генератора).
