"""Инструменты Finance Agent."""

import csv
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).parent.parent.parent / "data" / "transactions.csv"


def _load_transactions() -> list[dict[str, Any]]:
    """Загружает все транзакции из CSV."""
    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"transactions.csv не найден: {DATA_PATH}. "
            "Запусти `python data/generate_transactions.py`."
        )
    with DATA_PATH.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["amount"] = float(r["amount"])
    return rows


def _resolve_period(period: str, today: date | None = None) -> tuple[date, date]:
    """Преобразует строковый период в пару (start, end). Конец — включительно."""
    if today is None:
        today = date.today()

    if period == "previous_month":
        first_day_this = today.replace(day=1)
        last_day_prev = first_day_this - timedelta(days=1)
        first_day_prev = last_day_prev.replace(day=1)
        return first_day_prev, last_day_prev

    if period == "current_month":
        first_day = today.replace(day=1)
        return first_day, today

    if period == "last_30_days":
        return today - timedelta(days=29), today

    if period == "last_year":
        return today - timedelta(days=364), today

    if period.startswith("month:"):
        # формат: month:YYYY-MM
        ym = period.split(":", 1)[1]
        year, month = map(int, ym.split("-"))
        first = date(year, month, 1)
        if month == 12:
            last = date(year, 12, 31)
        else:
            last = date(year, month + 1, 1) - timedelta(days=1)
        return first, last

    if period.startswith("range:"):
        # формат: range:YYYY-MM-DD..YYYY-MM-DD
        rng = period.split(":", 1)[1]
        s, e = rng.split("..")
        return date.fromisoformat(s), date.fromisoformat(e)

    raise ValueError(f"Неизвестный период: {period}")


def query_transactions(
    period: str,
    category: str | None = None,
    aggregation: str = "sum",
    today: date | None = None,
) -> dict[str, Any]:
    """Запрашивает транзакции за период с опциональной фильтрацией по категории.

    Параметры:
        period: один из predefined ("previous_month", "current_month",
            "last_30_days", "last_year") или "month:YYYY-MM" или
            "range:YYYY-MM-DD..YYYY-MM-DD"
        category: фильтр по категории (опционально)
        aggregation: "sum" | "count" | "by_category" | "by_merchant" | "list"
        today: эталонная "сегодня" (для воспроизводимости тестов)

    Возвращает структурированный результат.
    """
    transactions = _load_transactions()
    start, end = _resolve_period(period, today)

    filtered = [
        t for t in transactions
        if start <= date.fromisoformat(t["date"]) <= end
    ]

    if category:
        filtered = [t for t in filtered if t["category"] == category]

    if aggregation == "sum":
        total = sum(t["amount"] for t in filtered)
        return {
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "category": category,
            "total_amount": round(total, 2),
            "currency": "RUB",
            "transaction_count": len(filtered),
        }

    if aggregation == "count":
        return {
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "category": category,
            "transaction_count": len(filtered),
        }

    if aggregation == "by_category":
        buckets: dict[str, dict[str, Any]] = {}
        for t in filtered:
            c = t["category"]
            if c not in buckets:
                buckets[c] = {"category": c, "amount": 0.0, "count": 0}
            buckets[c]["amount"] += t["amount"]
            buckets[c]["count"] += 1
        for b in buckets.values():
            b["amount"] = round(b["amount"], 2)
        result = sorted(buckets.values(), key=lambda b: -b["amount"])
        return {
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "by_category": result,
            "currency": "RUB",
        }

    if aggregation == "by_merchant":
        buckets = {}
        for t in filtered:
            m = t["merchant"]
            if m not in buckets:
                buckets[m] = {"merchant": m, "amount": 0.0, "count": 0}
            buckets[m]["amount"] += t["amount"]
            buckets[m]["count"] += 1
        for b in buckets.values():
            b["amount"] = round(b["amount"], 2)
        result = sorted(buckets.values(), key=lambda b: -b["amount"])
        return {
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "by_merchant": result[:10],  # топ-10 мерчантов
            "currency": "RUB",
        }

    if aggregation == "list":
        return {
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "category": category,
            "transactions": [
                {k: v for k, v in t.items() if k != "tx_id"}
                for t in filtered[:20]  # первые 20
            ],
            "total_count": len(filtered),
        }

    raise ValueError(f"Неизвестная агрегация: {aggregation}")


# JSON-схема инструмента в формате OpenAI tools API
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "query_transactions",
            "description": (
                "Запрашивает транзакции пользователя за указанный период с "
                "опциональной фильтрацией по категории и выбором типа агрегации."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": (
                            "Период. Допустимые значения: "
                            "'previous_month', 'current_month', 'last_30_days', "
                            "'last_year', 'month:YYYY-MM' (конкретный месяц), "
                            "'range:YYYY-MM-DD..YYYY-MM-DD' (произвольный диапазон)."
                        ),
                    },
                    "category": {
                        "type": "string",
                        "description": (
                            "Категория для фильтрации: 'food', 'transport', "
                            "'entertainment', 'shopping', 'health', "
                            "'utilities', 'other'. Опционально."
                        ),
                    },
                    "aggregation": {
                        "type": "string",
                        "enum": ["sum", "count", "by_category", "by_merchant", "list"],
                        "description": (
                            "Тип агрегации. 'sum' — общая сумма; 'count' — "
                            "количество; 'by_category' — разбивка по категориям; "
                            "'by_merchant' — топ-10 мерчантов; 'list' — список "
                            "транзакций."
                        ),
                    },
                },
                "required": ["period", "aggregation"],
            },
        },
    }
]


# Соответствие имени инструмента и реальной функции
TOOL_REGISTRY = {
    "query_transactions": query_transactions,
}
