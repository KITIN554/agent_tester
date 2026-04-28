"""Smoke-тест Travel Agent: проигрываем сценарий «удачного» бронирования.

Проверяем end-to-end: от запроса до подтверждённой брони с booking_id.
"""

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

from systems.travel_agent.agent import TravelAgent

load_dotenv()
console = Console()


SCRIPTED_CONVERSATION = [
    "Хочу куда-нибудь в Европу на неделю в июне 2026, бюджет до 200 тысяч рублей",
    "Поеду один",
    "Беру первый вариант",
    "С 10 по 17 июня 2026",
    "Иван Петров, ivan.petrov@example.com",
    "Да, согласен на обработку персональных данных",
]


def main() -> None:
    agent = TravelAgent()
    agent.start_session()

    for i, user_msg in enumerate(SCRIPTED_CONVERSATION):
        if agent.is_done():
            console.print(f"[yellow]Диалог завершён на ходе {i}, дальше не идём")
            break

        console.rule(f"[bold]Ход {i + 1}: {user_msg}")
        response = agent.send(user_msg)
        console.print(Panel(response.answer or "(пусто)", title="Ответ агента"))

        console.print(f"[dim]Состояние: {response.final_state}")
        console.print(f"[dim]Шагов в трассе: {len(response.trace)}")
        console.print(f"[dim]Токены: in={response.tokens_in}, out={response.tokens_out}")

        if response.error:
            console.print(f"[red]Ошибка: {response.error}")
            break

    console.rule("[bold green]ИТОГ")
    console.print(f"Финальное состояние: {agent.dialog.state.value}")
    console.print(f"Booking ID: {agent.dialog.context.booking_id}")
    console.print(f"Всего шагов в трассе: {len(agent.trace)}")
    console.print(f"Всего токенов: in={agent.tokens_in}, out={agent.tokens_out}")


if __name__ == "__main__":
    main()
