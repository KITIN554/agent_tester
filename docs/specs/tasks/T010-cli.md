# T010 — CLI агента-тестировщика

## Цель
Реализовать `tester/cli.py` — команды run, validate, report, compare, baseline.

## Связанные спецификации
- 08-cli.md — полная спецификация

## Что нужно сделать

1. Создать `tester/cli.py` с группой команд через `click`:
   - `tester run --basket PATH [--output DIR] [--judge-model MODEL] [--parallel N] [--max-scenarios N]`
   - `tester validate --basket PATH`
   - `tester baseline --basket NAME [--set RUN_ID]`
   - `tester report [RUN_ID] [--latest --basket NAME]`
   - `tester compare RUN_A RUN_B`
2. Exit codes:
   - 0 — ALLOW
   - 1 — CONDITIONAL_ALLOW
   - 2 — BLOCK
   - 3 — внутренняя ошибка (исключения)
3. Прогресс-бар через rich во время run
4. Все вывод в терминал — через rich.console.Console
5. `tests/test_cli.py` через `click.testing.CliRunner`:
   - `tester --help` выводит все команды
   - `tester validate` на валидной корзине → exit 0
   - `tester validate` на несуществующей корзине → exit code != 0
   - `tester compare` выводит таблицу

## Acceptance criteria

- [ ] `tester/cli.py` реализует все 5 команд
- [ ] `tester --help` показывает группу команд
- [ ] После `pip install -e .` команда `tester` доступна в окружении
- [ ] Exit codes соответствуют спецификации
- [ ] `pytest tests/test_cli.py` зелёный
- [ ] `ruff check tester/cli.py` зелёный
- [ ] Закоммичено: `feat: add CLI with run/validate/report/compare/baseline commands`

## Зависимости

T009.
