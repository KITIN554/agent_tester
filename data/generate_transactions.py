"""Генератор синтетических транзакций для Finance Agent.

Создаёт CSV-файл с 1000 записями за последние 12 месяцев.
Никаких реальных данных пользователей.
"""

import csv
import random
from datetime import date, timedelta
from pathlib import Path

from faker import Faker

# Фиксируем seed для воспроизводимости
random.seed(42)
fake = Faker("ru_RU")
fake.seed_instance(42)

CATEGORIES = {
    "food": {
        "merchants": ["Пятёрочка", "ВкусВилл", "Перекрёсток", "Магнит", "Лента", "Азбука Вкуса"],
        "amount_range": (200, 5000),
        "weight": 30,
    },
    "transport": {
        "merchants": ["Яндекс.Такси", "Uber", "Метро", "СитиМобил", "АЗС Лукойл", "АЗС Газпром"],
        "amount_range": (100, 3000),
        "weight": 15,
    },
    "entertainment": {
        "merchants": ["Кинопоиск", "Театр.ру", "Okko", "Wink", "Боулинг", "Ресторан"],
        "amount_range": (300, 4000),
        "weight": 12,
    },
    "shopping": {
        "merchants": ["Wildberries", "Ozon", "Lamoda", "Спортмастер", "DNS", "М.Видео"],
        "amount_range": (500, 30000),
        "weight": 20,
    },
    "health": {
        "merchants": ["Аптека Ригла", "Аптека 36.6", "Здоровье плюс", "СМ-Клиника", "Медицина"],
        "amount_range": (300, 8000),
        "weight": 8,
    },
    "utilities": {
        "merchants": ["ЖКУ", "Мосэнергосбыт", "Мобильный оператор", "Интернет-провайдер"],
        "amount_range": (500, 6000),
        "weight": 10,
    },
    "other": {
        "merchants": ["Перевод", "Снятие наличных", "Подписка"],
        "amount_range": (100, 10000),
        "weight": 5,
    },
}


def generate(n: int = 1000, output: Path = Path("data/transactions.csv")) -> None:
    today = date.today()
    one_year_ago = today - timedelta(days=365)

    weights = [c["weight"] for c in CATEGORIES.values()]
    cat_names = list(CATEGORIES.keys())

    rows = []
    for i in range(n):
        category = random.choices(cat_names, weights=weights)[0]
        cat = CATEGORIES[category]
        merchant = random.choice(cat["merchants"])
        lo, hi = cat["amount_range"]
        amount = round(random.uniform(lo, hi), 2)

        days_ago = random.randint(0, 365)
        tx_date = today - timedelta(days=days_ago)

        rows.append({
            "tx_id": f"TX{i + 1:06d}",
            "date": tx_date.isoformat(),
            "amount": amount,
            "currency": "RUB",
            "category": category,
            "merchant": merchant,
            "description": f"Покупка в {merchant}",
        })

    rows.sort(key=lambda r: r["date"])

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["tx_id", "date", "amount", "currency", "category", "merchant", "description"],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Сгенерировано {n} транзакций → {output}")
    print(f"Период: {one_year_ago} … {today}")
    print("Распределение по категориям:")
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    for cat, count in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {cat:15s} {count:4d}")


if __name__ == "__main__":
    generate()
