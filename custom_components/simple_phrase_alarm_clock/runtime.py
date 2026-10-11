"""Runtime data attached to each config entry."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry

from .kiosk import KioskClient
from .store import LastAlarmStore


@dataclass
class SpacData:
    """Everything one config entry needs while it is loaded."""

    client: KioskClient
    last: LastAlarmStore
    device_id: str | None  # the satellite's device in the device registry


type SpacConfigEntry = ConfigEntry[SpacData]
