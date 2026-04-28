"""Инструменты Travel Agent."""

import csv
import re
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).parent.parent.parent / "data" / "destinations.csv"


def _load_destinations() -> list[dict[str, Any]]:
    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"destinations.csv не найден: {DATA_PATH}. "
            "Запусти `python data/generate_destinations.py`."
        )
    with DATA_PATH.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["hotel_price_per_night_rub"] = int(r["hotel_price_per_night_rub"])
        r["flight_price_one_way_rub"] = int(r["flight_price_one_way_rub"])
        r["available"] = r["available"].lower() == "true"
    return rows


# =============== ИНСТРУМЕНТЫ ===============

def search_destinations(
    region: str | None = None,
    max_budget_rub: int | None = None,
    duration_days: int | None = None,
    guests: int = 1,
    top_n: int = 5,
) -> dict[str, Any]:
    """Ищет варианты направлений по фильтрам.

    Возвращает топ-N вариантов с расчётной полной стоимостью.
    Полная стоимость = (отель × ночей × гостей) + (перелёт × гостей × 2).
    """
    all_dest = _load_destinations()
    candidates = [d for d in all_dest if d["available"]]

    if region:
        candidates = [d for d in candidates if d["region"] == region]

    if not candidates:
        return {"options": [], "total_count": 0, "filters_applied": {"region": region, "max_budget_rub": max_budget_rub}}

    nights = (duration_days or 7) - 1 if duration_days else 6
    nights = max(nights, 1)

    enriched = []
    for d in candidates:
        hotel_total = d["hotel_price_per_night_rub"] * nights * guests
        flight_total = d["flight_price_one_way_rub"] * 2 * guests   # туда-обратно
        total = hotel_total + flight_total
        enriched.append({
            "option_id": f"OPT_{d['city'].upper().replace(' ', '_')}",
            "city": d["city"],
            "country": d["country"],
            "region": d["region"],
            "hotel_price_per_night_rub": d["hotel_price_per_night_rub"],
            "flight_price_one_way_rub": d["flight_price_one_way_rub"],
            "nights": nights,
            "guests": guests,
            "total_price_rub": total,
        })

    if max_budget_rub is not None:
        enriched = [e for e in enriched if e["total_price_rub"] <= max_budget_rub]

    enriched.sort(key=lambda x: x["total_price_rub"])
    options = enriched[:top_n]

    return {
        "options": options,
        "total_count": len(enriched),
        "filters_applied": {
            "region": region,
            "max_budget_rub": max_budget_rub,
            "duration_days": duration_days,
            "guests": guests,
        },
    }


def check_availability(option_id: str, start_date: str, end_date: str) -> dict[str, Any]:
    """Проверяет доступность конкретного варианта на даты."""
    all_dest = _load_destinations()

    # Извлекаем город из option_id
    city_token = option_id.replace("OPT_", "").replace("_", " ")
    matching = [
        d for d in all_dest
        if d["city"].upper().replace(" ", " ") == city_token.upper()
        or d["city"].upper() == city_token.upper()
    ]
    if not matching:
        return {"available": False, "reason": "Вариант не найден"}

    d = matching[0]
    if not d["available"]:
        return {"available": False, "reason": "Направление временно недоступно"}

    # Простая проверка дат
    try:
        s = date.fromisoformat(start_date)
        e = date.fromisoformat(end_date)
    except ValueError as exc:
        return {"available": False, "reason": f"Неверный формат даты: {exc}"}

    if s >= e:
        return {"available": False, "reason": "Дата отъезда должна быть позже даты заезда"}

    if s < date.today():
        return {"available": False, "reason": "Нельзя бронировать на прошедшую дату"}

    return {
        "available": True,
        "option_id": option_id,
        "city": d["city"],
        "start_date": start_date,
        "end_date": end_date,
        "nights": (e - s).days,
    }


def calculate_price(
    option_id: str, start_date: str, end_date: str, guests: int = 1
) -> dict[str, Any]:
    """Рассчитывает итоговую стоимость для конкретных дат и гостей."""
    avail = check_availability(option_id, start_date, end_date)
    if not avail.get("available"):
        return {"success": False, "reason": avail.get("reason")}

    all_dest = _load_destinations()
    city_token = option_id.replace("OPT_", "").replace("_", " ").upper()
    d = next((x for x in all_dest if x["city"].upper() == city_token), None)
    if not d:
        return {"success": False, "reason": "Вариант не найден"}

    nights = avail["nights"]
    hotel_total = d["hotel_price_per_night_rub"] * nights * guests
    flight_total = d["flight_price_one_way_rub"] * 2 * guests
    total = hotel_total + flight_total

    return {
        "success": True,
        "option_id": option_id,
        "city": d["city"],
        "start_date": start_date,
        "end_date": end_date,
        "nights": nights,
        "guests": guests,
        "hotel_total_rub": hotel_total,
        "flight_total_rub": flight_total,
        "total_price_rub": total,
        "currency": "RUB",
    }


_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
_NAME_RE = re.compile(r"^[А-Яа-яA-Za-z\- ]{2,40}$")


def validate_pii(first_name: str, last_name: str, email: str) -> dict[str, Any]:
    """Валидирует ПДн пользователя по формату.

    Не проверяет реальное существование email — только синтаксис.
    """
    errors = []
    if not _NAME_RE.match(first_name.strip()):
        errors.append("Имя содержит недопустимые символы или слишком короткое")
    if not _NAME_RE.match(last_name.strip()):
        errors.append("Фамилия содержит недопустимые символы или слишком короткая")
    if not _EMAIL_RE.match(email.strip()):
        errors.append("Email имеет неверный формат")

    if errors:
        return {"valid": False, "errors": errors}

    return {"valid": True}


def request_pii_consent(purpose: str) -> dict[str, Any]:
    """Регистрирует факт запроса согласия на обработку ПДн.

    Это служебный инструмент: он не получает согласие сам, а формализует,
    что агент явно запросил согласие у пользователя. Подтверждение приходит
    отдельной репликой пользователя, которую агент анализирует.
    """
    return {
        "consent_request_id": f"CRQ_{uuid.uuid4().hex[:12].upper()}",
        "purpose": purpose,
        "status": "requested",
        "policy_version": "v1.0",
    }


def create_booking(
    option_id: str,
    start_date: str,
    end_date: str,
    guests: int,
    first_name: str,
    last_name: str,
    email: str,
    consent_request_id: str,
) -> dict[str, Any]:
    """Создаёт бронь и возвращает booking_id.

    Перед созданием обязательно требует наличия consent_request_id —
    без согласия на обработку ПДн бронь не оформляется.
    """
    if not consent_request_id or not consent_request_id.startswith("CRQ_"):
        return {
            "success": False,
            "error": "Отсутствует подтверждение запроса согласия на обработку ПДн",
        }

    # Повторно валидируем
    pii = validate_pii(first_name, last_name, email)
    if not pii["valid"]:
        return {"success": False, "error": "Невалидные ПДн", "details": pii["errors"]}

    # Проверяем доступность ещё раз
    avail = check_availability(option_id, start_date, end_date)
    if not avail.get("available"):
        return {"success": False, "error": avail.get("reason")}

    pricing = calculate_price(option_id, start_date, end_date, guests)
    if not pricing.get("success"):
        return {"success": False, "error": "Ошибка расчёта стоимости"}

    booking_id = f"BK_{uuid.uuid4().hex[:10].upper()}"

    return {
        "success": True,
        "booking_id": booking_id,
        "option_id": option_id,
        "city": pricing["city"],
        "start_date": start_date,
        "end_date": end_date,
        "guests": guests,
        "total_price_rub": pricing["total_price_rub"],
        "passenger": f"{first_name} {last_name}",
        "email": email,
        "created_at": datetime.now().isoformat(),
        "status": "confirmed",
    }


# =============== JSON-СХЕМА (OpenAI tools API) ===============

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "search_destinations",
            "description": (
                "Ищет варианты направлений по фильтрам. Возвращает список "
                "вариантов с расчётной стоимостью и option_id для дальнейших "
                "операций. Используй когда пользователь описал предпочтения "
                "и нужно показать ему варианты."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "region": {
                        "type": "string",
                        "enum": ["russia", "cis", "europe", "asia"],
                        "description": "Регион поиска. Опционально.",
                    },
                    "max_budget_rub": {
                        "type": "integer",
                        "description": "Максимальный бюджет на всю поездку в рублях.",
                    },
                    "duration_days": {
                        "type": "integer",
                        "description": "Длительность поездки в днях.",
                    },
                    "guests": {
                        "type": "integer",
                        "description": "Количество гостей. По умолчанию 1.",
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Сколько вариантов вернуть (по умолчанию 5).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": (
                "Проверяет доступность конкретного варианта на указанные даты. "
                "Используй после того как пользователь выбрал option_id и "
                "сообщил даты."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "option_id": {"type": "string"},
                    "start_date": {"type": "string", "description": "ISO формат YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "ISO формат YYYY-MM-DD"},
                },
                "required": ["option_id", "start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_price",
            "description": (
                "Рассчитывает точную стоимость для конкретных дат и числа гостей. "
                "Возвращает разбивку: отель + перелёты."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "option_id": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "guests": {"type": "integer"},
                },
                "required": ["option_id", "start_date", "end_date", "guests"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "validate_pii",
            "description": (
                "Валидирует ПДн пользователя (имя, фамилию, email) по формату. "
                "Используй сразу после получения этих данных, до запроса согласия."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "first_name": {"type": "string"},
                    "last_name": {"type": "string"},
                    "email": {"type": "string"},
                },
                "required": ["first_name", "last_name", "email"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_pii_consent",
            "description": (
                "Регистрирует факт запроса согласия на обработку персональных "
                "данных. Возвращает consent_request_id, который ОБЯЗАТЕЛЕН для "
                "create_booking. Используй ТОЛЬКО ПОСЛЕ того как пользователь "
                "явно дал согласие в реплике."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "purpose": {
                        "type": "string",
                        "description": "Цель обработки ПДн.",
                    },
                },
                "required": ["purpose"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_booking",
            "description": (
                "Создаёт бронь. Требует: option_id, даты, гости, ПДн "
                "и consent_request_id (полученный из request_pii_consent после "
                "явного согласия пользователя). Возвращает booking_id."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "option_id": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "guests": {"type": "integer"},
                    "first_name": {"type": "string"},
                    "last_name": {"type": "string"},
                    "email": {"type": "string"},
                    "consent_request_id": {"type": "string"},
                },
                "required": [
                    "option_id", "start_date", "end_date", "guests",
                    "first_name", "last_name", "email", "consent_request_id",
                ],
            },
        },
    },
]


TOOL_REGISTRY = {
    "search_destinations": search_destinations,
    "check_availability": check_availability,
    "calculate_price": calculate_price,
    "validate_pii": validate_pii,
    "request_pii_consent": request_pii_consent,
    "create_booking": create_booking,
}
