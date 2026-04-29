# T017 — Прогон v1: получить ALLOW или CONDITIONAL_ALLOW

## Приоритет: КРИТИЧНО (#2, ~30 мин)

## Цель
После усиления промптов в T016 прогнать обе корзины и зафиксировать
улучшение. Цель — exit code 0 или 1 (а не 2 как было в v0).

## Что нужно сделать

1. Убедиться, что есть `.env` с `PROXY_API_KEY`, и переменные подгружены:
   ```bash
   set -a && . ./.env && set +a
   ```
2. Прогнать обе корзины:
   ```bash
   tester run --basket baskets/finance_agent --output reports/runs --parallel 4
   tester run --basket baskets/travel_agent  --output reports/runs --parallel 4
   ```
3. Зафиксировать `run_id`-ы как **v1 baseline** через симлинк (если уже
   реализован в T_baseline_override) или вручную пометить:
   ```bash
   tester baseline --basket finance_agent --set <finance_run_id>
   tester baseline --basket travel_agent  --set <travel_run_id>
   ```
4. Если хоть одна корзина BLOCK — задокументировать в коммит-сообщении
   причины и проверить, что они отличаются от v0 (агенты улучшились
   хоть в чём-то).

## Acceptance criteria

- [ ] Оба прогона завершились без exit=3 (внутренних ошибок).
- [ ] Артефакты на месте: `reports/runs/<run_id>/{index.html, report.json, manifest.json, traces/}`.
- [ ] Записать в коммит метрики до/после (RQS/PQS/RS/SS/ES, gate_decision,
  passed_count) для обоих агентов.
- [ ] **Целевое:** хотя бы одна корзина `ALLOW` или `CONDITIONAL_ALLOW`.
- [ ] Закоммичено: `chore: v1 regression run after agent prompt tightening`

## Зависимости
T016 (улучшенные промпты).

## Бюджет
Ожидаемая стоимость: $0.15–0.30 на оба прогона; время: 5–10 мин.
