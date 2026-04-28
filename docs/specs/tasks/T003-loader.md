# T003 — Загрузчик YAML-сценариев

## Цель
Реализовать `tester/loader.py` для чтения и валидации YAML-сценариев из корзины.

## Связанные спецификации
- 01-tester-architecture.md — раздел «loader.py»
- 02-scenario-format.md — формат YAML и правила валидации

## Что нужно сделать

1. Создать `tester/loader.py` с функциями:
   - `load_scenario(path: Path) -> Scenario`
   - `load_basket(basket_dir: Path) -> list[Scenario]`
2. Дополнительные валидации (поверх Pydantic):
   - ID соответствует регэкспу `^SCN-(FIN|TRV)-\d{3}$`
   - Префикс ID соответствует `system` (FIN → finance_agent, TRV → travel_agent)
   - single_turn имеет `input.user_message`
   - multi_turn имеет `input.conversation_turns`
3. При ошибке валидации выкинуть `ValueError` с понятным сообщением (путь к файлу + проблема)
4. `load_basket` должен:
   - Читать все `*.yaml` в директории по алфавиту
   - При ошибке отдельного файла — печатать предупреждение и продолжать с остальными
   - Возвращать только успешно загруженные
5. Создать первые 3 примера сценариев в `baskets/finance_agent/`:
   - `SCN-FIN-001.yaml` — функциональный, сумма расходов за прошлый месяц
   - `SCN-FIN-002.yaml` — граничный, по составной категории
   - `SCN-FIN-003.yaml` — негативный, запрос вне темы (должен отказать)
6. Создать 2 примера в `baskets/travel_agent/`:
   - `SCN-TRV-001.yaml` — функциональный, успешное бронирование (multi_turn)
   - `SCN-TRV-002.yaml` — безопасности, попытка обойти PII consent
7. `tests/test_loader.py` с минимум 5 тестами:
   - load_scenario на валидном файле
   - load_scenario на невалидном файле (выкидывает ValueError)
   - load_basket на директории с 3 сценариями
   - load_basket пропускает невалидные файлы и продолжает
   - Все 5 примеров (3 finance + 2 travel) валидны

## Acceptance criteria

- [ ] `tester/loader.py` создан, обе функции работают
- [ ] 3 + 2 = 5 валидных YAML-сценариев в `baskets/`
- [ ] `tester validate --basket baskets/finance_agent` (когда CLI будет готов) загрузит 3 сценария
- [ ] `pytest tests/test_loader.py` зелёный, минимум 5 тестов
- [ ] `ruff check tester/loader.py` зелёный
- [ ] `mypy tester/loader.py` зелёный
- [ ] Закоммичено в main: `feat: add YAML scenario loader and example baskets`

## Зависимости

T002 (Pydantic-модели должны существовать).
