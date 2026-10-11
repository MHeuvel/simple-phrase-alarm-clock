"""Client for the Kiosk Satellite Remote API.

Only what this integration needs: log in once to obtain a long-lived token,
and run the alarmSave / alarmDelete commands.

Only imports aiohttp, so it can be tested with a stub session.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10)
TOKEN_TTL_DAYS = 3650


class KioskError(Exception):
    """Base error for the kiosk client."""


class KioskConnectionError(KioskError):
    """The kiosk could not be reached."""


class KioskAuthError(KioskError):
    """The password or token was rejected."""


class KioskDuplicateError(KioskError):
    """Another alarm already rings at that time on the same days."""


class KioskNotFoundError(KioskError):
    """The alarm id does not exist."""


_NOT_FOUND_HINTS = ("not found", "no such", "unknown alarm", "does not exist", "not exist")


def _classify(message: str) -> KioskError:
    lowered = message.lower()
    if "duplicate" in lowered:
        return KioskDuplicateError(message)
    if any(hint in lowered for hint in _NOT_FOUND_HINTS):
        return KioskNotFoundError(message)
    return KioskError(message)


def base_url(host: str, port: int, ssl: bool) -> str:
    """Return the base URL of a kiosk."""
    scheme = "https" if ssl else "http"
    return f"{scheme}://{host}:{port}"


async def _request(
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    *,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
) -> Any:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        async with session.request(
            method,
            url,
            json=payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        ) as response:
            status = response.status
            text = await response.text()
    except (aiohttp.ClientError, asyncio.TimeoutError) as err:
        raise KioskConnectionError(f"Cannot reach the kiosk: {err}") from err

    _LOGGER.debug("%s %s -> %s %s", method, url, status, text[:500])

    if status in (401, 403):
        raise KioskAuthError("The kiosk rejected the credentials")

    body: Any = None
    if text:
        try:
            body = json.loads(text)
        except ValueError:
            body = None

    error_message: str | None = None
    if status >= 400:
        error_message = text or f"HTTP {status}"
    elif isinstance(body, dict):
        if body.get("ok") is False or body.get("error"):
            error_message = str(body.get("error") or body)
    if error_message is not None:
        raise _classify(error_message)

    return body


async def async_login(
    session: aiohttp.ClientSession,
    base: str,
    password: str,
    ttl_days: int = TOKEN_TTL_DAYS,
) -> str:
    """Exchange the admin password for a long-lived token.

    The password is only used here and is never stored.
    """
    body = await _request(
        session,
        "POST",
        f"{base}/api/login",
        payload={"password": password, "ttl_days": ttl_days},
    )
    token = body.get("token") if isinstance(body, dict) else None
    if not token:
        raise KioskError("The kiosk did not return a token")
    return str(token)


class KioskClient:
    """Talks to one kiosk."""

    def __init__(self, session: aiohttp.ClientSession, base: str, token: str) -> None:
        self._session = session
        self._base = base
        self._token = token

    async def async_command(self, name: str, params: dict[str, Any]) -> Any:
        """Run a command: POST /api/commands/<name> with JSON params."""
        return await _request(
            self._session,
            "POST",
            f"{self._base}/api/commands/{name}",
            token=self._token,
            payload=params,
        )

    async def async_save_alarm(
        self, alarm_id: str, hhmm: str, days: list[int] | None = None
    ) -> Any:
        """Add or change an alarm and switch it on.

        Without days it is a one-time alarm (the same minimal payload that is
        known to work: id, time, on). With days it repeats on those days
        (0 = Sunday ... 6 = Saturday).
        """
        alarm: dict[str, Any] = {"id": alarm_id, "time": hhmm, "on": True}
        if days:
            alarm["days"] = list(days)
        return await self.async_command("alarmSave", {"alarm": alarm})

    async def async_delete_alarm(self, alarm_id: str) -> Any:
        """Delete an alarm by id."""
        return await self.async_command("alarmDelete", {"id": alarm_id})

    async def async_open_alarm_list(self) -> Any:
        """Show the full-screen alarm list on the kiosk."""
        return await self.async_command("openAlarms", {})

    async def async_hide_alarm_list(self) -> Any:
        """Close the alarm list on the kiosk."""
        return await self.async_command("hideAlarms", {})
