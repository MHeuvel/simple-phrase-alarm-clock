"""Config flow for Simple Phrase alarm clock.

The admin password is typed once, exchanged for a long-lived token and then
discarded. Only the token is stored.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SSL,
    CONF_TOKEN,
    CONF_VERIFY_SSL,
)
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_MANAGE_S2P,
    CONF_S2P_ADDON,
    CONF_SATELLITE,
    DEFAULT_PORT,
    DEFAULT_S2P_ADDON,
    DOMAIN,
)
from .kiosk import (
    KioskAuthError,
    KioskConnectionError,
    KioskError,
    async_login,
    base_url,
)

_LOGGER = logging.getLogger(__name__)


def _user_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_SATELLITE, default=defaults.get(CONF_SATELLITE, vol.UNDEFINED)
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="assist_satellite")
            ),
            vol.Required(
                CONF_HOST, default=defaults.get(CONF_HOST, vol.UNDEFINED)
            ): selector.TextSelector(),
            vol.Required(
                CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
            vol.Required(CONF_PASSWORD): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Required(CONF_SSL, default=defaults.get(CONF_SSL, False)): bool,
            vol.Required(
                CONF_VERIFY_SSL, default=defaults.get(CONF_VERIFY_SSL, True)
            ): bool,
        }
    )


class SimplePhraseAlarmClockConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow."""

    VERSION = 1

    async def _async_get_token(
        self, host: str, port: int, ssl: bool, verify_ssl: bool, password: str
    ) -> str:
        session = async_get_clientsession(self.hass, verify_ssl=verify_ssl)
        return await async_login(session, base_url(host, port, ssl), password)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a kiosk."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_SATELLITE])
            self._abort_if_unique_id_configured()
            try:
                token = await self._async_get_token(
                    user_input[CONF_HOST],
                    user_input[CONF_PORT],
                    user_input[CONF_SSL],
                    user_input[CONF_VERIFY_SSL],
                    user_input[CONF_PASSWORD],
                )
            except KioskAuthError:
                errors["base"] = "invalid_auth"
            except KioskConnectionError:
                errors["base"] = "cannot_connect"
            except KioskError:
                _LOGGER.exception("Unexpected response from the kiosk")
                errors["base"] = "unknown"
            else:
                state = self.hass.states.get(user_input[CONF_SATELLITE])
                title = state.name if state else user_input[CONF_SATELLITE]
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_SATELLITE: user_input[CONF_SATELLITE],
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_PORT: user_input[CONF_PORT],
                        CONF_SSL: user_input[CONF_SSL],
                        CONF_VERIFY_SSL: user_input[CONF_VERIFY_SSL],
                        CONF_TOKEN: token,
                    },
                )

        # Keep what was typed, but never echo the password back.
        suggested = {
            key: value
            for key, value in (user_input or {}).items()
            if key != CONF_PASSWORD
        }
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                _user_schema(), suggested
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """The token no longer works: ask for the password again."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Log in again and replace the stored token."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            try:
                token = await self._async_get_token(
                    entry.data[CONF_HOST],
                    entry.data[CONF_PORT],
                    entry.data[CONF_SSL],
                    entry.data[CONF_VERIFY_SSL],
                    user_input[CONF_PASSWORD],
                )
            except KioskAuthError:
                errors["base"] = "invalid_auth"
            except KioskConnectionError:
                errors["base"] = "cannot_connect"
            except KioskError:
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_TOKEN: token}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    )
                }
            ),
            description_placeholders={"name": entry.title},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> OptionsFlowWithReload:
        """Return the options flow."""
        return SimplePhraseAlarmClockOptionsFlow()


class SimplePhraseAlarmClockOptionsFlow(OptionsFlowWithReload):
    """Options: how the Speech-to-Phrase file is managed."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_MANAGE_S2P, default=options.get(CONF_MANAGE_S2P, True)
                    ): bool,
                    vol.Required(
                        CONF_S2P_ADDON,
                        default=options.get(CONF_S2P_ADDON, DEFAULT_S2P_ADDON),
                    ): str,
                }
            ),
        )
