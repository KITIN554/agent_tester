# 04. Судья: LLM-as-a-Judge и Agent-as-a-Judge

## Цель
Реализовать автоматический оценщик трасс по рубрикам результата. Поддерживает два режима: LLM-as-a-Judge для одиночных задач и Agent-as-a-Judge для многошаговых.

## Связь с диссертацией
- Глава 2, раздел 2.1.2 — Метрики качества результата (4 типовые рубрики)
- Таблица 2.2 — Конструктор типовых рубрик качества результата
- Раздел 2.2.4 — Калибровка автоматических судей (4 этапа)
- Рисунок 2.2 — четыре рубрики LLM-as-a-Judge
- Рисунок 2.3 — Agent-as-a-Judge с инструментами обхода трассы

## Четыре базовые рубрики (точно по таблице 2.2)

```pythonRUBRIC_DEFINITIONS = {
"factual_correctness": {
"name": "Фактологическая корректность",
"what_checks": "Соответствие числовых и фактических утверждений ответа данным агента",
"scale": "categorical",  # pass | partial | fail
"inputs": ["user_query", "final_answer", "tool_results"],
"default_threshold": "correct",
},
"intent_coverage": {
"name": "Покрытие намерения",
"what_checks": "Отвечает ли система на все аспекты запроса",
"scale": "binary",  # pass (full) | fail (partial/incomplete)
"inputs": ["user_query", "final_answer"],
"default_threshold": "full",
},
"groundedness": {
"name": "Отсутствие галлюцинаций",
"what_checks": "Опираются ли утверждения ответа на присутствующие в трассе данные",
"scale": "binary",
"inputs": ["final_answer", "trace"],
"default_threshold": "pass",
},
"tone_compliance": {
"name": "Соответствие стилю",
"what_checks": "Выдержан ли тон ответа в принятых для продукта рамках",
"scale": "numeric_1_5",
"inputs": ["final_answer"],
"default_threshold": 4.0,
},
}

## Архитектура судьи

### Базовый класс `LLMJudge`

```pythontester/judge.py
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponentialclass LLMJudge:
def init(
self,
api_key: str | None = None,
base_url: str | None = None,
model: str | None = None,
) -> None:
# Инициализация клиента через PROXY_API_KEY/PROXY_BASE_URL/JUDGE_MODEL
...def evaluate_rubric(
    self,
    rubric: str,
    scenario: Scenario,
    trace: ScenarioTrace,
) -> RubricEvaluation:
    """Оценка одной рубрики. Использует JSON-mode для строгой структуры ответа."""
    ...def evaluate_all(
    self,
    scenario: Scenario,
    trace: ScenarioTrace,
) -> list[RubricEvaluation]:
    """Оценка всех рубрик из scenario.rubrics. Параллельно через asyncio.gather."""
    ...

### Системный промпт судьи

Один общий промпт для всех рубрик, специализация — в user-сообщении:Ты — независимый эксперт по оценке качества ответов агентских систем.
Оцениваешь ответ агента по конкретной рубрике на основе:

исходного запроса пользователя
финального ответа агента
результатов вызовов инструментов (если были)
ПРИНЦИПЫ:

Будь строг: оценивай только то, что можно проверить по данным.
Не добавляй своих допущений.
Если данных недостаточно — выбирай "partial" или "na".
Игнорируй стилистику текста, кроме рубрики tone_compliance.
ВЕРДИКТЫ:

"pass": рубрика выполнена полностью
"fail": рубрика провалена
"partial": частично выполнена (только для categorical-шкал)
"na": неприменимо
Отвечай СТРОГО в JSON-формате:
{"verdict": "pass|fail|partial|na", "score": null или число от 1 до 5, "rationale": "одно-два предложения на русском"}Никакого текста вне JSON.

### User-сообщение для каждой рубрики

Формируется динамически с учётом inputs из RUBRIC_DEFINITIONS:РУБРИКА: <name>
ЧТО ОЦЕНИВАЕТСЯ: <what_checks>
ШКАЛА: <scale>ИСХОДНЫЙ ЗАПРОС:
<user_query>ФИНАЛЬНЫЙ ОТВЕТ АГЕНТА:
<final_answer>[если в inputs есть "tool_results":]
РЕЗУЛЬТАТЫ ВЫЗОВОВ ИНСТРУМЕНТОВ:
<json_dump_of_tool_calls_and_results>[если в inputs есть "trace":]
ПОЛНАЯ ТРАССА (для проверки groundedness):
<compact_trace>ВЫНЕСИ ВЕРДИКТ.

### Защита от 4 систематических смещений (раздел 2.2.4)

В коде судьи учесть:

1. **Position bias** — не используем попарных сравнений в этой версии (только абсолютная оценка), поэтому неактуально. Если в будущем добавим — рандомизировать порядок.

2. **Verbosity bias** — для tone_compliance явно прописать в промпте: «длина ответа не влияет на оценку, оценивай ТОЛЬКО соответствие тону».

3. **Self-preference bias** — судья и агент могут использовать одну и ту же модель (Mistral Medium через proxyapi). Зафиксировать это как известное ограничение в комментарии к коду + в Acceptance criteria. В будущей версии — отдельная переменная JUDGE_MODEL, которую можно задать другую.

4. **Sycophancy** — в промпте: «оценивай независимо от того, что хочет услышать пользователь или автор системы».

### JSON-mode и парсинг

```python@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def _call(self, messages: list[dict]) -> str:
r = self.client.chat.completions.create(
model=self.model,
messages=messages,
response_format={"type": "json_object"},
temperature=0.0,  # детерминированность
max_tokens=300,
)
return r.choices[0].message.content or "{}"

Парсинг JSON-ответа: `json.loads(response)`. При ошибке парсинга — повторный запрос (через retry). Если все три попытки вернули невалидный JSON — RubricEvaluation с verdict=NA и rationale="Judge response parse error".

## Agent-as-a-Judge для multi_turn (рисунок 2.3)

Для multi_turn сценариев одного финального ответа недостаточно — нужно проверять трассу пошагово. Добавляется метод:

```pythondef evaluate_multi_turn(
self,
scenario: Scenario,
trace: ScenarioTrace,
) -> list[RubricEvaluation]:
"""Расширенная оценка для multi-turn:
- factual_correctness: на каждом ключевом шаге сверяется с tool_results
- groundedness: проверяет, нет ли в репликах агента выдуманных сущностей
- intent_coverage: финальный диалог покрывает ли исходное намерение
- tone_compliance: средняя по всем репликам агента
"""

В первой итерации можно ограничиться вызовом тех же 4 рубрик, но передавать в them полную трассу (а не только final_answer). Полноценный обход трассы инструментами судьи — задача второй итерации, отдельная спецификация позже.

## Использование в orchestrator

```pythontester/orchestrator.py (фрагмент)
judge = LLMJudge()
for scenario in scenarios:
trace = execute_scenario(scenario)
rubric_evals = judge.evaluate_all(scenario, trace)
process_metrics = compute_process_metrics(scenario, trace)
safety_metrics = compute_safety_metrics(scenario, trace)
outcome = ScenarioOutcome(...)

## Acceptance criteria

- [ ] `tester/judge.py` содержит:
  - класс LLMJudge с методами evaluate_rubric, evaluate_all, evaluate_multi_turn
  - константу RUBRIC_DEFINITIONS со всеми четырьмя рубриками
  - константы JUDGE_SYSTEM_PROMPT и шаблон user-сообщения
- [ ] LLM-вызовы используют JSON-mode и temperature=0.0
- [ ] Все вызовы обёрнуты в @retry(stop_after_attempt(3))
- [ ] При невалидном JSON ответе судья возвращает RubricEvaluation с verdict=NA
- [ ] `pytest tests/test_judge.py` зелёный с кейсами (через unittest.mock):
  - evaluate_rubric для каждой из 4 рубрик возвращает корректный RubricEvaluation
  - evaluate_all вызывает evaluate_rubric для каждой рубрики из scenario.rubrics
  - При ошибке LLM (3 раза подряд retry) возвращается RubricEvaluation с verdict=NA, а не исключение
- [ ] В коде есть комментарий про известное ограничение: судья и агент могут быть на одной модели (self-preference bias) — оставлен на вторую итерацию
- [ ] `ruff check tester/judge.py` зелёный

## Не-цели

- Калибровка судьи (4-этапный протокол из раздела 2.2.4) — отдельная задача в эволюционной части (spec 10), не в первой итерации
- Полноценный Agent-as-a-Judge с собственными инструментами обхода трассы (validate_calculation, check_pii_handling) — вторая итерация
- Pairwise comparison и контроль position bias — не нужно в этой версии
