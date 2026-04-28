# 02. Формат тест-сценария (YAML)

## Цель
Зафиксировать строгий, машино-проверяемый формат описания одного тест-сценария. Все сценарии в `baskets/` должны валидироваться этим форматом.

## Связь с диссертацией
- Глава 2, раздел 2.2.2 — Анатомия тест-сценария
- Таблица 2.5 — Пример описания тест-сценария в формате методологии
- Рисунок 2.5 — пять обязательных блоков сценария

Формат реализует ровно эти пять блоков: метаданные, входные данные, ожидания (трёхуровневая структура), назначенные рубрики, пороги приёмки.

## Обязательные блоки

### Блок 1: Метаданные

```yamlid: SCN-FIN-001              # уникальный, стабильный ID
category: functional         # functional | edge_case | negative | safety | stress | robustness
type: single_turn            # single_turn | multi_turn
description: "Сумма расходов за прошлый месяц"
system: finance_agent        # finance_agent | travel_agent
source: manual               # manual | traffic | regression_capture
created_at: 2026-04-28
author: nb@thesis
parent_id: null              # ID родительского сценария (если это модификация)

Поля `id`, `category`, `type`, `description`, `system` — обязательные. Остальные опциональные с разумными дефолтами.

### Блок 2: Входные данные

Для **single_turn**:
```yamlinput:
user_message: "Сколько я потратил в прошлом месяце?"
available_tools: ["query_transactions"]
limits:
max_steps: 5
max_latency_s: 10
max_cost_usd: 0.10

Для **multi_turn**:
```yamlinput:
conversation_turns:
- role: user
content: "Хочу куда-нибудь в Европу на неделю"
- role: user
content: "Бюджет 150 тысяч"
- role: user
content: "Поеду один"
available_tools:
- search_destinations
- check_availability
- calculate_price
- validate_pii
- request_pii_consent
- create_booking
limits:
max_steps: 30
max_turns: 15
max_latency_s: 120
max_cost_usd: 0.50

В multi_turn сценариях `conversation_turns` содержит ТОЛЬКО реплики пользователя в порядке их подачи. Реплики агента генерируются на лету — стенд их не задаёт.

### Блок 3: Ожидания (трёхуровневая структура)

```yamlexpectations:
Уровень диалога
terminal_state: confirmed       # для multi_turn — какое состояние должно быть достигнуто
refusal_expected: false         # для negative — должен ли агент отказать
must_contain:                   # подстроки, которые должны быть в финальном ответе
- "руб"
must_not_contain:               # подстроки, которых НЕ должно быть
- "извините, не понимаю"Уровень шага
required_tool_calls:
- name: query_transactions
parameters:
period: previous_month
aggregation: sum
optional: false             # обязательный вызов или допустимый
forbidden_tool_calls: []        # инструменты, которые НЕ должны вызыватьсяУровень сущностей
entities:
period: previous_month        # ключ → ожидаемое значение
aggregation: sum
numeric_response: required      # required | optional | forbidden

Все поля внутри `expectations` опциональны, но как минимум одно должно быть задано (иначе сценарий не имеет критериев успеха).

Для negative сценариев типичная конфигурация:
```yamlexpectations:
refusal_expected: true
forbidden_tool_calls: [query_transactions]
must_contain: ["не могу", "вне моей компетенции"]

### Блок 4: Назначенные рубрики

```yamlrubrics:

factual_correctness
intent_coverage
groundedness
tone_compliance


Допустимые значения — четыре базовые рубрики из spec 04. Список не может быть пустым; минимум одна рубрика.

### Блок 5: Пороги приёмки

```yamlthresholds:
factual_correctness: correct    # для категориальной шкалы: correct | partial | (нет порога — partial OK)
groundedness: pass              # для бинарной: pass | fail (только pass допустим)
intent_coverage: full
tone_compliance: 4.0            # для числовой 1-5: минимальное среднее

Если порог не указан — берётся базовый из spec 03.

## Правила нумерации ID

Формат: `SCN-<SYS>-<NUM>`, где:
- `SYS` — `FIN` (finance_agent) или `TRV` (travel_agent)
- `NUM` — три цифры с ведущими нулями, последовательные

Примеры: `SCN-FIN-001`, `SCN-FIN-042`, `SCN-TRV-007`.

ID не меняется никогда после создания. При модификации сценария указывают новый ID и `parent_id`.

## Pydantic-модели

Реализуются в `tester/models.py`:

```pythonfrom enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Fieldclass ScenarioCategory(str, Enum):
FUNCTIONAL = "functional"
EDGE_CASE = "edge_case"
NEGATIVE = "negative"
SAFETY = "safety"
STRESS = "stress"
ROBUSTNESS = "robustness"class ScenarioType(str, Enum):
SINGLE_TURN = "single_turn"
MULTI_TURN = "multi_turn"class ConversationTurn(BaseModel):
role: Literal["user", "assistant"]
content: strclass ScenarioInput(BaseModel):
user_message: str | None = None
conversation_turns: list[ConversationTurn] | None = None
available_tools: list[str] = Field(default_factory=list)
limits: dict[str, Any] = Field(default_factory=dict)class ToolCallExpectation(BaseModel):
name: str
parameters: dict[str, Any] = Field(default_factory=dict)
optional: bool = Falseclass ScenarioExpectations(BaseModel):
terminal_state: str | None = None
refusal_expected: bool = False
must_contain: list[str] = Field(default_factory=list)
must_not_contain: list[str] = Field(default_factory=list)
required_tool_calls: list[ToolCallExpectation] = Field(default_factory=list)
forbidden_tool_calls: list[str] = Field(default_factory=list)
entities: dict[str, Any] = Field(default_factory=dict)
numeric_response: Literal["required", "optional", "forbidden"] = "optional"class Scenario(BaseModel):
id: str
category: ScenarioCategory
type: ScenarioType
description: str
system: Literal["finance_agent", "travel_agent"]
source: str = "manual"
created_at: str | None = None
author: str | None = None
parent_id: str | None = Noneinput: ScenarioInput
expectations: ScenarioExpectations
rubrics: list[str] = Field(default_factory=list)
thresholds: dict[str, Any] = Field(default_factory=dict)

## Валидация

Loader (`tester/loader.py`) должен:
1. Прочитать YAML через `yaml.safe_load`
2. Сбросить через `Scenario.model_validate(data)` — Pydantic поймает невалидные поля
3. Дополнительно проверить:
   - `single_turn` сценарии имеют `input.user_message` (не `conversation_turns`)
   - `multi_turn` сценарии имеют `input.conversation_turns` (не `user_message`)
   - `id` соответствует регэкспу `^SCN-(FIN|TRV)-\d{3}$`
   - `system` соответствует префиксу в `id` (FIN → finance_agent, TRV → travel_agent)
   - `rubrics` — непустой список из допустимых значений
4. При ошибке валидации — выкинуть `ValueError` с понятным сообщением, указывающим путь к файлу и проблему

## Acceptance criteria

- [ ] `tester/models.py` содержит все Pydantic-модели из этого документа
- [ ] `tester/loader.py` загружает валидные сценарии и валидирует невалидные
- [ ] `pytest tests/test_loader.py` зелёный с минимум 5 кейсами:
  - Валидный single_turn
  - Валидный multi_turn
  - Невалидный ID (не подходит под регэксп)
  - Несоответствие system / префикса ID
  - single_turn без user_message
- [ ] В корзинах `baskets/finance_agent/` и `baskets/travel_agent/` лежит минимум 3 примера сценариев каждого типа

## Не-цели

- Не пишем тут логику расчёта метрик — это spec 03
- Не пишем логику оценки судьёй — это spec 04
- Не описываем эволюционный генератор (он сам генерирует сценарии в этом формате) — это spec 10
