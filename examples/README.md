# Примеры артефактов agent-tester

В этом каталоге лежат «живые» выходы стенда — открой их в браузере или
прочитай как код:

| Файл | Что внутри |
|---|---|
| `run_finance_v2.html` | Полный HTML-отчёт прогона `finance_agent` после v2 evolve cycle (3 свежих сценария + регрессия). Открывается локально без сервера. |
| `run_travel_v2.html`  | То же для `travel_agent` (multi_turn, более длинные трассы). |
| `scenario_finance_functional.yaml` | Канонический `single_turn` functional-сценарий. |
| `scenario_finance_negative.yaml`   | `negative` с `refusal_expected: true` и `forbidden_tool_calls`. |
| `scenario_travel_multiturn.yaml`   | `multi_turn` happy-path: подбор тура → calculate_price → consent → create_booking. |

## Как читать HTML-отчёт

1. **Topbar** сверху — gate-бирка + якорные ссылки на разделы.
2. **Gate-решение**: цветная бирка ALLOW / CONDITIONAL_ALLOW / BLOCK.
3. **Сводные показатели**: RQS / PQS / RS / SS / ES, дельты к baseline
   (если был передан).
4. **Метрики по осям**: 4 таблицы (качество результата, процесс,
   безопасность, стоимость и время) с прогресс-барами относительно
   порогов.
5. **Провалы**: каждый failed-сценарий — отдельная карточка с описанием,
   ответом агента, вердиктами рубрик и ссылкой на полную трассу
   `traces/<id>.json`.
6. **Успешные**: свёрнуты в `<details>`, разворачиваются по клику.

## Как воспроизвести

```bash
# Установка
pip install -e ".[dev]"

# .env с PROXY_API_KEY (обязательно), PROXY_BASE_URL, LLM_MODEL, JUDGE_MODEL
cp .env.example .env  # и заполнить

# Прогон корзины
set -a && . ./.env && set +a
tester run --basket baskets/finance_agent --output reports/runs --parallel 4

# Дашборд (после ≥1 прогона)
streamlit run dashboard/app.py

# Эволюционный цикл (generate → run → analyze)
tester evolve cycle --system finance_agent --rounds 1 --target-count 3
```
