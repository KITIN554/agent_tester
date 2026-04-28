"""Общие фикстуры pytest для тестов проекта."""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest


def _make_completion(
    content: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
) -> SimpleNamespace:
    """Собрать объект, по форме совпадающий с OpenAI ChatCompletion."""
    tc_objs: list[SimpleNamespace] | None = None
    if tool_calls:
        tc_objs = [
            SimpleNamespace(
                id=tc.get("id", f"call_{i}"),
                type="function",
                function=SimpleNamespace(
                    name=tc["name"],
                    arguments=tc["arguments"],
                ),
            )
            for i, tc in enumerate(tool_calls)
        ]
    message = SimpleNamespace(content=content, tool_calls=tc_objs)
    choice = SimpleNamespace(message=message, finish_reason="stop")
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )
    return SimpleNamespace(choices=[choice], usage=usage)


class MockProxyClient:
    """Минимальный мок OpenAI-клиента, совместимый с интерфейсом, который
    используют наши агенты и судья. Отдаёт заранее заготовленные ответы из FIFO-очереди.
    """

    def __init__(self) -> None:
        self._responses: list[Any] = []
        self.calls: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def queue_response(
        self,
        content: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        prompt_tokens: int = 10,
        completion_tokens: int = 5,
    ) -> None:
        """Положить следующий ответ в очередь.

        tool_calls: список словарей вида {"name": str, "arguments": str (JSON)}.
        """
        self._responses.append(
            _make_completion(content, tool_calls, prompt_tokens, completion_tokens)
        )

    def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if not self._responses:
            return _make_completion(content="(default mock answer)")
        return self._responses.pop(0)


@pytest.fixture
def mock_proxy_client() -> Iterator[MockProxyClient]:
    """Мок OpenAI-клиента для тестов агентов и судьи без реальных LLM-вызовов."""
    yield MockProxyClient()


@pytest.fixture
def sample_scenario() -> dict[str, Any]:
    """Пример валидного single_turn-сценария в формате spec 02.

    Возвращает словарь, чтобы фикстура была независима от Pydantic-моделей,
    которые появятся в `tester/models.py` в последующих тасках. Когда модели
    появятся, можно будет дополнительно прогонять этот словарь через
    `Scenario.model_validate(...)`.
    """
    return {
        "id": "SCN-FIN-001",
        "category": "functional",
        "type": "single_turn",
        "description": "Сумма расходов за прошлый месяц",
        "system": "finance_agent",
        "source": "manual",
        "created_at": "2026-04-28",
        "author": "tests@thesis",
        "input": {
            "user_message": "Сколько я потратил в прошлом месяце?",
            "available_tools": ["query_transactions"],
            "limits": {
                "max_steps": 5,
                "max_latency_s": 10,
                "max_cost_usd": 0.10,
            },
        },
        "expectations": {
            "must_contain": ["руб"],
            "required_tool_calls": [
                {
                    "name": "query_transactions",
                    "parameters": {
                        "period": "previous_month",
                        "aggregation": "sum",
                    },
                    "optional": False,
                }
            ],
            "forbidden_tool_calls": [],
            "entities": {
                "period": "previous_month",
                "aggregation": "sum",
            },
            "numeric_response": "required",
        },
        "rubrics": [
            "factual_correctness",
            "intent_coverage",
            "groundedness",
            "tone_compliance",
        ],
        "thresholds": {
            "factual_correctness": "correct",
            "groundedness": "pass",
            "intent_coverage": "full",
        },
    }
