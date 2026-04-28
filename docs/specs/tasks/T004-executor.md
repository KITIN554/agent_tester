# T004 — Executor: запуск сценария на тестируемом агенте

## Цель
Реализовать `tester/executor.py` — модуль, который берёт `Scenario` и запускает его на соответствующем агенте (finance или travel), возвращая `ScenarioTrace`.

## Связанные спецификации
- 01-tester-architecture.md — раздел «executor.py»
- 02-scenario-format.md — структура входов сценария

## Что нужно сделать

1. Создать `tester/executor.py` с функцией:
```pythondef execute_scenario(scenario: Scenario) -> ScenarioTrace
2. Маршрутизация:
   - `scenario.system == "finance_agent"` → использовать `FinanceAgent`
   - `scenario.system == "travel_agent"` → использовать `TravelAgent`
   - Иначе — выкинуть ValueError
3. Для finance_agent (single_turn):
   - Проверить, что есть `scenario.input.user_message`
   - Создать `FinanceAgent()`, вызвать `agent.run(message)`
   - Сериализовать трассу шагов в формат, совместимый с `ScenarioTrace.steps`
4. Для travel_agent (multi_turn):
   - Проверить, что есть `scenario.input.conversation_turns`
   - Создать `TravelAgent()`, `start_session()`
   - Прогнать каждую user-реплику по очереди через `agent.send()`
   - Если `agent.is_done()` — остановиться
   - Собрать финальную трассу
5. Обработка ошибок:
   - Если агент бросает исключение — поймать, записать в `ScenarioTrace.error`, вернуть трассу с тем что успело собраться
6. Уважать `scenario.input.limits`:
   - `max_latency_s` — если прогон превысил, прервать (через `asyncio.wait_for` или `signal.alarm`)
   - `max_cost_usd` — после каждого шага проверять накопленную стоимость
7. `tests/test_executor.py` с тестами (через моки FinanceAgent/TravelAgent):
   - execute_scenario на single_turn возвращает корректную ScenarioTrace
   - execute_scenario на multi_turn прогоняет все реплики
   - При ошибке агента возвращается ScenarioTrace с error
   - Превышение max_latency_s обрабатывается корректно
   - Маршрутизация по system работает

## Acceptance criteria

- [ ] `tester/executor.py` реализует execute_scenario
- [ ] `pytest tests/test_executor.py` зелёный, минимум 5 тестов с моками
- [ ] Лимиты из сценария соблюдаются
- [ ] Ошибки агента не падают наружу — конвертируются в ScenarioTrace.error
- [ ] `ruff check tester/executor.py` зелёный
- [ ] `mypy tester/executor.py` зелёный
- [ ] Закоммичено в main: `feat: add scenario executor for finance and travel agents`

## Зависимости

T002, T003.
