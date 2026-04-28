"""Smoke-тест: гарантирует, что главные модули импортируются без ошибок."""


def test_imports() -> None:
    """Импортируем тестируемые системы.

    Модули `tester/*` пока не существуют — их импорты появятся в следующих тасках.
    """
    from systems.finance_agent.agent import FinanceAgent  # noqa: F401
    from systems.travel_agent.agent import TravelAgent  # noqa: F401
