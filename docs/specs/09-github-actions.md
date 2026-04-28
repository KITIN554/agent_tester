# 09. GitHub Actions: автоматизация регрессии и Claude Code

## Цель
Настроить CI-автоматизацию двух типов:
1. **Регрессионный прогон** при каждом push в main — запускает `tester run` на обеих корзинах, выкладывает HTML-отчёты как artifacts, при BLOCK помечает коммит красной галочкой.
2. **Claude Code Action** — Claude Code отвечает на @claude в issue/PR, может реализовывать таски и делать коммиты в feature-ветки.

## Связь с диссертацией
- Глава 2, раздел 2.2.5 — Протокол регрессионного эксперимента, этапы 2 и 6 (прогон стендом, гейт релиза)
- Раздел 1.3, требование 6 — применимость в CI/CD
- Глава 3, раздел про lead time — этот workflow и есть основное доказательство автоматизации цикла

## Структура workflow-файлов
.github/workflows/
├── regression.yml      # автоматический прогон при push
└── claude.yml          # отвечает на @claude в issue/PR

## GitHub Secrets (настроить ОДИН раз)

В Settings → Secrets and variables → Actions добавить:

| Secret | Назначение |
|---|---|
| `PROXY_API_KEY` | ключ proxyapi.ru для прогона агентов и судьи |
| `ANTHROPIC_API_KEY` | ключ Anthropic для Claude Code Action |

`PROXY_BASE_URL` и `LLM_MODEL` идут в env workflow напрямую — это не секреты.

## Workflow 1: regression.yml

```yaml
name: Regression Run

on:
  push:
    branches: [main]
    paths:
      - 'systems/**'
      - 'tester/**'
      - 'baskets/**'
      - 'pyproject.toml'
      - '.github/workflows/regression.yml'
  workflow_dispatch:  # позволяет запустить вручную через UI

permissions:
  contents: read
  pull-requests: write  # для комментариев в PR при блокировке

env:
  PROXY_BASE_URL: https://api.proxyapi.ru/openrouter/v1
  LLM_MODEL: mistralai/mistral-medium-3.1
  JUDGE_MODEL: mistralai/mistral-medium-3.1
  RUN_BUDGET_USD: "5.00"

jobs:
  regression:
    name: Run regression on ${{ matrix.basket }}
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false  # один провал не блокирует другие
      matrix:
        basket:
          - finance_agent
          - travel_agent

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
          cache-dependency-path: pyproject.toml

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"

      - name: Generate synthetic data (idempotent)
        run: |
          python data/generate_transactions.py
          python data/generate_destinations.py

      - name: Validate basket
        run: tester validate --basket baskets/${{ matrix.basket }}

      - name: Run regression
        env:
          PROXY_API_KEY: ${{ secrets.PROXY_API_KEY }}
        run: |
          tester run \
            --basket baskets/${{ matrix.basket }} \
            --output reports/runs \
            --parallel 4
        continue-on-error: true   # exit code 1 (conditional) и 2 (block) — не падаем мгновенно
        id: run_step

      - name: Upload HTML report as artifact
        if: always()  # выкладываем артефакт даже при провале
        uses: actions/upload-artifact@v4
        with:
          name: report-${{ matrix.basket }}-${{ github.sha }}
          path: reports/runs/
          retention-days: 30

      - name: Fail job if gate=block
        if: steps.run_step.outcome == 'failure' && steps.run_step.outputs.exit_code == '2'
        run: |
          echo "::error::Gate decision: BLOCK for basket ${{ matrix.basket }}"
          exit 2

      - name: Warn if gate=conditional_allow
        if: steps.run_step.outputs.exit_code == '1'
        run: |
          echo "::warning::Gate decision: CONDITIONAL_ALLOW for basket ${{ matrix.basket }}"

  summarize:
    name: Summarize all baskets
    runs-on: ubuntu-latest
    needs: regression
    if: always()
    steps:
      - name: Download all artifacts
        uses: actions/download-artifact@v4
        with:
          path: ./all-reports

      - name: Print combined summary
        run: |
          echo "## Регрессионный прогон" >> $GITHUB_STEP_SUMMARY
          echo "" >> $GITHUB_STEP_SUMMARY
          echo "Commit: ${{ github.sha }}" >> $GITHUB_STEP_SUMMARY
          echo "" >> $GITHUB_STEP_SUMMARY
          echo "Артефакты с HTML-отчётами доступны во вкладке Actions → текущий run." >> $GITHUB_STEP_SUMMARY
```

### Объяснение ключевых решений

- **Matrix по корзинам** — обе корзины (finance_agent и travel_agent) гоняются параллельно как независимые джобы. Если один упадёт, второй продолжит.
- **Paths-фильтр** — workflow срабатывает только при изменении кода агентов или тестировщика, не на правки в README/docs.
- **continue-on-error + проверка exit code** — позволяет различать allow/conditional/block и реагировать соответственно.
- **Артефакты с retention 30 дней** — HTML-отчёты доступны для скачивания со страницы run, без необходимости поднимать сервер.
- **Summary через `$GITHUB_STEP_SUMMARY`** — это вкладка Summary каждого run, удобно для быстрого взгляда.

## Workflow 2: claude.yml

Claude Code Action позволяет тебе писать `@claude <задача>` в issue или PR-комменте, и Claude Code будет работать в твоём репозитории — реализовывать фичи, чинить баги, отвечать на вопросы.

```yaml
name: Claude Code

on:
  issue_comment:
    types: [created]
  pull_request_review_comment:
    types: [created]
  issues:
    types: [opened, assigned]
  pull_request_review:
    types: [submitted]

jobs:
  claude:
    if: |
      (github.event_name == 'issue_comment' && contains(github.event.comment.body, '@claude')) ||
      (github.event_name == 'pull_request_review_comment' && contains(github.event.comment.body, '@claude')) ||
      (github.event_name == 'pull_request_review' && contains(github.event.review.body, '@claude')) ||
      (github.event_name == 'issues' && (contains(github.event.issue.body, '@claude') || contains(github.event.issue.title, '@claude')))
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
      issues: write
      id-token: write
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 1

      - name: Run Claude Code
        uses: anthropics/claude-code-action@v1
        with:
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          claude_args: |
            --max-turns 30
            --allowed-tools "Read,Write,Edit,Glob,Grep,Bash(git:*),Bash(gh:*),Bash(pytest:*),Bash(ruff:*),Bash(python:*),Bash(pip:*)"
```

### Использование

После настройки ты в любом issue или PR пишешь:
@claude реализуй задачу docs/specs/tasks/T002-models.md

Claude Code:
1. Прочитает таск-файл
2. Прочитает связанные спецификации (docs/specs/02-scenario-format.md и т.д.)
3. Реализует код в feature-ветке `claude/T002-models`
4. Создаст PR с описанием
5. Тебе останется ревью и merge

### Альтернатива: явный prompt без @claude

Можно сделать workflow, который запускается на конкретное событие (например, новое issue с меткой `task`) и сразу даёт Claude Code задачу:

```yaml
on:
  issues:
    types: [labeled]

jobs:
  implement_task:
    if: github.event.label.name == 'task'
    ...
    steps:
      - uses: anthropics/claude-code-action@v1
        with:
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          prompt: |
            Реализуй задачу из issue #${{ github.event.issue.number }}.
            Прочитай docs/specs/tasks/<id>.md и реализуй согласно спецификации.
            Создай feature-ветку, сделай коммиты, открой PR.
          claude_args: --max-turns 50
```

В первой итерации настроим только `@claude`-вариант — он гибче.

## Установка Claude Code Action

В Claude Code локально (НЕ в GitHub Actions) выполни ОДИН раз:

```bash
claude
> /install-github-app
```

Это:
1. Откроет браузер на странице установки GitHub App
2. Попросит выбрать репозиторий agent_tester
3. Автоматически добавит секрет `ANTHROPIC_API_KEY` если его нет
4. Создаст пример workflow-файла

Если `/install-github-app` упадёт — вручную:
1. https://github.com/apps/claude → Install
2. Выбрать репозиторий
3. Settings → Secrets and variables → Actions → New repository secret → ANTHROPIC_API_KEY

## Branch protection (рекомендуется)

После того как regression.yml работает — в Settings → Branches → main:

- Require status checks to pass before merging:
  - regression / Run regression on finance_agent
  - regression / Run regression on travel_agent
- Require branches to be up to date before merging
- Не включать "Require pull request reviews" — у тебя авто-push в main по согласованию

Это автоматически блокирует merge PR, если регрессия упала. При прямом push в main GitHub помечает коммит красной галочкой, но не откатывает.

## Лимиты и стоимость

- Каждый прогон корзины ~ 30-60 сценариев × 2-5 секунд × Mistral Medium ≈ $0.50-$2.00
- Action минут: ubuntu-latest бесплатно для публичных репо, для приватных — 2000 минут/месяц на бесплатном тарифе. Один прогон ~5-10 минут × 2 корзины = 10-20 минут.
- Claude Code Action — оплачивается по Anthropic API биллингу: ~$0.10-$0.50 за обычную таску.

## Acceptance criteria

- [ ] `.github/workflows/regression.yml` существует и валидирован GitHub (нет красных аннотаций в Actions UI)
- [ ] `.github/workflows/claude.yml` существует
- [ ] Секреты `PROXY_API_KEY` и `ANTHROPIC_API_KEY` добавлены в репозиторий
- [ ] Тестовый push в main с малым изменением (например, в README) НЕ запускает regression workflow (paths-фильтр работает)
- [ ] Тестовый push в main с изменением в `tester/` запускает regression workflow
- [ ] Workflow проходит обе корзины и выкладывает артефакты
- [ ] Артефакт-zip содержит index.html, который можно скачать и открыть локально
- [ ] При искусственно сделанном BLOCK (например, добавили forbidden_tool_call в сценарий, который агент гарантированно вызовет) — workflow завершается с failure status
- [ ] `@claude напиши тест для функции X` в issue вызывает Claude Code Action и тот реагирует
- [ ] Claude Code Action создаёт ветки `claude/<id>` и PR

## Не-цели

- Кеширование LLM-ответов между runs — не нужно (каждый прогон должен быть свежим)
- Развёртывание дашборда на GitHub Pages — это отдельная задача в будущем
- Запуск дашборда в Action — Streamlit-сервер не нужен в CI
- Slack/Telegram уведомления — делаются позже, когда станет нужно
- Self-hosted runners — не нужны для дипломного проекта
