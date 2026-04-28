"""Генератор синтетического каталога направлений для Travel Agent."""

import csv
import random
from pathlib import Path


# Города и базовые цены
CITIES = [
    # Россия и СНГ
    {"city": "Сочи", "country": "Россия", "region": "russia", "base_hotel": 4500, "base_flight": 12000},
    {"city": "Калининград", "country": "Россия", "region": "russia", "base_hotel": 3500, "base_flight": 9000},
    {"city": "Казань", "country": "Россия", "region": "russia", "base_hotel": 3000, "base_flight": 7000},
    {"city": "Минск", "country": "Беларусь", "region": "cis", "base_hotel": 3200, "base_flight": 11000},
    {"city": "Ереван", "country": "Армения", "region": "cis", "base_hotel": 4000, "base_flight": 18000},
    {"city": "Тбилиси", "country": "Грузия", "region": "cis", "base_hotel": 4200, "base_flight": 17000},
    {"city": "Алматы", "country": "Казахстан", "region": "cis", "base_hotel": 3800, "base_flight": 16000},

    # Европа
    {"city": "Стамбул", "country": "Турция", "region": "europe", "base_hotel": 5500, "base_flight": 22000},
    {"city": "Прага", "country": "Чехия", "region": "europe", "base_hotel": 6800, "base_flight": 35000},
    {"city": "Рим", "country": "Италия", "region": "europe", "base_hotel": 9500, "base_flight": 42000},
    {"city": "Барселона", "country": "Испания", "region": "europe", "base_hotel": 8500, "base_flight": 40000},
    {"city": "Париж", "country": "Франция", "region": "europe", "base_hotel": 11000, "base_flight": 45000},
    {"city": "Будапешт", "country": "Венгрия", "region": "europe", "base_hotel": 5800, "base_flight": 33000},

    # Азия
    {"city": "Бангкок", "country": "Таиланд", "region": "asia", "base_hotel": 4500, "base_flight": 55000},
    {"city": "Пхукет", "country": "Таиланд", "region": "asia", "base_hotel": 6500, "base_flight": 58000},
    {"city": "Бали", "country": "Индонезия", "region": "asia", "base_hotel": 5500, "base_flight": 65000},
    {"city": "Дубай", "country": "ОАЭ", "region": "asia", "base_hotel": 12000, "base_flight": 35000},
    {"city": "Токио", "country": "Япония", "region": "asia", "base_hotel": 14000, "base_flight": 75000},
    {"city": "Сеул", "country": "Южная Корея", "region": "asia", "base_hotel": 11000, "base_flight": 70000},

    # Морские курорты
    {"city": "Анталия", "country": "Турция", "region": "europe", "base_hotel": 6500, "base_flight": 25000},
    {"city": "Мармарис", "country": "Турция", "region": "europe", "base_hotel": 6000, "base_flight": 24000},
    {"city": "Шарм-эль-Шейх", "country": "Египет", "region": "asia", "base_hotel": 5800, "base_flight": 30000},
    {"city": "Хургада", "country": "Египет", "region": "asia", "base_hotel": 5500, "base_flight": 28000},

    # Романтические/городские
    {"city": "Венеция", "country": "Италия", "region": "europe", "base_hotel": 12500, "base_flight": 42000},
    {"city": "Вена", "country": "Австрия", "region": "europe", "base_hotel": 9000, "base_flight": 40000},
    {"city": "Амстердам", "country": "Нидерланды", "region": "europe", "base_hotel": 11500, "base_flight": 43000},
    {"city": "Лондон", "country": "Великобритания", "region": "europe", "base_hotel": 14000, "base_flight": 48000},
    {"city": "Мадрид", "country": "Испания", "region": "europe", "base_hotel": 8000, "base_flight": 39000},

    # Экзотика
    {"city": "Мальдивы", "country": "Мальдивы", "region": "asia", "base_hotel": 25000, "base_flight": 80000},
    {"city": "Пхукет (южные пляжи)", "country": "Таиланд", "region": "asia", "base_hotel": 8000, "base_flight": 58000},
]


def generate(output: Path = Path("data/destinations.csv")) -> None:
    random.seed(42)
    rows = []
    for c in CITIES:
        # Шумим базовую цену +-20% для разнообразия
        hotel_jitter = random.uniform(0.85, 1.15)
        flight_jitter = random.uniform(0.90, 1.10)

        rows.append({
            "city": c["city"],
            "country": c["country"],
            "region": c["region"],
            "hotel_price_per_night_rub": round(c["base_hotel"] * hotel_jitter),
            "flight_price_one_way_rub": round(c["base_flight"] * flight_jitter),
            # Доступность — небольшой процент городов «забит»
            "available": random.random() > 0.05,
        })

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["city", "country", "region",
                        "hotel_price_per_night_rub",
                        "flight_price_one_way_rub", "available"],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Сгенерировано {len(rows)} направлений → {output}")


if __name__ == "__main__":
    generate()
