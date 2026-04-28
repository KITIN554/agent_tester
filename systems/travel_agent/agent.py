"""Travel Agent — многошаговый агент бронирования путешествий.

В отличие от Finance Agent работает в режиме диалога: получает
сообщения пользователя по одному, поддерживает состояние между ними.
"""

import json
import os
import time
from datetime import datetime
from typing import Any

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from .prompts import SYSTEM_PROMPT
from .state import DialogState, DialogStateData, TERMINAL_STATES
from .tools import TOOL_REGISTRY, TOOLS_SCHEMA
from .types import AgentResponse, StepType, TraceStep

PRICE_INPUT_PER_1K = 0.0004
PRICE_OUTPUT_PER_1K = 0.0020


class TravelAgent:
    """Многошаговый агент бронирования.

    Использование:
        agent = TravelAgent()
        agent.start_session()
        while not agent.is_done():
            user_msg = input("> ")
            response = agent.send(user_msg)
            print(response.answer)
        # В конце response.final_state, response.booking_id
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        max_iterations_per_turn: int = 8,
        max_turns: int = 25,
    ) -> None:
        self.client = OpenAI(
            api_key=api_key or os.environ["PROXY_API_KEY"],
            base_url=base_url or os.environ.get(
                "PROXY_BASE_URL", "https://api.proxyapi.ru/openrouter/v1"
            ),
        )
        self.model = model or os.environ.get("LLM_MODEL", "mistralai/mistral-medium-3.1")
        self.max_iterations_per_turn = max_iterations_per_turn
        self.max_turns = max_turns

        # Состояние сессии
        self.dialog: DialogStateData = DialogStateData()
        self.messages: list[dict[str, Any]] = []
        self.trace: list[TraceStep] = []
        self.step_id: int = 0
        self.tokens_in: int = 0
        self.tokens_out: int = 0
        self.session_start_time: float | None = None

    def start_session(self) -> None:
        """Сбрасывает состояние и инициализирует новую сессию."""
        self.dialog = DialogStateData()
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.trace = []
        self.step_id = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.session_start_time = time.time()

    def is_done(self) -> bool:
        """Достигнуто ли терминальное состояние."""
        return self.dialog.state in TERMINAL_STATES or self.dialog.turn_count >= self.max_turns

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def _call_llm(self) -> Any:
        return self.client.chat.completions.create(
            model=self.model,
            messages=self.messages,
            tools=TOOLS_SCHEMA,
            tool_choice="auto",
        )

    def _add_trace(self, step_type: StepType, content: dict[str, Any]) -> None:
        self.trace.append(TraceStep(
            step_id=self.step_id,
            step_type=step_type,
            timestamp=datetime.now(),
            content=content,
        ))
        self.step_id += 1

    def send(self, user_message: str) -> AgentResponse:
        """Один ход диалога.

        Принимает сообщение пользователя, возвращает ответ агента +
        обновлённую трассу. Состояние накапливается в self.dialog.
        """
        if self.session_start_time is None:
            self.start_session()

        if self.is_done():
            return self._build_response("Диалог завершён.", final=True)

        self.dialog.turn_count += 1
        self._add_trace(StepType.USER_MESSAGE, {"message": user_message})
        self.messages.append({"role": "user", "content": user_message})

        try:
            for _iteration in range(self.max_iterations_per_turn):
                response = self._call_llm()
                msg = response.choices[0].message

                self.tokens_in += response.usage.prompt_tokens
                self.tokens_out += response.usage.completion_tokens

                if msg.tool_calls:
                    # Записываем вызов модели в историю сообщений
                    self.messages.append({
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

                    for tc in msg.tool_calls:
                        tool_name = tc.function.name
                        try:
                            tool_args = json.loads(tc.function.arguments)
                        except json.JSONDecodeError as e:
                            tool_args = {"_parse_error": str(e)}

                        self._add_trace(
                            StepType.TOOL_CALL,
                            {"name": tool_name, "parameters": tool_args},
                        )

                        # Выполнение
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

                        self._add_trace(
                            StepType.TOOL_RESULT,
                            {"name": tool_name, "result": result, "error": error},
                        )

                        # Обновляем контекст диалога по факту вызовов
                        self._update_state_from_tool(tool_name, tool_args, result)

                        self.messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(
                                {"result": result, "error": error},
                                ensure_ascii=False,
                            ),
                        })
                    # Продолжаем — модель сформирует следующий шаг
                    continue

                # Финальный ответ модели в этом ходе
                final_text = msg.content or ""
                self.messages.append({"role": "assistant", "content": final_text})
                self._add_trace(StepType.AGENT_MESSAGE, {"message": final_text})

                # Если бронь оформлена — терминал
                if self.dialog.context.booking_id:
                    self.dialog.state = DialogState.CONFIRMED

                return self._build_response(final_text)

            # Превысили лимит итераций внутри одного хода
            error_msg = "Превышен лимит итераций в ходе"
            self._add_trace(StepType.ERROR, {"error": error_msg})
            self.dialog.state = DialogState.ERROR
            return self._build_response(error_msg, error=error_msg)

        except Exception as e:
            self._add_trace(StepType.ERROR, {"error": str(e)})
            self.dialog.state = DialogState.ERROR
            return self._build_response("", error=str(e))

    def _update_state_from_tool(
        self, tool_name: str, args: dict, result: Any
    ) -> None:
        """Обновляет состояние диалога на основе вызова инструмента."""
        ctx = self.dialog.context

        if tool_name == "search_destinations" and isinstance(result, dict):
            ctx.shown_options = result.get("options", [])
            self.dialog.state = DialogState.SHOWING_OPTIONS

        elif tool_name == "calculate_price" and isinstance(result, dict):
            if result.get("success"):
                ctx.selected_option_id = result["option_id"]
                ctx.selected_total_rub = result["total_price_rub"]
                ctx.start_date = result["start_date"]
                ctx.end_date = result["end_date"]
                ctx.guests_count = result["guests"]

        elif tool_name == "validate_pii":
            if args:
                ctx.first_name = args.get("first_name")
                ctx.last_name = args.get("last_name")
                ctx.email = args.get("email")
            self.dialog.state = DialogState.AWAITING_CONSENT

        elif tool_name == "request_pii_consent":
            ctx.pii_consent_given = True
            self.dialog.state = DialogState.CREATING_BOOKING

        elif tool_name == "create_booking" and isinstance(result, dict):
            if result.get("success"):
                ctx.booking_id = result["booking_id"]
                self.dialog.state = DialogState.CONFIRMED

    def _build_response(
        self,
        answer: str,
        final: bool = False,
        error: str | None = None,
    ) -> AgentResponse:
        latency = time.time() - (self.session_start_time or time.time())
        cost = (
            self.tokens_in * PRICE_INPUT_PER_1K / 1000
            + self.tokens_out * PRICE_OUTPUT_PER_1K / 1000
        )
        return AgentResponse(
            answer=answer,
            trace=list(self.trace),
            final_state=self.dialog.state.value,
            booking_id=self.dialog.context.booking_id,
            tokens_in=self.tokens_in,
            tokens_out=self.tokens_out,
            latency_s=round(latency, 2),
            cost_usd=round(cost, 6),
            turn_count=self.dialog.turn_count,
            error=error,
        )
