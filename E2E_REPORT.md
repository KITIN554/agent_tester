# E2E проверка — финальный отчёт

**Дата проверки:** 2026-04-28
**Git commit:** `ed274c0` (на момент прогона)
**Окружение:** macOS (darwin 24.6.0), Python 3.12.0, Mistral Medium через
proxyapi.ru

## Сводка

Конвейер методологии (`loader → executor → judge → metrics → gate → reporter`)
прошёл end-to-end по обеим корзинам без падений и сбоев инфраструктуры. Обе
корзины получили решение **BLOCK** — это **легитимная сработка gate-логики
на реальное качество агентов**, а не баг методологии. Подробности ниже.

## Результаты

### Прогон корзин

| Basket | Run ID | Gate | RQS | PQS | RS | SS | ES | Cost, $ |
|---|---|---|---|---|---|---|---|---|
| finance_agent | `20260428-193646-finance_agent` | **BLOCK** | 0.868 | 0.850 | 0.529 | 0.471 | 0.868 | 0.0079 |
| travel_agent  | `20260428-193701-travel_agent`  | **BLOCK** | 0.789 | 0.629 | 0.188 | 0.000 | 0.789 | 0.1489 |

**Прогон finance_agent:** 17 сценариев, прошло 9 (52.9%). Причины BLOCK:
1 policy_violation, intent_coverage 0.647 (порог 0.9), step_accuracy 0.769
(0.85), parameter_extraction 0.756 (0.92), scenario_completion 0.824 (0.95),
refusal_accuracy 0.5 (0.98).

**Прогон travel_agent:** 16 сценариев, прошло 3 (18.75%). SS=0.000 (зафиксирован
PII leakage и/или policy violation). Метрики процесса просели в полтора раза
относительно finance.

**Итог:** оба прогона представляют собой **продуктовый результат методологии** —
обнаружение реальных пробелов в качестве дефолтных Mistral Medium-агентов.
Gate отказал в релизе по объективным числам. Тюнить агенты или ослаблять
пороги — задача отдельной итерации.

### Артефакты прогона

Структура `reports/runs/<run_id>/` для обоих прогонов:

- ✓ `index.html` — HTML-отчёт открывается без ошибок
- ✓ `report.json` — валиден через `RunReport.model_validate_json` (round-trip)
- ✓ `manifest.json` — содержит `git_commit=ed274c0`, `git_branch=main`,
  `model_agent`, `model_judge`, `proxy_base_url`, `scenarios_count`
- ✓ `traces/<scenario_id>.json` — по одному файлу на каждый сценарий (17 для
  finance, 16 для travel)
- ✓ `assets/style.css` — скопирован

### Дашборд

- ✓ `import dashboard.app` без ошибок (Streamlit 1.56.0, plotly импортируется)
- ✓ `py_compile` чистый на всех модулях dashboard
- ⚠ Интерактивный запуск `streamlit run dashboard/app.py` и визуальная
  проверка 4 вкладок выполняется пользователем вручную; на момент отчёта
  два прогона уже лежат в `reports/runs/`, чего достаточно для построения
  динамики, парето и сценарной вкладки.

### Эволюционный цикл

- ✓ Генератор смоук-протестирован против реального LLM в T014: команда
  `tester evolve generate --system finance_agent --target-count 2` создала
  два валидных YAML (SCN-FIN-017 — functional/entertainment, SCN-FIN-018 —
  изначально multi_turn safety, удалён в T015 как несовместимый с
  архитектурой FinanceAgent; см. ниже «Известные ограничения»).
- ✓ `tester validate` после генерации возвращает exit 0.
- ✓ `RunReport.lead_time_metrics` — поле добавлено и сериализуется.
- ⚠ Полный `tester evolve cycle --rounds 1` не запускался для финального
  отчёта — на 17 сценариях и 4 рубриках это ~$1.5 за раунд, инфраструктура
  показала работоспособность через 12 unit-тестов с моками (`tests/test_evolution.py`)
  и реальный smoke generate.

### GitHub Actions

- ✓ `.github/workflows/regression.yml` создан, валиден как YAML, содержит
  paths-фильтр, matrix-стратегию, артефакты с retention 30 дней, разбор
  exit code 0/1/2/3 в три отдельных step'а.
- ✓ `.github/workflows/claude.yml` создан, триггерится на `@claude` в
  issue/PR/review-комменте.
- ⚠ Реальный пуш в main и проверка работы в GitHub UI выполняется
  пользователем — для этого нужно `gh secret set PROXY_API_KEY` и
  `gh secret set ANTHROPIC_API_KEY`. Workflow-файлы готовы.

### Качество кода

- ✓ `pytest` зелёный: **107 тестов прошли, 0 провалов** (~1 сек).
- ✓ `ruff check .` зелёный (после exclusion `systems` и `data` —
  фикстуры, не код методологии).
- ✓ `ruff format --check .` — 33 файла уже отформатированы, расхождений нет.
- ✓ `mypy tester/` зелёный (`systems.*` исключены оверрайдом из-за
  конфликта с актуальными стабами openai SDK).

## Известные ограничения

- **Self-preference bias судьи** — судья и агент используют одну и ту же
  модель (Mistral Medium через proxyapi). В коде стоит TODO в верхнем
  докстринге `tester/judge.py`, в спеке 04 это явно фиксируется.
- **pass^k не реализован** — требует множественных прогонов одного сценария
  и снижение temperature; это вторая итерация методологии.
- **Калибровка судьи** через эталонный датасет (4-этапный протокол из
  раздела 2.2.4 ВКР) — отдельный пункт второй итерации.
- **Orchestrator не изолирует per-scenario исключения** — обнаружено в
  T015: один сценарий с архитектурно несовместимыми входами (multi_turn
  для FinanceAgent) приводит к падению всего прогона с exit=3 вместо
  записи `error` в трассу одного сценария. Bug-fix вынесен из scope T015,
  чтобы не «починить и продолжить» по правилу таски.
- **Генератор не учитывает single_turn-only архитектуру FinanceAgent** —
  тоже из T015: SCN-FIN-018, сгенерированный T014, был multi_turn для
  finance_agent. Удалён вручную, прогон повторён. Подсказку в prompt
  («для finance_agent только single_turn») можно добавить во второй итерации.

## Метрики проекта

- **Файлов кода в `tester/`:** 11 (`__init__`, `models`, `loader`,
  `executor`, `judge`, `metrics`, `gate`, `reporter`, `orchestrator`,
  `cli`, `evolution`)
- **Строк Python (tester + dashboard + tests):** 6645
- **Pytest-кейсов:** 107
- **YAML-сценариев в корзинах:** 33 (17 finance + 16 travel)
- **Стоимость двух прогонов:** $0.157 (finance $0.0079 + travel $0.149)
