"""Pure helpers for alarm ids, weekdays and wording (no Home Assistant imports)."""

from __future__ import annotations

from .const import ID_PREFIX

# The kiosk numbers weekdays 0 = Sunday ... 6 = Saturday.
WEEKDAY_NAMES = {
    0: "Sunday",
    1: "Monday",
    2: "Tuesday",
    3: "Wednesday",
    4: "Thursday",
    5: "Friday",
    6: "Saturday",
}


def alarm_id(hours: int, minutes: int, weekday: int | None = None) -> str:
    """Return the deterministic kiosk alarm id.

    One-time alarm: spac-1510. Repeating on one weekday: spac-0730-1.
    """
    _check(hours, minutes)
    base = f"{ID_PREFIX}-{int(hours):02d}{int(minutes):02d}"
    if weekday is None:
        return base
    _check_weekday(weekday)
    return f"{base}-{int(weekday)}"


def format_time(hours: int, minutes: int) -> str:
    """Return HH:MM, zero padded, as the kiosk API expects."""
    _check(hours, minutes)
    return f"{int(hours):02d}:{int(minutes):02d}"


def describe(hours: int, minutes: int, weekday: int | None = None) -> str:
    """Return how an alarm is spoken: '15:10' or 'every Monday at 07:30'."""
    hhmm = format_time(hours, minutes)
    if weekday is None:
        return hhmm
    _check_weekday(weekday)
    return f"every {WEEKDAY_NAMES[int(weekday)]} at {hhmm}"


def is_ours(alarm_id_value: str) -> bool:
    """Return True if an alarm id was created by this integration."""
    return alarm_id_value.startswith(f"{ID_PREFIX}-")


def _check(hours: int, minutes: int) -> None:
    if not 0 <= int(hours) <= 23:
        raise ValueError(f"hours out of range: {hours}")
    if not 0 <= int(minutes) <= 59:
        raise ValueError(f"minutes out of range: {minutes}")


def _check_weekday(weekday: int) -> None:
    if int(weekday) not in WEEKDAY_NAMES:
        raise ValueError(f"weekday out of range: {weekday}")
