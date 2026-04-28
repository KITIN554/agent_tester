"""Finance Agent — QA-агент по личным финансам."""

import json
import os
import time
from datetime import datetime
from typing import Any

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from .prompts import SYSTEM_PROMPT
from .tools import TOOL_REGISTRY, TOOLS_SCHEMA
from .types import AgentResponse, StepType, TraceStep

# Стоимость DeepSeek-chat (актуально на момент написания)
# Если цены изменятся — поправь здесь
PRICE_INPUT_PER_1K = 0.00027
PRICE_OUTPUT_PER_1K = 0.00110


class FinanceAgent:
    """QA-агент по личным финансам пользователя.

    Архитектура: один tool (query_transactions) + LLM с function calling.
    Агент делает один или два шага: классификация запроса → вызов инструмента →
    форматирование ответа.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        max_iterations: int = 5,
    ) -> None:
        self.client = OpenAI(
            api_key=api_key or os.environ["PROXY_API_KEY"],
            base_url=base_url or os.environ.get(
                "PROXY_BASE_URL", "https://api.proxyapi.ru/deepseek"
            ),
        )
        self.model = model or os.environ.get("LLM_MODEL", "deepseek-chat")
        self.max_iterations = max_iterations

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def _call_llm(self, messages: list[dict[str, Any]]) -> Any:
        """Один вызов LLM с retry."""
        return self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=TOOLS_SCHEMA,
            tool_choice="auto",
        )

    def run(self, user_message: str) -> AgentResponse:
        """Обрабатывает один запрос пользователя.

        Возвращает финальный ответ + полную трассу шагов.
        """
        start_time = time.time()
        trace: list[TraceStep] = []
        step_id = 0

        # Шаг: сообщение пользователя
        trace.append(TraceStep(
            step_id=step_id,
            step_type=StepType.USER_MESSAGE,
            timestamp=datetime.now(),
            content={"message": user_message},
        ))
        step_id += 1

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        tokens_in = 0
        tokens_out = 0

        try:
            for iteration in range(self.max_iterations):
                response = self._call_llm(messages)
                msg = response.choices[0].message

                tokens_in += response.usage.prompt_tokens
                tokens_out += response.usage.completion_tokens

                # Если модель решила вызвать инструмент
                if msg.tool_calls:
                    # Записываем в messages вызов модели
                    messages.append({
                        "role": "assistant",
                        "content": msg.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in msg.tool_calls
                        ],
                    })

                    # Выполняем все вызовы инструментов
                    for tc in msg.tool_calls:
                        tool_name = tc.function.name
                        try:
                            tool_args = json.loads(tc.function.arguments)
                        except json.JSONDecodeError as e:
                            tool_args = {"_parse_error": str(e)}

                        trace.append(TraceStep(
                            step_id=step_id,
                            step_type=StepType.TOOL_CALL,
                            timestamp=datetime.now(),
                            content={"name": tool_name, "parameters": tool_args},
                        ))
                        step_id += 1

                        # Выполняем инструмент
                        if tool_name in TOOL_REGISTRY:
                            try:
                                result = TOOL_REGISTRY[tool_name](**tool_args)
                                error = None
                            except Exception as e:
                                result = None
                                error = str(e)
                        else:
                            result = None
                            error = f"Неизвестный инструмент: {tool_name}"

                        trace.append(TraceStep(
                            step_id=step_id,
                            step_type=StepType.TOOL_RESULT,
                            timestamp=datetime.now(),
                            content={"result": result, "error": error},
                        ))
                        step_id += 1

                        # Добавляем результат в messages
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(
                                {"result": result, "error": error},
                                ensure_ascii=False,
                            ),
                        })

                    # Продолжаем цикл — модель сформирует финальный ответ
                    continue

                # Модель завершила без вызова инструмента — финальный ответ
                final_answer = msg.content or ""
                trace.append(TraceStep(
                    step_id=step_id,
                    step_type=StepType.FINAL_ANSWER,
                    timestamp=datetime.now(),
                    content={"answer": final_answer},
                ))

                latency = time.time() - start_time
                cost = (
                    tokens_in * PRICE_INPUT_PER_1K / 1000
                    + tokens_out * PRICE_OUTPUT_PER_1K / 1000
                )

                return AgentResponse(
                    answer=final_answer,
                    trace=trace,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    latency_s=latency,
                    cost_usd=round(cost, 6),
                )

            # Превысили max_iterations
            error_msg = f"Превышен лимит итераций ({self.max_iterations})"
            trace.append(TraceStep(
                step_id=step_id,
                step_type=StepType.ERROR,
                timestamp=datetime.now(),
                content={"error": error_msg},
            ))

            return AgentResponse(
                answer="",
                trace=trace,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_s=time.time() - start_time,
                error=error_msg,
            )

        except Exception as e:
            trace.append(TraceStep(
                step_id=step_id,
                step_type=StepType.ERROR,
                timestamp=datetime.now(),
                content={"error": str(e)},
            ))
            return AgentResponse(
                answer="",
                trace=trace,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_s=time.time() - start_time,
                error=str(e),
            )
