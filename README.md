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

## Лицензия

Открытый код для академических целей.
