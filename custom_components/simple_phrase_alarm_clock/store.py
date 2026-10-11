"""Remember the last alarm this integration set on a kiosk.

This is the only state the integration keeps. It makes "delete the last
alarm" work, and it survives a restart of Home Assistant.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

STORAGE_VERSION = 1


@dataclass(frozen=True)
class LastAlarm:
    """The last alarm that was set."""

    alarm_id: str
    spoken: str  # how it is spoken back: "15:10" or "every Monday at 07:30"


class LastAlarmStore:
    """Persisted last-alarm record for one config entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[dict[str, str]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.last_alarm.{entry_id}"
        )
        self._last: LastAlarm | None = None

    async def async_load(self) -> None:
        """Load the record from disk."""
        data = await self._store.async_load()
        if data and "id" in data and "spoken" in data:
            self._last = LastAlarm(alarm_id=data["id"], spoken=data["spoken"])

    @property
    def last(self) -> LastAlarm | None:
        """Return the last alarm, if known."""
        return self._last

    async def async_set(self, alarm_id: str, spoken: str) -> None:
        """Record a newly set alarm."""
        self._last = LastAlarm(alarm_id=alarm_id, spoken=spoken)
        await self._store.async_save({"id": alarm_id, "spoken": spoken})

    async def async_clear(self) -> None:
        """Forget the last alarm (after it was deleted)."""
        self._last = None
        await self._store.async_save({})

    async def async_remove(self) -> None:
        """Delete the storage file (entry removed)."""
        await self._store.async_remove()
