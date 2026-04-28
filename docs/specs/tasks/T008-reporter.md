# T008 — HTML-репортер

## Цель
Реализовать `tester/reporter.py` и Jinja2-шаблон HTML-отчёта.

## Связанные спецификации
- 06-reporter.md — полная спецификация

## Что нужно сделать

1. Создать `tester/reporter.py`:
   - `save_run_artifacts(report, output_dir) -> Path`
   - `generate_html_report(report, baseline_report=None) -> str`
   - `generate_manifest(report) -> dict`
   - `_get_git_commit() -> str | None`
   - `_get_git_branch() -> str | None`
2. Создать `tester/templates/report.html.j2` — Jinja2-шаблон по структуре спек 06:
   - Шапка с метаданными
   - Gate-бирка цветная (allow/conditional/block)
   - Таблица RQS/PQS/RS/SS/ES с дельтами vs baseline
   - Метрики по 6 осям
   - Список провалов (раскрыты)
   - Список успешных (свёрнуты через `<details>`)
3. Создать `tester/templates/style.css` (контент из спек 06)
4. save_run_artifacts создаёт всю файловую структуру:
   - `<output_dir>/<run_id>/index.html`
   - `<output_dir>/<run_id>/report.json`
   - `<output_dir>/<run_id>/manifest.json`
   - `<output_dir>/<run_id>/traces/<scenario_id>.json` (по одному файлу на сценарий)
   - `<output_dir>/<run_id>/assets/style.css`
5. `tests/test_reporter.py`:
   - generate_html_report выдаёт строку с `<!DOCTYPE html>`
   - save_run_artifacts создаёт все ожидаемые файлы
   - manifest содержит git_commit или null
   - HTML корректен для пустого baseline (без дельт)
   - HTML корректен с baseline (показывает дельты)

## Acceptance criteria

- [ ] `tester/reporter.py` реализует все функции
- [ ] `tester/templates/report.html.j2` существует, валиден как Jinja2
- [ ] `tester/templates/style.css` существует
- [ ] HTML открывается в браузере без ошибок
- [ ] Gate-бирка имеет правильный цвет
- [ ] `pytest tests/test_reporter.py` зелёный
- [ ] `ruff check tester/reporter.py` зелёный
- [ ] Закоммичено: `feat: add HTML reporter with Jinja2 templates`

## Зависимости

T002, T007.
