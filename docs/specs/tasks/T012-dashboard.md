# T012 — Локальный Streamlit-дашборд

## Цель
Реализовать дашборд для визуализации прогонов: 4 вкладки (Сводка, Динамика, Парето, Сценарий).

## Связанные спецификации
- 07-dashboard.md — полная спецификация

## Что нужно сделать

1. Создать структуру:dashboard/
├── init.py
├── app.py
├── data_loader.py
└── views/
├── init.py
├── summary.py
├── trends.py
├── pareto.py
└── scenario.py

2. `dashboard/data_loader.py`:
   - `load_report(run_id) -> RunReport` (с `@lru_cache`)
   - `list_runs(basket=None) -> list[dict]`
   - `list_baskets() -> list[str]`

3. `dashboard/app.py`:
   - `st.set_page_config(layout="wide")`
   - Sidebar: выбор basket, current_run, baseline
   - 4 таба через `st.tabs`

4. `views/summary.py`:
   - Цветная gate-бирка (allow/conditional/block)
   - Карточки RQS/PQS/RS/SS/ES с дельтами
   - Топ-10 провалов

5. `views/trends.py`:
   - Линейный график RQS/PQS/RS/SS/ES по последним 30 прогонам
   - График pass_rate
   - График avg_cost + p95_latency (двойная ось)

6. `views/pareto.py`:
   - Scatter cost × RQS
   - Парето-фронт (закрашенные vs полые точки)
   - Алгоритм `is_pareto_optimal`

7. `views/scenario.py`:
   - Selectbox со сценариями
   - Описание + финальный ответ
   - Таблица рубрик
   - Метрики процесса/безопасности
   - Раскрывающаяся трасса (`st.expander`)

8. `tests/test_dashboard_loader.py`:
   - `load_report` парсит report.json
   - `list_runs(basket="finance_agent")` фильтрует
   - `list_baskets` возвращает уникальные

## Acceptance criteria

- [ ] `streamlit run dashboard/app.py` запускается без ошибок
- [ ] При отсутствии прогонов — информативное сообщение, не падение
- [ ] Все 4 вкладки рендерятся при наличии хотя бы 2 прогонов
- [ ] Gate-бирка корректно цветная
- [ ] Парето-фронт визуально выделен
- [ ] Трасса сценария разворачивается через expander
- [ ] `pytest tests/test_dashboard_loader.py` зелёный
- [ ] `ruff check dashboard/` зелёный
- [ ] Закоммичено: `feat: add Streamlit dashboard with 4 tabs (summary, trends, pareto, scenario)`

## Зависимости

T002, T011 (нужны прогоны для тестирования визуально). Для этого перед T012 запусти `tester run` на обеих корзинах хотя бы 2-3 раза, чтобы было что показывать.

## Замечания

- Plotly-графики обязательно с hover (run_id + значение)
- Шрифт и цвета — дефолтные Streamlit, не переопределяй
- Темная тема не нужна
