# Agent Tester

Прототип методологии тестирования агентских систем (магистерская ВКР).

## Что внутри

- `tester/` — агент-тестировщик (orchestrator, executor, judge, metrics, reporter)
- `systems/` — два экспериментальных агента-объекта тестирования:
  - `finance_agent/` — QA-агент по личным финансам (одиночные задачи)
  - `travel_agent/` — агент бронирования путешествия (многошаговые задачи)
- `baskets/` — тестовые корзины (YAML-сценарии)
- `reports/` — HTML-отчёты прогонов
- `dashboard/` — Streamlit-дашборд для локальной визуализации метрик
- `.claude/agents/` — sub-agents для Claude Code (scenario-generator, judge, reporter)
- `.github/workflows/` — GitHub Actions для автоматической регрессии

## Запуск

```bash
# Установка
pip install -e .

# Запустить регрессию на одной корзине
tester run --basket baskets/finance_agent

# Открыть локальный дашборд
streamlit run dashboard/app.py
```

## Конфигурация

Скопируй `.env.example` → `.env` и впиши свой ключ proxyapi.ru.

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
