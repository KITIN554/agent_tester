# 10. Эволюционный цикл агента-тестировщика

## Цель
Реализовать механизм, при котором агент-тестировщик **сам читает код тестируемой системы** и **автоматически расширяет корзину** новыми сценариями. Это центральная фишка главы 3 ВКР — переход от «методологии» к «методологии, которая сама себя поддерживает».

## Связь с диссертацией
- Глава 1, раздел 1.2 — четвёртый системный пробел существующих методологий: масштабируемость генерации сценариев. IntellAgent (январь 2025) частично решает это автогенерацией из политик; здесь идём дальше — генерация из исходного кода.
- Глава 2, раздел 2.2.3 — два подхода к формированию корзин (от трафика «снизу вверх», от модели «сверху вниз»); эволюционный цикл — реализация подхода «сверху вниз»
- Глава 3, ключевой подраздел про эволюционирующего агента и lead time argument — это и есть он

## Концепция
    ┌─────────────────────────────────────────────┐
    │  Тестируемая система (systems/finance_agent)│
    │  - tools.py                                 │
    │  - prompts.py                               │
    │  - agent.py                                 │
    └──────────────────┬──────────────────────────┘
                       │ читается
                       ▼
    ┌──────────────────────────────────────────────┐
    │  scenario-generator (sub-agent)              │
    │  1. парсит код, выделяет инструменты         │
    │  2. идентифицирует функциональные области    │
    │  3. идентифицирует политики и edge cases    │
    │  4. генерирует YAML-сценарии 6 категорий    │
    └──────────────────┬───────────────────────────┘
                       │ создаёт
                       ▼
    ┌──────────────────────────────────────────────┐
    │  baskets/<system>/SCN-XXX-NNN.yaml          │
    └──────────────────┬───────────────────────────┘
                       │ запускается
                       ▼
    ┌──────────────────────────────────────────────┐
    │  tester run → reports/runs/...               │
    └──────────────────┬───────────────────────────┘
                       │ анализируется
                       ▼
    ┌──────────────────────────────────────────────┐
    │  metric-analyzer (sub-agent)                 │
    │  выявляет gaps в покрытии                    │
    └──────────────────┬───────────────────────────┘
                       │ инициирует следующий цикл
                       ▼
    Возврат к scenario-generator с новыми приоритетами

## Принцип ядра и периферии

Чтобы избежать «расползания» эволюции, методология делится на:

**Ядро (НЕ модифицируется агентом):**
- 4 базовые рубрики (factual_correctness, intent_coverage, groundedness, tone_compliance)
- Шесть категорий сценариев (functional, edge_case, negative, safety, stress, robustness)
- Метрики и формулы агрегации (RQS, PQS, RS, SS, ES)
- Пороги нулевой терпимости (PII, policy)
- Gate-логика (4 условия)
- Протоколы регрессии и A/B

**Периферия (МОЖЕТ расширяться агентом):**
- YAML-сценарии в корзинах
- Веса некритичных рубрик в RQS (в рамках указанных границ)
- Дополнительные пороги для конкретных метрик
- Производные рубрики (например, domain-specific — но обязательно с сохранением четырёх базовых)

Это ограничение реализуется через:
- Жёсткую валидацию YAML (нельзя ввести unknown rubric)
- Защиту от модификации файлов: `tester/metrics.py`, `tester/gate.py`, `tester/judge.py`, `tester/models.py` — Claude Code не должен их менять без явного приказа

## Команды CLI для эволюционного цикла

Расширение CLI (см. spec 08):

### `tester evolve generate`

Запустить scenario-generator на конкретной системе.

```bash
tester evolve generate \
  --system finance_agent \
  --target-count 20 \
  --categories functional,edge_case,negative \
  [--seed-coverage]
```

Параметры:
- `--system` (обязательный) — для какой системы генерируем
- `--target-count` (по умолчанию 10) — сколько сценариев добавить
- `--categories` (по умолчанию все шесть) — какие категории генерировать
- `--seed-coverage` — режим первого заполнения корзины (минимум один сценарий каждой категории)

Что делает:
1. Читает `systems/<system>/` (tools.py, prompts.py, agent.py)
2. Читает существующие сценарии в `baskets/<system>/` для дедупликации
3. Делегирует sub-agent'у `scenario-generator` через программный вызов Claude Code SDK
4. Sub-agent возвращает структурированный список новых сценариев
5. Каждый сохраняется как `baskets/<system>/SCN-<SYS>-<next_id>.yaml`
6. Печатает сводку: что сгенерировано по категориям

### `tester evolve analyze`

Запустить metric-analyzer на последнем прогоне.

```bash
tester evolve analyze --basket finance_agent
```

Что делает:
1. Загружает последний non-block отчёт прогона
2. Делегирует sub-agent'у `metric-analyzer`
3. Получает список рекомендаций (root cause + suggested fix)
4. Печатает в терминал
5. Опционально: сохраняет в `reports/analysis/<run_id>.md`

### `tester evolve cycle`

Полный эволюционный цикл одной итерацией.

```bash
tester evolve cycle --system finance_agent --rounds 1
```

Что делает (по одной итерации):
1. `evolve generate` — добавить N новых сценариев
2. `tester run` — прогнать новую корзину
3. `evolve analyze` — проанализировать результат
4. По результату анализа — обновить веса/приоритеты для следующего раунда генерации

`--rounds N` — повторить весь цикл N раз. Каждая итерация даёт примерно $0.50-$1.50 расхода на API.

## Реализация: программный запуск sub-agent

В `.claude/agents/scenario-generator.md` уже есть описание sub-agent. Теперь нужен **программный** способ его вызвать (вне VS Code). Используем Anthropic Agent SDK:

```python
# tester/evolution.py
import os
from anthropic import Anthropic
from pathlib import Path

def invoke_scenario_generator(
    system: str,
    target_count: int,
    categories: list[str],
) -> list[dict]:
    """Программный вызов sub-agent для генерации сценариев.

    Использует Anthropic API напрямую (НЕ через Claude Code CLI).
    Загружает промпт из .claude/agents/scenario-generator.md
    и тело системного агента из systems/<system>/.

    Returns:
        Список словарей-сценариев в формате spec 02.
    """
    # 1. Загружаем определение sub-agent
    agent_def = (Path(".claude/agents/scenario-generator.md").read_text())

    # 2. Парсим frontmatter, извлекаем system_prompt
    # 3. Собираем контекст: код тестируемой системы + существующие сценарии
    context = _build_system_context(system)

    # 4. Вызов через Anthropic SDK
    client = Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-6-20250929",
        max_tokens=8000,
        system=agent_def,
        messages=[{
            "role": "user",
            "content": f"""Сгенерируй {target_count} тест-сценариев для системы {system}.
Категории: {', '.join(categories)}.
Контекст: {context}.
Верни JSON-список сценариев в формате spec 02.""",
        }],
    )

    # 5. Парсим ответ, валидируем через Pydantic
    return _parse_and_validate_scenarios(response.content[0].text, system)


def _build_system_context(system: str) -> str:
    """Собирает компактный контекст о системе:
    - Список инструментов и их описания (из tools.py)
    - Системный промпт (из prompts.py)
    - Существующие ID сценариев в корзине (для дедупликации)
    """
    ...
```

**Альтернатива** — использовать Claude Code CLI в headless-режиме:

```bash
claude -p "Реализуй задачу: сгенерируй $TARGET_COUNT сценариев для $SYSTEM" \
  --output-format json
```

Это проще, но требует наличия Claude Code в окружении. Для CLI tester выбираем Anthropic API напрямую — независимость от установки Claude Code.

## Sub-agent: scenario-generator (расширение)

Файл `.claude/agents/scenario-generator.md` уже создан в этапе 3. Дополнительно в нём указываем:

- **Антидубликаты**: перед генерацией сравнивает с существующими ID и описаниями в корзине
- **Соблюдение пропорций категорий**: 60% functional, 15% edge_case, 10% negative, 10% safety, 5% stress/robustness (пропорции из spec 02)
- **Использование инструментов**: при генерации сценария указывает только инструменты из `tools.py` системы
- **Привязка к коду**: каждый сценарий имеет комментарий-обоснование, какой функциональный блок системы он покрывает

## Sub-agent: metric-analyzer (расширение)

Файл `.claude/agents/metric-analyzer.md` тоже уже есть. Расширение:

- **Корреляция между провалами и кодом** — выявляет, какой компонент системы (инструмент, шаг, рубрика) систематически проваливается
- **Рекомендации в форме task-файлов** — может породить новый docs/specs/tasks/ файл с задачей: «Усилить промпт системы X в части обработки даты `previous_month`, потому что 7 из 10 провалов groundedness связаны с этим»

## Lead time measurement

Эволюционный цикл — это и есть мерило lead time. В отчёте каждого прогона логируем:

```json
{
  "lead_time_metrics": {
    "scenario_generation_seconds": 45.2,
    "regression_run_seconds": 312.7,
    "analysis_seconds": 18.3,
    "total_cycle_seconds": 376.2
  }
}
```

В главе 3 это будет ключевой график: «время от изменения промпта системы до получения отчёта» — было N часов аналитика вручную, стало M минут.

## Acceptance criteria

- [ ] `tester/evolution.py` содержит функции:
  - invoke_scenario_generator
  - invoke_metric_analyzer
  - run_evolution_cycle
- [ ] CLI `tester evolve generate --system finance_agent --target-count 5` создаёт 5 новых YAML-файлов в baskets/finance_agent/
- [ ] CLI `tester evolve analyze --basket finance_agent` печатает структурированный анализ последнего прогона
- [ ] CLI `tester evolve cycle --system finance_agent --rounds 1` выполняет полный цикл генерация→прогон→анализ
- [ ] Сгенерированные сценарии валидны (проходят `tester validate`)
- [ ] Сгенерированные сценарии не дублируют существующие (по описанию и сути)
- [ ] Каждый прогон логирует lead_time_metrics в report.json
- [ ] `pytest tests/test_evolution.py` зелёный (с моками Anthropic API):
  - invoke_scenario_generator возвращает список валидных Pydantic-объектов Scenario
  - run_evolution_cycle обрабатывает ошибку sub-agent'а корректно
- [ ] Sub-agent НЕ модифицирует файлы из «ядра» (tester/metrics.py, tester/gate.py, tester/judge.py, tester/models.py) — это проверяется на уровне permissions в .claude/settings.json

## Не-цели

- Self-improvement самого агента-тестировщика (его собственного кода) — это слишком далеко, выйдет за рамки магистерской работы
- Multi-agent дискуссия (несколько generator/judge sub-agents спорят) — концепция IntellAgent, но не реализуем сейчас
- Автоматическая модификация рубрик и весов — только через явный CLI-флаг и review человеком
- Полная автономия (агент сам решает когда генерировать) — пока запуск только по команде
