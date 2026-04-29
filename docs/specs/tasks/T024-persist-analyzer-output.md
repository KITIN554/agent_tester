# T024 — Сохранять metric-analyzer вывод в reports/analysis/

## Приоритет: Желательно (#9, ~15 мин)

## Цель
Сейчас `tester evolve analyze` и `evolve cycle` печатают результат в
stdout. Чтобы сравнивать анализы между раундами и подшивать в защиту —
нужно персистить.

## Что нужно сделать

1. `tester/evolution.py::invoke_metric_analyzer`:
   - После получения dict — сохранять `reports/analysis/<run_id>.json`
     с полным результатом + timestamp.
   - Параллельно — markdown-отчёт `reports/analysis/<run_id>.md`
     (форматированный из dict: regressions / improvements / patterns /
     recommendations).
2. CLI `tester evolve analyze` — добавить опцию `--save-to PATH`,
   по умолчанию `reports/analysis/`.
3. `run_evolution_cycle` — каждый раунд сохраняет анализ автоматически.
4. Тест `test_evolution.py`:
   - после `invoke_metric_analyzer` ожидаемый файл существует на диске.

## Acceptance criteria

- [ ] `reports/analysis/<run_id>.json` и `<run_id>.md` создаются после
  каждого вызова `invoke_metric_analyzer`.
- [ ] `tester evolve cycle` тоже сохраняет анализ (через тот же путь).
- [ ] Существующие тесты + 1 новый зелёные.
- [ ] Закоммичено: `feat(evolve): persist metric-analyzer output to reports/analysis/`

## Зависимости
T014 (анализатор).
