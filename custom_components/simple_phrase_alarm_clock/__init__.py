"""Simple Phrase alarm clock.

Set and delete alarms on a Kiosk Satellite by voice, with a small fixed set of
phrases that works with the Speech-to-Phrase add-on.
"""

from __future__ import annotations

import asyncio
import logging

from homeassistant.components import persistent_notification
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    CONF_SSL,
    CONF_TOKEN,
    CONF_VERIFY_SSL,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    config_validation as cv,
    entity_registry as er,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_MANAGE_S2P,
    CONF_S2P_ADDON,
    CONF_SATELLITE,
    DEFAULT_S2P_ADDON,
    DOMAIN,
    LANGUAGE,
    NOTIFICATION_ID,
    S2P_SHARE_ROOT,
)
from .files import remove_generated, sync_share_sentences, write_config_sentences
from .intents import async_register_intents
from .kiosk import KioskClient, base_url
from .runtime import SpacConfigEntry, SpacData
from .sentences import phrase_count
from .store import LastAlarmStore

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the intent handlers once."""
    hass.data[DOMAIN] = {"sync_lock": asyncio.Lock()}
    async_register_intents(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: SpacConfigEntry) -> bool:
    """Set up one kiosk."""
    session = async_get_clientsession(hass, verify_ssl=entry.data[CONF_VERIFY_SSL])
    client = KioskClient(
        session,
        base_url(entry.data[CONF_HOST], entry.data[CONF_PORT], entry.data[CONF_SSL]),
        entry.data[CONF_TOKEN],
    )
    last = LastAlarmStore(hass, entry.entry_id)
    await last.async_load()

    entry.runtime_data = SpacData(
        client=client,
        last=last,
        device_id=_satellite_device_id(hass, entry),
    )

    await _async_sync_sentences(hass, entry)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SpacConfigEntry) -> bool:
    """Unload a kiosk. There are no platforms to unload."""
    return True


async def async_remove_entry(hass: HomeAssistant, entry: SpacConfigEntry) -> None:
    """Clean up when a kiosk is removed."""
    await LastAlarmStore(hass, entry.entry_id).async_remove()

    remaining = [
        other
        for other in hass.config_entries.async_entries(DOMAIN)
        if other.entry_id != entry.entry_id
    ]
    if remaining:
        return

    # Last kiosk gone: remove the sentences we generated.
    manage_share, addon = _share_options(entry)
    config_changed, share_changed = await hass.async_add_executor_job(
        remove_generated, hass.config.config_dir, LANGUAGE, S2P_SHARE_ROOT, manage_share
    )
    if config_changed:
        await _async_reload_conversation(hass)
    if share_changed:
        _notify_manual_restart(hass, addon, removed=True)


def _satellite_device_id(hass: HomeAssistant, entry: SpacConfigEntry) -> str | None:
    """Read (never modify) the satellite's device id, used for routing."""
    satellite = er.async_get(hass).async_get(entry.data[CONF_SATELLITE])
    if satellite is None or satellite.device_id is None:
        _LOGGER.warning(
            "Satellite %s has no device; routing uses the entity id only",
            entry.data[CONF_SATELLITE],
        )
        return None
    return satellite.device_id


def _share_options(entry: SpacConfigEntry) -> tuple[bool, str]:
    """Return (manage Speech-to-Phrase, add-on slug) from an entry's options."""
    return (
        entry.options.get(CONF_MANAGE_S2P, True),
        entry.options.get(CONF_S2P_ADDON, DEFAULT_S2P_ADDON),
    )


async def _async_sync_sentences(hass: HomeAssistant, entry: SpacConfigEntry) -> None:
    """Write the sentence files, and retrain Speech-to-Phrase if they changed.

    Idempotent: when nothing changed, nothing is written, reloaded or restarted.
    """
    # Options live on every entry; the first entry decides for everyone.
    first = hass.config_entries.async_entries(DOMAIN)[0]
    manage_share, addon = _share_options(first)

    async with hass.data[DOMAIN]["sync_lock"]:
        try:
            config_changed = await hass.async_add_executor_job(
                write_config_sentences, hass.config.config_dir, LANGUAGE
            )
        except OSError as err:
            _LOGGER.error("Could not write the Assist sentence file: %s", err)
            config_changed = False

        if config_changed:
            await _async_reload_conversation(hass)

        share_changed = False
        if manage_share:
            try:
                share_changed = await hass.async_add_executor_job(
                    sync_share_sentences, LANGUAGE
                )
            except OSError as err:
                _LOGGER.error("Could not write the Speech-to-Phrase file: %s", err)

    if share_changed:
        _LOGGER.info(
            "Speech-to-Phrase sentences changed (%s phrases); retraining",
            phrase_count(),
        )
        entry.async_create_background_task(
            hass, _async_retrain(hass, addon), name=f"{DOMAIN}_retrain"
        )


async def _async_reload_conversation(hass: HomeAssistant) -> None:
    """Make Assist pick up the new custom sentence file."""
    try:
        await hass.services.async_call(
            "conversation", "reload", {"language": LANGUAGE}, blocking=True
        )
    except Exception:  # noqa: BLE001 - never fail setup over a reload
        _LOGGER.exception("Could not reload the conversation sentences")


async def _async_retrain(hass: HomeAssistant, addon: str) -> None:
    """Restart the Speech-to-Phrase add-on so it trains on the new sentences."""
    if not hass.services.has_service("hassio", "addon_restart"):
        _notify_manual_restart(hass, addon)
        return
    try:
        await hass.services.async_call(
            "hassio", "addon_restart", {"addon": addon}, blocking=True
        )
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Could not restart the add-on %s", addon)
        _notify_manual_restart(hass, addon)
        return
    persistent_notification.async_create(
        hass,
        "The alarm phrases changed, so the Speech-to-Phrase add-on was restarted "
        "to learn them. Training can take a while; spoken alarm commands work "
        "again once the add-on is ready.",
        title="Simple Phrase alarm clock",
        notification_id=NOTIFICATION_ID,
    )


def _notify_manual_restart(
    hass: HomeAssistant, addon: str, removed: bool = False
) -> None:
    action = "removed" if removed else "updated"
    persistent_notification.async_create(
        hass,
        f"The alarm phrases were {action} for Speech-to-Phrase. Restart the "
        f"Speech-to-Phrase add-on (slug: {addon}) so it trains on them.",
        title="Simple Phrase alarm clock",
        notification_id=NOTIFICATION_ID,
    )
