# T001 — Базовая инфраструктура тестов

## Цель
Создать каркас тестов и убедиться, что pytest работает в проекте. Это база — без неё все следующие таски не смогут проверить acceptance criteria.

## Связанные спецификации
- 00-overview.md — раздел «Тестирование», «Git-flow»

## Что нужно сделать

1. Создать директорию `tests/` с `__init__.py`
2. Создать `tests/conftest.py` с базовыми фикстурами:
   - `fixture mock_proxy_client` — мок OpenAI-клиента, который возвращает заданные ответы (для тестирования агентов и судьи без реальных LLM-вызовов)
   - `fixture sample_scenario` — пример валидного Scenario для тестов
3. Создать `tests/test_imports.py` — единственный тест, проверяющий что все основные модули импортируются:
```pythondef test_imports():
from systems.finance_agent.agent import FinanceAgent
from systems.travel_agent.agent import TravelAgent
# tester/* пока не существует — будут импортироваться в следующих тасках
4. Запустить `pytest tests/test_imports.py` — должен пройти

## Acceptance criteria

- [ ] Директория `tests/` создана с `__init__.py` и `conftest.py`
- [ ] `pytest` запускается без ошибок (даже если только один тест проходит)
- [ ] `pytest --collect-only` показывает test_imports
- [ ] `ruff check tests/` проходит чисто
- [ ] Изменения закоммичены в main (через ruff + pytest проверку перед коммитом)

## Зависимости

Нет (это первая таска).
