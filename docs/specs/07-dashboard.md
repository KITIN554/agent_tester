# 07. Локальный дашборд (Streamlit)

## Цель
Дать тебе единое место, где видно динамику качества обоих агентов во времени, можно сравнить два прогона рядом и быстро провалиться к деталям конкретного сценария.

## Связь с диссертацией
- Глава 2, раздел 2.1.5 — диаграмма Парето качество ↔ стоимость
- Раздел 2.2.5, этап 4 — двухуровневая агрегация (корзина + сценарий)
- Дашборд — практическая реализация наблюдаемости (требование из 1.3)

## Принципы

- Single-file Streamlit-приложение в `dashboard/app.py`
- Источник данных — `reports/runs/<run_id>/report.json` (читается на лету при запуске)
- Никакого собственного хранилища, БД, кеша — всё из файлов
- Сравнение "текущий vs baseline" — через выбор двух прогонов в выпадающих списках

## Структура дашборда

### Боковая панель (sidebar)🎛️ Фильтры
─────────────
Корзина: [finance_agent ▼]   ← выпадающий, корзины из reports/runs/
Прогоны: [последние 30 ▼]    ← пресет временного окна
Текущий: [20260428-153012 ▼] ← последний по умолчанию
Сравнить с: [20260427-103045 ▼] ← предыдущий по умолчанию

### Главная страница — 4 вкладки (через `st.tabs`)

#### Вкладка 1: «Сводка»

- Большая карточка с gate-решением текущего прогона (как в HTML-отчёте, цветная)
- Таблица 5 сводных показателей (RQS, PQS, RS, SS, ES) с дельтами
- Краткая статистика: total_scenarios, passed, failed, pass_rate, total_cost_usd
- Список провалов (топ-10) — каждый кликабелен и переходит на вкладку «Сценарий»

#### Вкладка 2: «Динамика»

Графики через `plotly.express`:

- Линейный график RQS / PQS / RS / SS / ES по последним 30 прогонам (5 линий, легенда снизу)
- Линейный график pass_rate
- Линейный график avg_cost_usd на сценарий + p95_latency_s (двойная ось Y)

Каждый график имеет hover с run_id и точным значением.

#### Вкладка 3: «Парето»

Реализация диаграммы Парето из раздела 2.1.5 (рисунок 2.4):

- X — стоимость на сценарий ($)
- Y — RQS
- Каждая точка = один прогон корзины (за выбранное окно)
- Подписи точек = run_id (короткое)
- Парето-фронт автоматически выделяется (закрашенные точки = на фронте, полые = доминируемые)
- Алгоритм Парето:
```pythondef is_pareto_optimal(point, all_points):
# точка оптимальна, если нет другой точки с большим RQS И меньшей стоимостью
cost_x, rqs_x = point
for p in all_points:
if p == point: continue
if p[1] >= rqs_x and p[0] <= cost_x and p != point:
if p[1] > rqs_x or p[0] < cost_x:
return False
return True

#### Вкладка 4: «Сценарий»

Детальный разбор одного сценария:

- Выпадающий список всех сценариев из текущего прогона
- Описание сценария (id, описание, категория)
- Финальный ответ агента
- Таблица всех рубрик с вердиктами и rationale
- Метрики процесса
- Метрики безопасности
- Полная трасса (раскрывающаяся через `st.expander`):
  - Все шаги в порядке
  - Каждый шаг — JSON в `st.json`

## Файловая структураdashboard/
├── app.py            # главное приложение Streamlit
├── data_loader.py    # функции загрузки и кэширования отчётов
├── views/
│   ├── init.py
│   ├── summary.py    # вкладка «Сводка»
│   ├── trends.py     # вкладка «Динамика»
│   ├── pareto.py     # вкладка «Парето»
│   └── scenario.py   # вкладка «Сценарий»
└── init.py

## Загрузка данных

```pythondashboard/data_loader.py
from functools import lru_cache
from pathlib import Path
import json
from tester.models import RunReportREPORTS_ROOT = Path("reports/runs")@lru_cache(maxsize=128)
def load_report(run_id: str) -> RunReport:
path = REPORTS_ROOT / run_id / "report.json"
return RunReport.model_validate_json(path.read_text())def list_runs(basket: str | None = None) -> list[dict]:
"""Возвращает список прогонов с метаданными (run_id, basket, started_at, gate_decision)."""
runs = []
for run_dir in sorted(REPORTS_ROOT.glob("*/"), reverse=True):
report_path = run_dir / "report.json"
if not report_path.exists(): continue
try:
report = RunReport.model_validate_json(report_path.read_text())
if basket and report.basket != basket: continue
runs.append({
"run_id": report.run_id,
"basket": report.basket,
"started_at": report.started_at,
"gate_decision": report.gate_decision,
"rqs": report.aggregate_metrics.rqs,
})
except Exception:
continue
return runsdef list_baskets() -> list[str]:
runs = list_runs()
return sorted(set(r["basket"] for r in runs))

## Главное приложение

```pythondashboard/app.py
import streamlit as st
from dashboard.data_loader import list_baskets, list_runs, load_report
from dashboard.views import summary, trends, pareto, scenariost.set_page_config(
page_title="Agent Tester Dashboard",
layout="wide",
)st.title("Agent Tester — методология тестирования агентских систем")Sidebar
with st.sidebar:
st.header("🎛️ Фильтры")
basket = st.selectbox("Корзина", options=list_baskets() or ["—"])
if basket == "—":
st.info("Запусти tester run --basket baskets/finance_agent, чтобы увидеть данные.")
st.stop()runs = list_runs(basket=basket)
if not runs:
    st.info(f"Для корзины {basket} нет прогонов.")
    st.stop()current_run_id = st.selectbox("Текущий прогон", options=[r["run_id"] for r in runs])
baseline_run_id = st.selectbox(
    "Сравнить с (baseline)",
    options=["—"] + [r["run_id"] for r in runs if r["run_id"] != current_run_id],
)current_report = load_report(current_run_id)
baseline_report = load_report(baseline_run_id) if baseline_run_id != "—" else NoneTabs
tab1, tab2, tab3, tab4 = st.tabs(["📋 Сводка", "📈 Динамика", "🎯 Парето", "🔍 Сценарий"])
with tab1: summary.render(current_report, baseline_report)
with tab2: trends.render(basket, runs)
with tab3: pareto.render(basket, runs)
with tab4: scenario.render(current_report)

## Acceptance criteria

- [ ] `streamlit run dashboard/app.py` запускается без ошибок
- [ ] При отсутствии прогонов в `reports/runs/` дашборд показывает информативное сообщение
- [ ] Все 4 вкладки рендерятся без ошибок при корректных данных
- [ ] Сводка показывает gate-бирку правильным цветом
- [ ] Дельты RQS/PQS/RS/SS/ES со стрелками и цветами
- [ ] Динамика отображает 3 графика, каждый интерактивный
- [ ] Парето корректно определяет фронт (точки на фронте отличаются визуально)
- [ ] Сценарий-вкладка позволяет выбрать любой сценарий и видит его рубрики, метрики, трассу
- [ ] `pytest tests/test_dashboard_loader.py` зелёный с кейсами:
  - load_report корректно парсит report.json
  - list_runs фильтрует по basket
  - list_baskets возвращает уникальные значения
- [ ] `ruff check dashboard/` зелёный

## Не-цели

- Аутентификация — дашборд только локальный
- Real-time обновление — данные читаются при каждой смене фильтра, без websocket
- Экспорт графиков — Streamlit/Plotly даёт встроенный «📷» и этого достаточно
- Сравнение трёх и более прогонов — только парное сравнение
