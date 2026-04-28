# T015 — End-to-end проверка проекта

## Цель
Финальная проверка: всё работает вместе. После этой таски проект готов как объект защиты.

## Связанные спецификации
- 00-overview.md — раздел «Acceptance criteria для проекта в целом»

## Что нужно сделать

1. Прогнать обе корзины через CLI:
```bashtester run --basket baskets/finance_agent
tester run --basket baskets/travel_agent
   - Оба должны завершиться с exit code 0 (ALLOW) или 1 (CONDITIONAL_ALLOW)
   - Если 2 (BLOCK) — разбираться, что не так в реализации (баг в judge / metrics / agents)

2. Проверить все артефакты:
   - `reports/runs/<run_id>/index.html` открывается
   - `reports/runs/<run_id>/report.json` валиден через `RunReport.model_validate_json`
   - `reports/runs/<run_id>/manifest.json` содержит git_commit
   - `reports/runs/<run_id>/traces/` содержит JSON по каждому сценарию

3. Запустить дашборд:
```bashstreamlit run dashboard/app.py
   - Все 4 вкладки рендерятся
   - На динамике видно минимум 2 точки (если прогонов больше)

4. Прогнать эволюционный цикл:
```bashtester evolve cycle --system finance_agent --rounds 1
   - Сгенерировались новые сценарии
   - Корзина прошла прогон
   - В отчёте есть `lead_time_metrics`

5. Проверить GitHub Actions:
   - Сделать тестовый коммит в `tester/` (например, добавить комментарий)
   - Запушить в main
   - Убедиться что regression workflow запустился
   - Скачать артефакты HTML-отчётов

6. Проверить @claude в issue:
   - Создать issue с текстом `@claude напиши краткий комментарий о том, что ты видишь в проекте`
   - Убедиться что Claude Code Action ответил

7. Финальные общие проверки:
```bashpytest                    # все тесты зелёные
ruff check .              # без ошибок
ruff format --check .     # без правок

## Создать E2E_REPORT.md в корне репозитория

Документ-фикс факт прохождения всех проверок:

```markdownE2E проверка — финальный отчётДата проверки: YYYY-MM-DDРезультатыПрогон корзин

finance_agent: <ALLOW|CONDITIONAL_ALLOW>, RQS=X, PQS=X, ...
travel_agent: <ALLOW|CONDITIONAL_ALLOW>, RQS=X, PQS=X, ...
Артефакты прогона

HTML-отчёты: ✓
report.json валиден: ✓
manifest.json с git_commit: ✓
Trace-файлы по сценариям: ✓
Дашборд

Запуск: ✓
4 вкладки рендерятся: ✓
Парето-фронт корректен: ✓
Эволюционный цикл

Генератор создал новые сценарии: ✓
Анализатор отработал: ✓
Lead time metrics записаны: ✓
GitHub Actions

Regression workflow срабатывает на push: ✓
Артефакты доступны: ✓
@claude в issue работает: ✓
Качество кода

pytest: ✓ (X тестов прошли, 0 провалов)
ruff check: ✓
ruff format: ✓
Известные ограничения (для главы 3)
Self-preference bias судьи (одна модель для агента и судьи)
pass^k не реализован (требует множественных прогонов одного сценария)
Калибровка судьи через эталонный датасет — отдельный пункт второй итерации
Метрики проекта
Файлов кода: X
Строк кода: Y
Тестов: Z
Сценариев в корзинах: 15+15


## Acceptance criteria

- [ ] Обе корзины прогоняются без BLOCK
- [ ] Все артефакты на месте
- [ ] Дашборд работает
- [ ] Эволюционный цикл работает
- [ ] GitHub Actions срабатывают
- [ ] `pytest` зелёный
- [ ] `ruff check` зелёный
- [ ] E2E_REPORT.md создан и описывает результаты
- [ ] Закоммичено: `chore: add E2E verification report`

## Зависимости

T001-T014 (все предыдущие).

## Если что-то падает

Не пытайся «починить и продолжить» — сообщи мне (пользователю), что именно упало, и я разберу. Признаки правильного провала:

- exit code 2 (BLOCK) на чистой корзине → баг в gate / metrics / judge
- сегфолт в Streamlit → проблема версий streamlit/plotly
- 5xx ошибки в LLM-вызовах → проблема с прокси, не с кодом
- timeout в GitHub Actions → нужно увеличивать `--parallel` или урезать корзины
