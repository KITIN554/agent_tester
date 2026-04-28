"""LLM-as-a-Judge: оценка трасс по 4 базовым рубрикам результата (spec 04).

TODO (вторая итерация): известное ограничение — судья и агент могут быть
на одной модели (например, Mistral Medium через proxyapi). Это создаёт
self-preference bias: судья склонен предпочитать ответы своей же модели.
В первой итерации методологии этот эффект НЕ контролируется. Для второй
итерации требуется зафиксировать отдельную JUDGE_MODEL, отличную от
LLM_MODEL агента, и провести 4-этапную калибровку из раздела 2.2.4 ВКР.
"""

from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from .models import (
    RubricEvaluation,
    RubricVerdict,
    Scenario,
    ScenarioTrace,
    StepType,
)

# ---------------------------------------------------------------------------
# Определения 4 базовых рубрик (точно по таблице 2.2 ВКР / spec 04)
# ---------------------------------------------------------------------------

RUBRIC_DEFINITIONS: dict[str, dict[str, Any]] = {
    "factual_correctness": {
        "name": "Фактологическая корректность",
        "what_checks": ("Соответствие числовых и фактических утверждений ответа данным агента"),
        "scale": "categorical",  # pass | partial | fail
        "inputs": ["user_query", "final_answer", "tool_results"],
        "default_threshold": "correct",
    },
    "intent_coverage": {
        "name": "Покрытие намерения",
        "what_checks": "Отвечает ли система на все аспекты запроса пользователя",
        "scale": "binary",  # pass | fail
        "inputs": ["user_query", "final_answer"],
        "default_threshold": "full",
    },
    "groundedness": {
        "name": "Отсутствие галлюцинаций",
        "what_checks": ("Опираются ли утверждения ответа на присутствующие в трассе данные"),
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

JUDGE_SYSTEM_PROMPT = """Ты — независимый эксперт по оценке качества ответов агентских систем.
Оцениваешь ответ агента по конкретной рубрике на основе:
- исходного запроса пользователя
- финального ответа агента
- результатов вызовов инструментов (если были)

ПРИНЦИПЫ:
- Будь строг: оценивай только то, что можно проверить по данным.
- Не добавляй своих допущений.
- Если данных недостаточно — выбирай "partial" или "na".
- Игнорируй стилистику текста, кроме рубрики tone_compliance.
- Оценивай независимо от того, что хочет услышать пользователь или автор системы.

ВЕРДИКТЫ:
- "pass": рубрика выполнена полностью
- "fail": рубрика провалена
- "partial": частично выполнена (только для categorical-шкал)
- "na": неприменимо

Отвечай СТРОГО в JSON-формате (одной строкой):
{"verdict": "pass|fail|partial|na",
 "score": null или число от 1 до 5,
 "rationale": "одно-два предложения на русском"}

Никакого текста вне JSON."""  # noqa: E501


# ---------------------------------------------------------------------------
# Класс судьи
# ---------------------------------------------------------------------------


class LLMJudge:
    """LLM-as-a-Judge для оценки трасс по 4 базовым рубрикам.

    Все LLM-вызовы:
    - JSON-mode (`response_format={"type": "json_object"}`)
    - temperature=0.0 (детерминированность)
    - max_tokens=300
    - обёрнуты в @retry(stop_after_attempt(3), wait_exponential(min=1, max=10))

    При невалидном JSON или сетевых ошибках после исчерпания retry —
    возвращает RubricEvaluation с verdict=NA вместо исключения.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        *,
        client: Any = None,
    ) -> None:
        if client is not None:
            # Внедрение зависимости (для тестов / Agent-as-a-Judge поверх судьи)
            self.client = client
        else:
            self.client = OpenAI(
                api_key=api_key or os.environ["PROXY_API_KEY"],
                base_url=base_url
                or os.environ.get("PROXY_BASE_URL", "https://api.proxyapi.ru/openrouter/v1"),
            )
        self.model = model or os.environ.get(
            "JUDGE_MODEL",
            os.environ.get("LLM_MODEL", "mistralai/mistral-medium-3.1"),
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        reraise=True,
    )
    def _call_and_parse(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Один LLM-вызов + парсинг JSON. Любой сбой триггерит retry."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=300,
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
        if not isinstance(data, dict):
            raise json.JSONDecodeError("Ожидался JSON-объект", content, 0)
        return data

    def evaluate_rubric(
        self,
        rubric: str,
        scenario: Scenario,
        trace: ScenarioTrace,
    ) -> RubricEvaluation:
        """Оценка одной рубрики; при любом сбое возвращает verdict=NA."""
        if rubric not in RUBRIC_DEFINITIONS:
            return RubricEvaluation(
                rubric=rubric,
                verdict=RubricVerdict.NA,
                rationale=f"Неизвестная рубрика: {rubric}",
            )

        messages = [
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": self._build_user_message(rubric, scenario, trace),
            },
        ]
        return self._invoke_and_parse(rubric, messages)

    def evaluate_all(
        self,
        scenario: Scenario,
        trace: ScenarioTrace,
    ) -> list[RubricEvaluation]:
        """Оценка всех рубрик из scenario.rubrics, по одной за раз."""
        return [self.evaluate_rubric(r, scenario, trace) for r in scenario.rubrics]

    def evaluate_multi_turn(
        self,
        scenario: Scenario,
        trace: ScenarioTrace,
    ) -> list[RubricEvaluation]:
        """Расширенная оценка для multi_turn: всегда передаём полную трассу.

        В первой итерации это всё та же 4-рубричная оценка, но в user-сообщение
        добавляется секция «ПОЛНАЯ ТРАССА» вне зависимости от inputs рубрики.
        Полноценный Agent-as-a-Judge с инструментами обхода трассы (раздел 2.2.4) —
        задача второй итерации.
        """
        results: list[RubricEvaluation] = []
        for rubric in scenario.rubrics:
            if rubric not in RUBRIC_DEFINITIONS:
                results.append(
                    RubricEvaluation(
                        rubric=rubric,
                        verdict=RubricVerdict.NA,
                        rationale=f"Неизвестная рубрика: {rubric}",
                    )
                )
                continue
            messages = [
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": self._build_user_message(
                        rubric, scenario, trace, include_full_trace=True
                    ),
                },
            ]
            results.append(self._invoke_and_parse(rubric, messages))
        return results

    # ------------------------------------------------------------------
    # Внутренние помощники
    # ------------------------------------------------------------------

    def _invoke_and_parse(
        self,
        rubric: str,
        messages: list[dict[str, Any]],
    ) -> RubricEvaluation:
        try:
            data = self._call_and_parse(messages)
        except json.JSONDecodeError:
            return RubricEvaluation(
                rubric=rubric,
                verdict=RubricVerdict.NA,
                rationale="Judge response parse error",
            )
        except Exception as exc:  # noqa: BLE001 — контракт: не падаем наружу
            return RubricEvaluation(
                rubric=rubric,
                verdict=RubricVerdict.NA,
                rationale=f"Judge API error: {type(exc).__name__}",
            )
        return _parse_judge_json(rubric, data)

    def _build_user_message(
        self,
        rubric: str,
        scenario: Scenario,
        trace: ScenarioTrace,
        *,
        include_full_trace: bool = False,
    ) -> str:
        defn = RUBRIC_DEFINITIONS[rubric]
        inputs = list(defn["inputs"])
        if include_full_trace and "trace" not in inputs:
            inputs.append("trace")

        lines = [
            f"РУБРИКА: {defn['name']}",
            f"ЧТО ОЦЕНИВАЕТСЯ: {defn['what_checks']}",
            f"ШКАЛА: {defn['scale']}",
            "",
            "ИСХОДНЫЙ ЗАПРОС:",
            _extract_user_query(scenario),
            "",
            "ФИНАЛЬНЫЙ ОТВЕТ АГЕНТА:",
            trace.final_answer or "(пусто)",
        ]
        if "tool_results" in inputs:
            lines.extend(
                [
                    "",
                    "РЕЗУЛЬТАТЫ ВЫЗОВОВ ИНСТРУМЕНТОВ:",
                    _format_tool_results(trace),
                ]
            )
        if "trace" in inputs:
            lines.extend(
                [
                    "",
                    "ПОЛНАЯ ТРАССА (для проверки groundedness):",
                    _format_compact_trace(trace),
                ]
            )
        if rubric == "tone_compliance":
            # Защита от verbosity bias: явное напоминание в пользовательском сообщении.
            lines.extend(
                [
                    "",
                    "ВАЖНО: длина ответа НЕ влияет на оценку. Оценивай ТОЛЬКО соответствие тону.",
                ]
            )
        lines.append("")
        lines.append("ВЫНЕСИ ВЕРДИКТ.")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Свободные хелперы
# ---------------------------------------------------------------------------


def _extract_user_query(scenario: Scenario) -> str:
    if scenario.input.user_message:
        return scenario.input.user_message
    if scenario.input.conversation_turns:
        return "\n".join(f"[{t.role}] {t.content}" for t in scenario.input.conversation_turns)
    return "(пусто)"


def _format_tool_results(trace: ScenarioTrace) -> str:
    """Список вызов→результат в JSON для секции tool_results."""
    items: list[dict[str, Any]] = []
    pending: dict[str, Any] | None = None
    for step in trace.steps:
        if step.step_type == StepType.TOOL_CALL:
            pending = {
                "tool": step.content.get("name"),
                "params": step.content.get("parameters", {}),
            }
        elif step.step_type == StepType.TOOL_RESULT and pending is not None:
            pending["result"] = step.content.get("result")
            pending["error"] = step.content.get("error")
            items.append(pending)
            pending = None
    if not items:
        return "(вызовов инструментов не было)"
    return json.dumps(items, ensure_ascii=False, default=str)


def _format_compact_trace(trace: ScenarioTrace) -> str:
    lines: list[str] = []
    for step in trace.steps:
        if step.step_type in (
            StepType.USER_MESSAGE,
            StepType.AGENT_MESSAGE,
            StepType.FINAL_ANSWER,
        ):
            text = step.content.get("message") or step.content.get("answer") or ""
            lines.append(f"[{step.step_type.value}] {text}")
        elif step.step_type == StepType.TOOL_CALL:
            params = json.dumps(step.content.get("parameters", {}), ensure_ascii=False, default=str)
            lines.append(f"[tool_call] {step.content.get('name')}({params})")
        elif step.step_type == StepType.TOOL_RESULT:
            payload = json.dumps(
                {
                    "result": step.content.get("result"),
                    "error": step.content.get("error"),
                },
                ensure_ascii=False,
                default=str,
            )
            lines.append(f"[tool_result] {payload}")
        elif step.step_type == StepType.ERROR:
            lines.append(f"[error] {step.content.get('error')}")
    return "\n".join(lines) if lines else "(трасса пуста)"


def _parse_judge_json(rubric: str, data: dict[str, Any]) -> RubricEvaluation:
    """Преобразует JSON-словарь от судьи в RubricEvaluation, защищаясь от мусора."""
    verdict_raw = str(data.get("verdict", "na")).lower().strip()
    try:
        verdict = RubricVerdict(verdict_raw)
    except ValueError:
        verdict = RubricVerdict.NA

    score: float | None = None
    score_raw = data.get("score")
    if score_raw is not None:
        try:
            score = float(score_raw)
        except (TypeError, ValueError):
            score = None
        else:
            if not 1.0 <= score <= 5.0:
                score = None

    rationale = str(data.get("rationale", ""))

    return RubricEvaluation(
        rubric=rubric,
        verdict=verdict,
        score=score,
        rationale=rationale,
    )


__all__ = [
    "LLMJudge",
    "RUBRIC_DEFINITIONS",
    "JUDGE_SYSTEM_PROMPT",
]
