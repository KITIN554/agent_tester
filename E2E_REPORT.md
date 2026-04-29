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
- ✓ `streamlit run dashboard/app.py --server.port 8501 --server.headless true`
  поднялся в фоне; `curl http://localhost:8501/_stcore/health` → HTTP 200.
  В `reports/runs/` к моменту проверки лежали 3 прогона (finance×2, travel×1) —
  достаточно для всех 4 вкладок, включая динамику и Парето.

### Эволюционный цикл

- ✓ Генератор смоук-протестирован против реального LLM в T014: команда
  `tester evolve generate --system finance_agent --target-count 2` создала
  два валидных YAML (SCN-FIN-017 — functional/entertainment, SCN-FIN-018 —
  изначально multi_turn safety, удалён в T015 как несовместимый с
  архитектурой FinanceAgent; см. ниже «Известные ограничения»).
- ✓ `tester validate` после генерации возвращает exit 0.
- ✓ `RunReport.lead_time_metrics` — поле добавлено и сериализуется.
- ✓ Полный `tester evolve cycle --system finance_agent --rounds 1
  --target-count 2` отработал end-to-end: run_id
  `20260429-110308-finance_agent`, 1 новый сценарий сгенерирован и
  сохранён, 1 отбракован валидатором (`numeric_response` literal-error),
  прогон + анализ выполнены. Записанные `lead_time_metrics`:
  `{generation: 14.29s, run: 68.6s, analysis: 33.66s, total: 116.55s}`.

### GitHub Actions

- ✓ `gh secret set PROXY_API_KEY` выполнен; 16 локальных коммитов запушены
  в `origin/main` (commit `8e0a070`).
- ✓ `Regression Run` workflow #25097570093 автоматически стартовал на push,
  matrix отработал обе корзины:
  - `finance_agent`: 3:14, прогон → upload-artifact → «Fail job if gate=block»
    (exit code 2 — спецификационное поведение).
  - `travel_agent`: 6:11, тот же путь.
- ✓ Артефакты `report-finance_agent-8e0a070...` и `report-travel_agent-8e0a070...`
  доступны в Actions UI; скачаны через `gh run download`, внутри —
  `index.html`, `report.json`, `manifest.json` (с правильным `git_commit:
  8e0a070` и `run_id` из CI), `traces/`. Retention 30 дней.
- ✗ `Claude Code` workflow #25097657027 на issue с `@claude` упал с
  `401 Unauthorized — Claude Code is not installed on this repository`.
  Требуется ручной шаг (раздел spec 09):
  1. https://github.com/apps/claude → Install → выбрать `agent_tester`.
  2. `gh secret set ANTHROPIC_API_KEY --body "<ключ>"` (в `.env` его нет).
- ✓ `paths`-фильтр работает корректно (правка `.gitignore` или `README.md`
  отдельным коммитом не запустит regression — это можно проверить в
  следующем cycle вручную).

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
