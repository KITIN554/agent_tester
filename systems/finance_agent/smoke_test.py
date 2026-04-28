"""Smoke-тест Finance Agent. Запускает три типичных запроса и печатает результат.

Используется только для ручной проверки на этапе разработки.
"""

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

from systems.finance_agent.agent import FinanceAgent

load_dotenv()
console = Console()


def run_demo(agent: FinanceAgent, message: str) -> None:
    console.rule(f"[bold]Запрос: {message}")
    response = agent.run(message)

    console.print(Panel(response.answer or "(пусто)", title="Ответ агента"))

    console.print(f"[dim]Шагов в трассе: {len(response.trace)}")
    console.print(f"[dim]Токены: вход={response.tokens_in}, выход={response.tokens_out}")
    console.print(f"[dim]Latency: {response.latency_s:.2f} с")
    console.print(f"[dim]Стоимость: ${response.cost_usd}")

    if response.error:
        console.print(f"[red]Ошибка: {response.error}")

    console.print("\n[bold]Трасса:")
    for step in response.trace:
        console.print(f"  [{step.step_id}] {step.step_type.value}: {step.content}")


def main() -> None:
    agent = FinanceAgent()

    queries = [
        "Сколько я потратил в прошлом месяце?",
        "На что больше всего ушло денег за последний месяц?",
        "Сколько потратил на еду за прошлый месяц?",
    ]

    for q in queries:
        run_demo(agent, q)
        console.print()


if __name__ == "__main__":
    main()
