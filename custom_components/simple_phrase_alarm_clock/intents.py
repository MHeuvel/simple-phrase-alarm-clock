"""Intent handlers: set, repeat, delete alarms and show/hide the alarm list.

Which kiosk an alarm goes to is decided by which voice satellite heard the
sentence. A typed sentence has no satellite, so it only works when exactly
one kiosk is configured.
"""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent

from .alarm import alarm_id, describe, format_time
from .const import (
    CONF_SATELLITE,
    DOMAIN,
    INTENT_DELETE,
    INTENT_HIDE_LIST,
    INTENT_SET,
    INTENT_SET_REPEATING,
    INTENT_SHOW_LIST,
    SLOT_HOURS,
    SLOT_MINUTES,
    SLOT_REPEAT_MINUTES,
    SLOT_WEEKDAY,
)
from .kiosk import (
    KioskAuthError,
    KioskDuplicateError,
    KioskError,
    KioskNotFoundError,
)
from .runtime import SpacConfigEntry

_LOGGER = logging.getLogger(__name__)

_HOURS = vol.All(vol.Coerce(int), vol.Range(min=0, max=23))
_MINUTES = vol.All(vol.Coerce(int), vol.Range(min=0, max=59))
_WEEKDAY = vol.All(vol.Coerce(int), vol.Range(min=0, max=6))


def _fail(response: intent.IntentResponse, text: str) -> intent.IntentResponse:
    """Return a spoken error response."""
    response.async_set_error(intent.IntentResponseErrorCode.FAILED_TO_HANDLE, text)
    return response


def resolve_entry(
    hass: HomeAssistant, intent_obj: intent.Intent
) -> tuple[SpacConfigEntry | None, str]:
    """Find the config entry (kiosk) that belongs to the speaking satellite.

    Returns (entry, "") or (None, spoken problem).
    """
    entries: list[SpacConfigEntry] = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if getattr(entry, "runtime_data", None) is not None
    ]
    if not entries:
        return None, "No alarm clock is set up yet."

    # The satellite entity id and/or its device id, depending on the HA version.
    satellite_id = getattr(intent_obj, "satellite_id", None)
    device_id = getattr(intent_obj, "device_id", None)

    if satellite_id:
        for entry in entries:
            if entry.data[CONF_SATELLITE] == satellite_id:
                return entry, ""
    if device_id:
        for entry in entries:
            if entry.runtime_data.device_id == device_id:
                return entry, ""
    if satellite_id or device_id:
        # A known source that has no alarm clock: never guess another room.
        return None, "This voice assistant has no alarm clock set up."

    # No source at all, for example a sentence typed in the Assist dialog.
    if len(entries) == 1:
        return entries[0], ""
    return None, "I can't tell which alarm clock you mean."


async def _handle_kiosk_error(
    hass: HomeAssistant,
    entry: SpacConfigEntry,
    response: intent.IntentResponse,
    err: KioskError,
    what: str,
) -> intent.IntentResponse:
    if isinstance(err, KioskAuthError):
        entry.async_start_reauth(hass)
        return _fail(
            response,
            "I can't log in to the alarm clock any more. "
            "Check the notification in Home Assistant.",
        )
    _LOGGER.warning("Could not %s: %s", what, err)
    return _fail(response, f"Sorry, I couldn't {what}.")


async def _save_alarm(
    intent_obj: intent.Intent,
    hours: int,
    minutes: int,
    weekday: int | None,
) -> intent.IntentResponse:
    """Shared by the one-time and the repeating alarm."""
    hass = intent_obj.hass
    response = intent_obj.create_response()

    entry, problem = resolve_entry(hass, intent_obj)
    if entry is None:
        return _fail(response, problem)

    kiosk_id = alarm_id(hours, minutes, weekday)
    hhmm = format_time(hours, minutes)
    spoken = describe(hours, minutes, weekday)
    days = None if weekday is None else [weekday]
    try:
        await entry.runtime_data.client.async_save_alarm(kiosk_id, hhmm, days)
    except KioskDuplicateError:
        return _fail(response, f"There is already an alarm for {spoken} on this clock.")
    except KioskError as err:
        return await _handle_kiosk_error(hass, entry, response, err, "set the alarm")

    await entry.runtime_data.last.async_set(kiosk_id, spoken)
    if weekday is None:
        response.async_set_speech(f"Alarm set for {spoken}.")
    else:
        response.async_set_speech(f"Repeating alarm set for {spoken}.")
    return response


class SetAlarmHandler(intent.IntentHandler):
    """Set a one-time alarm: 'set an alarm for 15 hours 10 minutes'."""

    intent_type = INTENT_SET
    slot_schema = {
        vol.Required(SLOT_HOURS): _HOURS,
        vol.Optional(SLOT_MINUTES): _MINUTES,
    }

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        """Handle the intent."""
        slots = self.async_validate_slots(intent_obj.slots)
        hours = slots[SLOT_HOURS]["value"]
        minutes = slots.get(SLOT_MINUTES, {}).get("value", 0)
        return await _save_alarm(intent_obj, hours, minutes, None)


class SetRepeatingAlarmHandler(intent.IntentHandler):
    """Set an alarm that repeats weekly on one day."""

    intent_type = INTENT_SET_REPEATING
    slot_schema = {
        vol.Required(SLOT_HOURS): _HOURS,
        vol.Optional(SLOT_REPEAT_MINUTES): _MINUTES,
        vol.Required(SLOT_WEEKDAY): _WEEKDAY,
    }

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        """Handle the intent."""
        slots = self.async_validate_slots(intent_obj.slots)
        hours = slots[SLOT_HOURS]["value"]
        minutes = slots.get(SLOT_REPEAT_MINUTES, {}).get("value", 0)
        weekday = slots[SLOT_WEEKDAY]["value"]
        return await _save_alarm(intent_obj, hours, minutes, weekday)


class DeleteAlarmHandler(intent.IntentHandler):
    """Delete an alarm: the last one set, or the one-time alarm at a given time."""

    intent_type = INTENT_DELETE
    slot_schema = {
        vol.Optional(SLOT_HOURS): _HOURS,
        vol.Optional(SLOT_MINUTES): _MINUTES,
    }

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        """Handle the intent."""
        hass = intent_obj.hass
        slots = self.async_validate_slots(intent_obj.slots)
        response = intent_obj.create_response()

        entry, problem = resolve_entry(hass, intent_obj)
        if entry is None:
            return _fail(response, problem)

        last = entry.runtime_data.last
        by_time = SLOT_HOURS in slots

        if by_time:
            hours = slots[SLOT_HOURS]["value"]
            minutes = slots.get(SLOT_MINUTES, {}).get("value", 0)
            kiosk_id = alarm_id(hours, minutes)
            hhmm = format_time(hours, minutes)
            spoken = f"Deleted the alarm for {hhmm}."
            missing = f"I couldn't find a one-time alarm for {hhmm} that I created."
        else:
            if last.last is None:
                return _fail(response, "I don't know of a recent alarm to delete.")
            kiosk_id = last.last.alarm_id
            spoken = f"Deleted the last alarm, {last.last.spoken}."
            missing = "The last alarm I set is no longer on the alarm clock."

        forget = last.last is not None and last.last.alarm_id == kiosk_id
        try:
            await entry.runtime_data.client.async_delete_alarm(kiosk_id)
        except KioskNotFoundError:
            if forget:
                await last.async_clear()
            return _fail(response, missing)
        except KioskError as err:
            return await _handle_kiosk_error(
                hass, entry, response, err, "delete the alarm"
            )

        if forget:
            await last.async_clear()
        response.async_set_speech(spoken)
        return response


async def _run_list_command(
    intent_obj: intent.Intent, open_list: bool
) -> intent.IntentResponse:
    hass = intent_obj.hass
    response = intent_obj.create_response()

    entry, problem = resolve_entry(hass, intent_obj)
    if entry is None:
        return _fail(response, problem)

    client = entry.runtime_data.client
    try:
        if open_list:
            await client.async_open_alarm_list()
        else:
            await client.async_hide_alarm_list()
    except KioskError as err:
        what = "show the alarm list" if open_list else "close the alarm list"
        return await _handle_kiosk_error(hass, entry, response, err, what)

    response.async_set_speech(
        "Showing the alarm list." if open_list else "Closing the alarm list."
    )
    return response


class ShowAlarmListHandler(intent.IntentHandler):
    """Open the alarm list on the kiosk."""

    intent_type = INTENT_SHOW_LIST

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        """Handle the intent."""
        return await _run_list_command(intent_obj, open_list=True)


class HideAlarmListHandler(intent.IntentHandler):
    """Close the alarm list on the kiosk."""

    intent_type = INTENT_HIDE_LIST

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        """Handle the intent."""
        return await _run_list_command(intent_obj, open_list=False)


def async_register_intents(hass: HomeAssistant) -> None:
    """Register all handlers."""
    for handler in (
        SetAlarmHandler(),
        SetRepeatingAlarmHandler(),
        DeleteAlarmHandler(),
        ShowAlarmListHandler(),
        HideAlarmListHandler(),
    ):
        intent.async_register(hass, handler)
