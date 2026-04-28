# T013 — GitHub Actions

## Цель
Настроить два workflow: regression при push и Claude Code Action для @claude.

## Связанные спецификации
- 09-github-actions.md — полная спецификация

## Что нужно сделать

1. Создать `.github/workflows/regression.yml` точно по спек 09:
   - on: push в main + workflow_dispatch
   - paths-фильтр (только изменения кода/корзин)
   - matrix по двум корзинам
   - Переменные env (PROXY_BASE_URL, LLM_MODEL, JUDGE_MODEL)
   - Секрет PROXY_API_KEY используется
   - Артефакты HTML-отчётов (retention 30 дней)
   - Корректные exit codes для allow/conditional/block

2. Создать `.github/workflows/claude.yml`:
   - on: issue_comment, pull_request_review_comment, issues, pull_request_review
   - Триггер по `@claude` в тексте
   - permissions: contents:write, pull-requests:write, issues:write, id-token:write
   - Использует `anthropics/claude-code-action@v1`
   - allowed-tools: Read, Write, Edit, Glob, Grep, Bash(git:*), Bash(gh:*), Bash(pytest:*), Bash(ruff:*), Bash(python:*), Bash(pip:*)

3. Записать в README.md секцию «Настройка CI»:
   - Какие секреты нужны (`PROXY_API_KEY`, `ANTHROPIC_API_KEY`)
   - Как добавить через `gh secret set` или Settings UI
   - Как использовать `@claude` в issue
   - Как просмотреть артефакты прогона

## Acceptance criteria

- [ ] `.github/workflows/regression.yml` создан и валиден (нет красных аннотаций в Actions UI)
- [ ] `.github/workflows/claude.yml` создан
- [ ] README обновлён с разделом про CI
- [ ] Тестовый push с изменением в `tester/` запускает regression
- [ ] Тестовый push с изменением только в README не запускает regression (paths-фильтр)
- [ ] Workflow проходит обе корзины при чистом коде
- [ ] При искусственном BLOCK (например, добавили forbidden_tool_call в существующий сценарий) — workflow завершается с failure
- [ ] HTML-отчёты доступны как артефакты Actions
- [ ] Закоммичено: `feat: add GitHub Actions workflows (regression + claude)`

## Зависимости

T010 (нужен CLI), T011 (нужны корзины для прогона).

## Что НЕ делать в этой таске

- Не настраивать `gh secret set` в коде — это делает пользователь руками один раз
- Не настраивать branch protection — это вручную через UI
- Не делать самостоятельных пуш-веток или удалений
