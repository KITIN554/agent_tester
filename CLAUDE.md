# Agent Tester — методология тестирования агентских систем

Это прототип методологии для магистерской ВКР по теме «Разработка методологии тестирования и оценивания работы агентских систем».

## Архитектура проектаagent-tester/
├── tester/          # Агент-тестировщик
│   ├── orchestrator.py   # Главный оркестратор прогонов
│   ├── executor.py       # Запуск сценариев на тестируемых системах
│   ├── judge.py          # LLM-as-a-Judge / Agent-as-a-Judge
│   ├── metrics.py        # Расчёт RQS/PQS/RS/SS/ES
│   ├── reporter.py       # Генерация HTML-отчётов
│   └── cli.py            # CLI-интерфейс
├── systems/         # Тестируемые агенты
│   ├── finance_agent/    # QA-агент по личным финансам (одиночные задачи)
│   └── travel_agent/     # Агент бронирования (многошаговые задачи)
├── baskets/         # Тестовые корзины (YAML-сценарии)
├── reports/         # HTML-отчёты прогонов
├── dashboard/       # Streamlit-дашборд
└── .claude/agents/  # Sub-agents для Claude Code

## Технологический стек

- **Python**: 3.11+
- **LLM**: DeepSeek через proxyapi.ru (OpenAI-совместимый API)
- **Конфигурация**: `pydantic` для моделей данных, `pyyaml` для сценариев, `python-dotenv` для секретов
- **Дашборд**: Streamlit + Plotly
- **CLI**: Click + Rich

## Принципы работы с LLM

ВАЖНО: все LLM-вызовы идут через прокси:

```pythonfrom openai import OpenAI
import osclient = OpenAI(
api_key=os.environ["PROXY_API_KEY"],
base_url=os.environ["PROXY_BASE_URL"],  # https://api.proxyapi.ru/deepseek
)response = client.chat.completions.create(
model=os.environ["LLM_MODEL"],  # deepseek-chat
messages=[...],
)

Никогда не используй прямой вызов Anthropic SDK или OpenAI без `base_url` — это потратит чужой бюджет или вернёт 401.

## Методологические концепции (из глав 1-2 ВКР)

### Шесть осей оценки
1. Качество результата → метрики Factual Correctness, Intent Coverage, Groundedness, Tone Compliance
2. Качество процесса → Step Accuracy, Tool Selection Accuracy, Parameter Extraction, Scenario Completion
3. Надёжность → pass^k, медиана, доля провалов
4. Безопасность → Policy Violation Rate, PII Leakage Rate
5. Стоимость → tokens, calls, cost_usd
6. Время → latency p50/p95/p99

### Сводные показатели
- **RQS** (Result Quality Score) — взвешенная сумма метрик результата
- **PQS** (Process Quality Score) — взвешенная сумма метрик процесса
- **RS** (Reliability Score) — pass^k + медиана + стабильность
- **SS** (Safety Score) — произведение долей пройденных метрик безопасности
- **ES** (Efficiency Score) — нормализованная стоимость с поправкой на качество

### Уровни иерархии метрик
шаг → траектория → прогон → корзина

### Категории сценариев
функциональные, граничные, негативные, безопасности, стресс, робастности

## Формат тест-сценария

Сценарий — YAML-файл в `baskets/<system_name>/<scenario_id>.yaml`:

```yamlid: SCN-FIN-001
category: functional
type: single_turn   # или multi_turn
description: "Сумма расходов за прошлый месяц"
input:
user_message: "Сколько я потратил в прошлом месяце?"
available_tools: ["query_transactions"]
limits:
max_steps: 5
max_latency_s: 10
max_cost_usd: 0.10
expectations:
required_tool_calls:
- name: "query_transactions"
parameters:
period: "previous_month"
entities:
period: "previous_month"
numeric_response: required
rubrics:

factual_correctness
intent_coverage
groundedness
tone_compliance
thresholds:
factual_correctness: correct
groundedness: pass
intent_coverage: full


## Стиль кода

- Python 3.11+ с современными type hints (`list[str]`, `dict[str, int]`, `X | None`)
- Pydantic-модели для всех структур данных (сценарии, трассы, оценки, метрики)
- Async/await для LLM-вызовов (через `asyncio.gather` для параллельных прогонов)
- Decorator `@retry` из `tenacity` на каждый LLM-вызов (3 попытки с экспоненциальной задержкой)
- Логирование через `rich.console` — никаких `print()`
- Type hints обязательны; mypy и ruff пройдут чисто

## Sub-agents

В `.claude/agents/` лежат специализированные под-агенты:
- `scenario-generator` — генерирует новые тест-сценарии для тестируемых систем
- `metric-analyzer` — разбирает результаты прогона и предлагает действия
- `report-writer` — пишет краткое summary прогона на русском

Используй их через инструмент `Task` (built-in в Claude Code) для делегирования.

## Команды разработки

```bashАктивация окружения
source .venv/bin/activateЛинтинг и проверки
ruff check .
ruff format .
mypy tester/Запуск прогона
tester run --basket baskets/finance_agentДашборд
streamlit run dashboard/app.pyТесты
pytest

## Git workflow

- Основная ветка: `main` (защищённая)
- Feature-ветки: `feat/<short-name>`, `fix/<short-name>`
- Перед коммитом: ruff format, ruff check, pytest
- Коммиты — Conventional Commits: `feat:`, `fix:`, `chore:`, `docs:`, `test:`
- PR в main только через GitHub Actions проверку

## Безопасность

- Ключ proxyapi лежит **только в `.env` (никогда не коммитится)** и в **GitHub Secrets**
- В коде использовать `os.environ["PROXY_API_KEY"]` — без хардкода
- В логах и отчётах **не печатать ключ**
- Синтетические данные пользователей — **не используй настоящие имена/реальные данные**

## ВАЖНО: чего НЕ делать

- НЕ коммить `.env`
- НЕ хардкодить ключи в коде
- НЕ использовать прямые SDK Anthropic или официальный OpenAI без base_url
- НЕ загружать данные из реальных корпоративных систем — только синтетические
- НЕ выводить полные трассы LLM в отчётах — это раздуёт логи; выводи в виде ссылок на JSON-артефакты
