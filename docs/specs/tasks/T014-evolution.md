# T014 — Эволюционный цикл (генератор сценариев и анализатор)

## Цель
Реализовать `tester/evolution.py` и расширить CLI командами `tester evolve generate / analyze / cycle`. Это центральный механизм самомодификации, описанный в главе 3 ВКР.

## Связанные спецификации
- 10-evolution-loop.md — полная спецификация
- 08-cli.md — формат CLI-команд

## Что нужно сделать

1. Создать `tester/evolution.py`:
   - `invoke_scenario_generator(system, target_count, categories) -> list[Scenario]`
   - `invoke_metric_analyzer(run_id) -> dict` (структура анализа)
   - `run_evolution_cycle(system, rounds=1) -> list[dict]` (история циклов)

2. Реализация:
   - LLM-вызовы через тот же `OpenAI(base_url=PROXY_BASE_URL)` (для единообразия)
   - Загружать промпты sub-agents из `.claude/agents/scenario-generator.md` и `.claude/agents/metric-analyzer.md` (парсить frontmatter, использовать тело как system prompt)
   - Контекст для генератора: код тестируемой системы (`tools.py`, `prompts.py`, `agent.py`) + список существующих ID
   - Парсить ответ как JSON-список словарей, валидировать через `Scenario.model_validate`
   - Сохранять каждый сценарий как отдельный YAML с правильно подобранным следующим ID

3. Расширить `tester/cli.py`:
   - Группа команд `evolve`:
     - `tester evolve generate --system NAME --target-count N [--categories LIST] [--seed-coverage]`
     - `tester evolve analyze --basket NAME [--run-id ID]`
     - `tester evolve cycle --system NAME [--rounds N]`

4. Логирование lead time в каждом прогоне:
   - В `RunReport` добавить опциональное поле `lead_time_metrics: dict | None` с тайминга:
     - `regression_run_seconds`
   - Если запущен через cycle — добавлять `scenario_generation_seconds` и `analysis_seconds`

5. `tests/test_evolution.py` (с моками Anthropic API / OpenAI):
   - `invoke_scenario_generator` возвращает список валидных Scenario
   - `invoke_scenario_generator` корректно нумерует ID (берёт следующий после самого большого существующего)
   - `invoke_metric_analyzer` возвращает структурированный словарь
   - `run_evolution_cycle` логирует lead_time_metrics
   - При ошибке LLM (3 retry) — функция возвращает пустой список, не падает

## Acceptance criteria

- [ ] `tester/evolution.py` реализует все три функции
- [ ] CLI-команды `evolve generate / analyze / cycle` работают
- [ ] `tester evolve generate --system finance_agent --target-count 3` создаёт 3 валидных YAML
- [ ] `tester validate --basket baskets/finance_agent` после этого зелёный
- [ ] Сгенерированные сценарии не дублируют существующие (проверка по описанию через эмбеддинги или хотя бы по подстрокам)
- [ ] `tester evolve cycle --system finance_agent --rounds 1` выполняет полный цикл и логирует lead time
- [ ] `pytest tests/test_evolution.py` зелёный (с моками)
- [ ] `ruff check tester/evolution.py` зелёный
- [ ] Эволюционный sub-agent НЕ модифицирует ядро (`tester/metrics.py`, `tester/gate.py`, `tester/judge.py`, `tester/models.py`)
- [ ] Закоммичено: `feat: add evolutionary cycle (scenario-generator + metric-analyzer)`

## Зависимости

T010, T011.

## Подсказка по reuse sub-agents

Sub-agents `.claude/agents/scenario-generator.md` и `.claude/agents/metric-analyzer.md` уже определены в этапе 3 настройки проекта. Их frontmatter и тело используются как промпт для LLM-вызова через OpenAI SDK (через прокси, как везде в проекте). НЕ запускай отдельный Claude Code CLI subprocess — используй прямой LLM-вызов.

## Замечания про lead time argument

В главе 3 будет сравнение:
- Ручной цикл: добавить сценарий → прогнать → проанализировать ≈ часы
- Автоматизированный: команда `evolve cycle --rounds 1` ≈ минуты

Для этого `lead_time_metrics` критичен. После реализации сделай хотя бы один полный прогон `tester evolve cycle --system finance_agent --rounds 1` и убедись, что в `report.json` есть тайминги.
