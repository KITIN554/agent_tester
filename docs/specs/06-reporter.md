# 06. HTML-отчёт прогона

## Цель
Генерировать самодостаточный HTML-отчёт по каждому прогону корзины. Отчёт открывается в браузере без сервера, содержит все метрики, разбор каждого сценария и ссылку на исходные артефакты.

## Связь с диссертацией
- Глава 2, раздел 2.2.5, этап 4 — Первичная агрегация (отчёт двух уровней)
- Этап 7 — Фиксация и архивирование

Каждый прогон создаёт отдельный отчёт в `reports/runs/<run_id>/`. Эталонные точки для сравнения — это успешные прогоны прошлых дней.

## Файловая структура отчётаreports/runs/<run_id>/
├── index.html          # главная страница отчёта
├── report.json         # машиночитаемый RunReport (для baseline и dashboard)
├── manifest.json       # манифест прогона (этап 1 протокола 2.2.5)
├── traces/             # трассы по сценариям
│   ├── SCN-FIN-001.json
│   ├── SCN-FIN-002.json
│   └── ...
└── assets/             # CSS, может быть JS для интерактивности
└── style.css

`run_id` — таймстамп `YYYYMMDD-HHMMSS-<basket>` (например, `20260428-153012-finance_agent`).

## Манифест прогона

`manifest.json` — фиксация всех воспроизводимости-релевантных параметров:

```json{
"run_id": "20260428-153012-finance_agent",
"basket": "finance_agent",
"started_at": "2026-04-28T15:30:12Z",
"finished_at": "2026-04-28T15:35:48Z",
"git_commit": "a1b2c3d",
"git_branch": "main",
"model_agent": "mistralai/mistral-medium-3.1",
"model_judge": "mistralai/mistral-medium-3.1",
"proxy_base_url": "https://api.proxyapi.ru/openrouter/v1",
"scenarios_count": 12,
"executor_version": "0.1.0",
"judge_version": "0.1.0"
}

Этот манифест требуется главой 2 (этап 1 протокола регрессии) и обязателен для воспроизводимости.

## Главная страница (index.html)

Шаблон в `tester/templates/report.html.j2` через Jinja2.

### Структура страницы┌─────────────────────────────────────────────────────────┐
│  ОТЧЁТ ПО ПРОГОНУ                                       │
│  basket: finance_agent                                  │
│  run_id: 20260428-153012-finance_agent                  │
│  git: a1b2c3d (main)                                    │
│  started: 28.04.2026 15:30                             │
└─────────────────────────────────────────────────────────┘┌─────────────────────────────────────────────────────────┐
│  GATE-РЕШЕНИЕ                                           │
│  ╔═══════════╗                                          │
│  ║   ALLOW   ║   ← цветная бирка (зелёная/жёлтая/красная)│
│  ╚═══════════╝                                          │
│  Обоснование: все 4 условия выполнены.                  │
└─────────────────────────────────────────────────────────┘┌─────────────────────────────────────────────────────────┐
│  СВОДНЫЕ ПОКАЗАТЕЛИ                                     │
│  ┌────┬───────┬─────────┬──────┐                        │
│  │ RQS│ 0.93  │ ↑ +0.02 │ vs baseline                   │
│  │ PQS│ 0.87  │ ↓ -0.01 │                               │
│  │ RS │ 0.92  │ ─       │                               │
│  │ SS │ 1.00  │ ─       │                               │
│  │ ES │ 0.78  │ ↓ -0.05 │                               │
│  └────┴───────┴─────────┴──────┘                        │
└─────────────────────────────────────────────────────────┘┌─────────────────────────────────────────────────────────┐
│  МЕТРИКИ ПО ОСЯМ                                        │
│  Качество результата (4 рубрики)                        │
│  Качество процесса (5 метрик)                           │
│  Безопасность (3 метрики)                               │
│  Стоимость и время                                      │
│  → таблицы с pass_rate / средними / порогами / статусом │
└─────────────────────────────────────────────────────────┘┌─────────────────────────────────────────────────────────┐
│  ПРОВАЛЫ И РЕГРЕССИИ                                    │
│  ▣ SCN-FIN-007 [factual_correctness fail]               │
│    Запрос: "Сколько потратил на еду в августе?"         │
│    Ответ: "..."                                          │
│    Вердикт: fail. Обоснование: указанная сумма          │
│    не соответствует данным (фактически 12 450,         │
│    в ответе 13 200).                                    │
│    → trace: traces/SCN-FIN-007.json                     │
│                                                         │
│  ▣ SCN-FIN-014 [groundedness fail]                      │
│    ...                                                  │
└─────────────────────────────────────────────────────────┘┌─────────────────────────────────────────────────────────┐
│  УСПЕШНЫЕ СЦЕНАРИИ                                      │
│  (свернуто, можно раскрыть)                             │
│  ▶ SCN-FIN-001 — pass                                  │
│  ▶ SCN-FIN-002 — pass                                  │
└─────────────────────────────────────────────────────────┘

### Цвета gate-бирки

- ALLOW — `#2e7d32` (зелёный)
- CONDITIONAL_ALLOW — `#f9a825` (жёлтый)
- BLOCK — `#c62828` (красный)

### Стиль

- Чистый минималистичный дизайн без сторонних библиотек
- Шрифт: системный (sans-serif), моноспейс для кода и id
- Адаптивная вёрстка (мобильные не поддерживаем — отчёты смотрятся с десктопа)
- Тёмная тема не нужна
- Никакого JS не требуется (всё статично через Jinja2). Если детали сценария разворачиваются — через `<details>`/`<summary>`.

## Интерфейс модуля

```pythontester/reporter.pyfrom pathlib import Path
from .models import RunReportdef save_run_artifacts(
report: RunReport,
output_dir: Path,
) -> Path:
"""Сохраняет полный набор артефактов прогона.Создаёт:
- <output_dir>/report.json
- <output_dir>/manifest.json
- <output_dir>/traces/<scenario_id>.json (по одному файлу на сценарий)
- <output_dir>/assets/style.css
- <output_dir>/index.htmlReturns:
    Путь к index.html
"""def generate_html_report(
report: RunReport,
baseline_report: RunReport | None = None,
) -> str:
"""Генерирует HTML-строку. Используется внутри save_run_artifacts."""def generate_manifest(
report: RunReport,
) -> dict:
"""Собирает manifest.json. Включает git-инфо через subprocess."""

## Получение git-информации

```pythonimport subprocessdef _get_git_commit() -> str | None:
try:
return subprocess.check_output(
["git", "rev-parse", "--short", "HEAD"],
text=True,
).strip()
except Exception:
return Nonedef _get_git_branch() -> str | None:
try:
return subprocess.check_output(
["git", "rev-parse", "--abbrev-ref", "HEAD"],
text=True,
).strip()
except Exception:
return None

## Шаблон Jinja2

Лежит в `tester/templates/report.html.j2`. Передаваемый контекст:

```python{
"report": report,                # RunReport (Pydantic-модель)
"baseline": baseline_report,     # RunReport | None
"manifest": manifest,            # dict
"delta": {                       # сравнение с baseline (если есть)
"rqs": +0.02,                # положительные = улучшение
"pqs": -0.01,
...
},
"failed_outcomes": [...],        # список ScenarioOutcome где passed=False
"passed_outcomes": [...],        # passed=True
}

## CSS

```css/* tester/templates/style.css */
body {
font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
max-width: 1100px;
margin: 24px auto;
padding: 0 16px;
color: #222;
line-height: 1.5;
}
h1, h2, h3 { font-weight: 600; }
code, pre { font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 0.9em; }
pre { background: #f5f5f5; padding: 12px; border-radius: 4px; overflow-x: auto; }
table { border-collapse: collapse; width: 100%; margin: 16px 0; }
th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #e0e0e0; }
th { background: #f5f5f5; font-weight: 600; }.gate-badge { display: inline-block; padding: 8px 24px; font-weight: 700;
font-size: 1.2em; border-radius: 4px; color: white; }
.gate-allow { background: #2e7d32; }
.gate-conditional { background: #f9a825; }
.gate-block { background: #c62828; }.delta-positive { color: #2e7d32; }
.delta-negative { color: #c62828; }
.delta-zero { color: #757575; }.outcome-fail { border-left: 4px solid #c62828; padding: 12px 16px; margin: 12px 0; background: #fff5f5; }
.outcome-pass { border-left: 4px solid #2e7d32; padding: 12px 16px; margin: 12px 0; background: #f1f8e9; }

## Acceptance criteria

- [ ] `tester/reporter.py` содержит все три функции (save_run_artifacts, generate_html_report, generate_manifest)
- [ ] `tester/templates/report.html.j2` существует и валиден как Jinja2-шаблон
- [ ] `tester/templates/style.css` есть и подключён через `<link>` в шаблоне
- [ ] После прогона корзины в `reports/runs/<run_id>/` лежит:
  - index.html (открывается в браузере без ошибок)
  - report.json (валидный JSON, парсится обратно в RunReport)
  - manifest.json
  - traces/ с файлами по сценариям
  - assets/style.css
- [ ] index.html отображает gate-бирку правильным цветом (allow/conditional/block)
- [ ] Если baseline передан — показываются дельты со стрелками ↑↓
- [ ] Если baseline отсутствует — дельты не показываются, секция пустая
- [ ] Провалившиеся сценарии показаны раскрытыми, успешные — свёрнутыми через <details>
- [ ] `pytest tests/test_reporter.py` зелёный с кейсами:
  - generate_html_report выдаёт строку, начинающуюся с "<!DOCTYPE html>"
  - save_run_artifacts создаёт все ожидаемые файлы
  - manifest содержит git_commit (если git доступен) или null
- [ ] `ruff check tester/reporter.py` зелёный

## Не-цели

- Графики (динамика метрик во времени) — это spec 07 (Dashboard)
- Сравнение нескольких прогонов в одном отчёте — для дашборда, не для отчёта-снимка
- PDF-экспорт — не нужен
- Email-уведомления о результате прогона — не нужны
