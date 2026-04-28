"""Конечный автомат сценария бронирования."""

from enum import Enum

from pydantic import BaseModel, Field


class DialogState(str, Enum):
    """Состояния автомата сценария бронирования."""

    INITIAL = "initial"                          # старт диалога
    COLLECTING_DESTINATION = "collecting_destination"   # собираем направление
    COLLECTING_DATES = "collecting_dates"        # собираем даты
    COLLECTING_GUESTS = "collecting_guests"      # количество гостей
    SHOWING_OPTIONS = "showing_options"          # показали варианты, ждём выбора
    COLLECTING_PII = "collecting_pii"            # собираем имя/фамилию/email
    AWAITING_CONSENT = "awaiting_consent"        # ждём согласия на обработку ПДн
    CREATING_BOOKING = "creating_booking"        # запись брони
    CONFIRMED = "confirmed"                      # терминал — успех
    CANCELLED = "cancelled"                      # терминал — пользователь отказался
    OUT_OF_SCOPE = "out_of_scope"                # терминал — вне компетенции
    ERROR = "error"                              # терминал — ошибка


TERMINAL_STATES = {
    DialogState.CONFIRMED,
    DialogState.CANCELLED,
    DialogState.OUT_OF_SCOPE,
    DialogState.ERROR,
}


class TripContext(BaseModel):
    """Накопленные данные о поездке (рабочая память агента)."""

    # Направление и параметры
    destination_city: str | None = None
    destination_country: str | None = None
    region_filter: str | None = None       # "europe", "asia", "russia", "cis"
    budget_rub: int | None = None
    duration_days: int | None = None

    # Даты
    start_date: str | None = None          # ISO
    end_date: str | None = None            # ISO

    # Гости
    guests_count: int | None = None

    # Выбранный вариант
    selected_option_id: str | None = None
    selected_total_rub: int | None = None

    # Персональные данные
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    pii_consent_given: bool = False

    # Финальное подтверждение
    booking_id: str | None = None

    # Список вариантов, которые показали пользователю
    shown_options: list[dict] = Field(default_factory=list)


class DialogStateData(BaseModel):
    """Полное состояние диалога."""

    state: DialogState = DialogState.INITIAL
    context: TripContext = Field(default_factory=TripContext)
    turn_count: int = 0
