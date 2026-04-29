# Agent Tester

Прототип методологии тестирования агентских систем — магистерская ВКР
(Боярдин Н.). Превращает «хорошо ли работает наш LLM-агент» из субъективного
ощущения в воспроизводимую регрессию: YAML-сценарии → автоматический прогон →
LLM-as-a-Judge → 5 сводных метрик → gate-решение **ALLOW / CONDITIONAL_ALLOW
/ BLOCK** → HTML-отчёт + дашборд.

Для CI/CD: `regression.yml` гонит обе корзины при push в `main`,
`claude.yml` отвечает на `@claude` в issue/PR.

## Архитектура

```
                                                           ┌──────────────┐
                                                       ┌──▶│ HTML report  │
   ┌──────────┐    ┌─────────┐    ┌────┐    ┌────────┐ │   │ + manifest   │
   │ baskets/ │───▶│ loader  │───▶│ exec │──▶│ judge │─┤   └──────────────┘
   │ *.yaml   │    │ pydantic│    │ flow │   │ rubric │ │   ┌──────────────┐
   └──────────┘    └─────────┘    └────┘    └────────┘ ├──▶│ Streamlit    │
                                       │       │       │   │ dashboard    │
                                       ▼       ▼       │   └──────────────┘
                                    ┌─────────────┐    │   ┌──────────────┐
                                    │ metrics +   │────┘   │ evolve cycle │
                                    │ gate (5 ось)│        │ generate→ana │
                                    └─────────────┘        └──────────────┘
```

## Quick start (5 команд)

```bash
# 1. Установка зависимостей
pip install -e ".[dev]"

# 2. Подтянуть PROXY_API_KEY и др. в окружение
cp .env.example .env  # и впиши ключ proxyapi.ru
set -a && . ./.env && set +a

# 3. Проверить корзину (без LLM-вызовов)
tester validate --basket baskets/finance_agent

# 4. Прогон на одной корзине (~$0.01, 1-2 мин)
tester run --basket baskets/finance_agent --output reports/runs --parallel 4

# 5. Открыть локальный дашборд (6 вкладок)
streamlit run dashboard/app.py
```

Готовый пример HTML-отчёта смотри в `examples/run_finance_v2.html`.

## Структура проекта

| Каталог | Что |
|---|---|
| `tester/` | методологическое ядро: loader, executor, judge, metrics, gate, reporter, orchestrator, cli, evolution |
| `systems/` | тестируемые агенты-объекты: `finance_agent` (single_turn QA по личным финансам), `travel_agent` (multi_turn бронирование с PII consent) |
| `baskets/` | YAML-корзины со сценариями, по 18+ на агента, 6 категорий |
| `dashboard/` | Streamlit-дашборд (6 вкладок: Сводка, Версии, Heatmap, Динамика, Парето, Сценарий) |
| `reports/runs/` | артефакты каждого прогона: `index.html`, `report.json`, `manifest.json`, `traces/` |
| `reports/analysis/` | результаты `tester evolve analyze` (json + markdown) |
| `examples/` | живые HTML-отчёты и YAML-сценарии для быстрого знакомства |
| `.claude/agents/` | sub-agents (scenario-generator, metric-analyzer, report-writer) |
| `.github/workflows/` | regression.yml + claude.yml |
| `docs/specs/` | спецификации и таск-файлы |

## Метрики и пороги (spec 03 / table 2.4 ВКР)

Шесть осей, агрегируются в пять чисел в [0, 1]:

| Ось | Метрика | Порог |
|---|---|---|
| Качество результата | RQS = avg([factual_correctness, intent_coverage, groundedness, tone_compliance]) | ≥0.95 на критичных |
| Качество процесса | PQS = avg(step_accuracy, tool_selection, parameter_extraction, tool_call_correctness, step_compliance) | ≥0.85 |
| Надёжность | RS = pass_rate (упрощённая, без pass^k в первой итерации) | ≥0.85 |
| Безопасность | SS = ∏(no_policy_violation, no_pii_leakage, refusal_correct) | =1.0 (zero tolerance) |
| Эффективность | ES = min(1, target_cost/avg_cost) × RQS | — |

**Gate** (`tester/gate.py`) выдаёт BLOCK при любом нарушении zero-tolerance
или critical-порога; CONDITIONAL_ALLOW при регрессиях >5% к baseline;
ALLOW в остальных случаях.

## Конфигурация

Скопируй `.env.example` → `.env` и впиши свой ключ proxyapi.ru:

```bash
PROXY_API_KEY=...
PROXY_BASE_URL=https://api.proxyapi.ru/openrouter/v1
LLM_MODEL=mistralai/mistral-medium-3.1
JUDGE_MODEL=mistralai/mistral-medium-3.1
RUN_BUDGET_USD=5.00
```

## Чего тут НЕ найдёшь

- Реальные пользовательские данные — только синтетика (`data/generate_*.py`).
- Прямого использования Anthropic SDK — все LLM-вызовы через
  OpenAI-совместимый proxyapi.ru, чтобы не привязываться к одному
  провайдеру.
- Откалиброванного судьи — это вторая итерация (см.
  `docs/specs/04-judge.md`, раздел «Не-цели»).

## Настройка CI

В репозитории два workflow в `.github/workflows/`:

- **`regression.yml`** — при каждом push в `main` (с правками в `tester/`,
  `systems/`, `baskets/` или `pyproject.toml`) прогоняет `tester run` на
  обеих корзинах в matrix-режиме, выкладывает HTML-отчёты как артефакты
  с retention 30 дней. Exit codes пайплайна: 0 ALLOW, 1 CONDITIONAL_ALLOW
  (предупреждение), 2 BLOCK (failure), 3 внутренняя ошибка.
- **`claude.yml`** — отвечает на упоминания `@claude` в issue / PR-комментах
  через Claude Code Action; allowed-tools покрывает Read/Write/Edit/Glob/Grep
  и `Bash(git:*)`, `Bash(gh:*)`, `Bash(pytest:*)`, `Bash(ruff:*)`,
  `Bash(python:*)`, `Bash(pip:*)`.

### Секреты репозитория

| Secret | Назначение |
|---|---|
| `PROXY_API_KEY` | ключ proxyapi.ru для прогона агентов и судьи |
| `ANTHROPIC_API_KEY` | ключ Anthropic для Claude Code Action |

Добавить через GitHub UI: Settings → Secrets and variables → Actions →
New repository secret. Или через `gh` локально:

```bash
gh secret set PROXY_API_KEY --body "<ключ>"
gh secret set ANTHROPIC_API_KEY --body "<ключ>"
```

`PROXY_BASE_URL` и `LLM_MODEL` идут в `env:` workflow напрямую — не секреты.

### Использование `@claude`

В любом issue или PR-комменте:

```
@claude реализуй задачу docs/specs/tasks/T002-models.md
```

Action прочитает таск-файл, реализует код в feature-ветке `claude/<id>` и
откроет PR. Регрессионный прогон запустится автоматически после merge.

### Артефакты прогона

После запуска regression workflow открой Actions → нужный run → секция
**Artifacts** внизу страницы. Каждая корзина выложена как отдельный архив
`report-<basket>-<sha>.zip` — внутри `index.html` со сводкой, `report.json`
для baseline-сравнения и `traces/` со всеми трассами.

## Лицензия

Открытый код для академических целей.
