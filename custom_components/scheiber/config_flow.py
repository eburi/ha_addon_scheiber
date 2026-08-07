"""Config flow for the Scheiber CAN integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    CONF_CAN_INTERFACE,
    CONF_CONFIG_PATH,
    CONF_DISCOVERY_ONLY,
    CONF_MAX_MESSAGE_IDS,
    CONF_READ_ONLY,
    CONF_STATE_FILE,
    DEFAULT_CAN_INTERFACE,
    DEFAULT_DISCOVERY_ONLY,
    DEFAULT_MAX_MESSAGE_IDS,
    DEFAULT_READ_ONLY,
    DOMAIN,
)


class ScheiberConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Scheiber CAN."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            can_interface = user_input[CONF_CAN_INTERFACE].strip()
            if not can_interface:
                errors[CONF_CAN_INTERFACE] = "cannot_be_empty"
            else:
                await self.async_set_unique_id(f"scheiber_{can_interface}")
                self._abort_if_unique_id_configured()
                data = {
                    CONF_CAN_INTERFACE: can_interface,
                    CONF_READ_ONLY: user_input[CONF_READ_ONLY],
                    CONF_DISCOVERY_ONLY: user_input[CONF_DISCOVERY_ONLY],
                    CONF_MAX_MESSAGE_IDS: user_input[CONF_MAX_MESSAGE_IDS],
                }
                optional_config_path = user_input.get(CONF_CONFIG_PATH, "").strip()
                optional_state_file = user_input.get(CONF_STATE_FILE, "").strip()
                if optional_config_path:
                    data[CONF_CONFIG_PATH] = optional_config_path
                if optional_state_file:
                    data[CONF_STATE_FILE] = optional_state_file

                return self.async_create_entry(
                    title=f"Scheiber CAN ({can_interface})",
                    data=data,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input or {}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return ScheiberOptionsFlow(config_entry)


class ScheiberOptionsFlow(config_entries.OptionsFlow):
    """Handle Scheiber CAN options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            data = dict(user_input)
            if not data.get(CONF_CONFIG_PATH, "").strip():
                data.pop(CONF_CONFIG_PATH, None)
            if not data.get(CONF_STATE_FILE, "").strip():
                data.pop(CONF_STATE_FILE, None)
            return self.async_create_entry(title="", data=data)

        merged = {**self._entry.data, **self._entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=_schema(merged),
        )


def _schema(defaults: dict[str, Any]) -> vol.Schema:
    """Return config/options schema."""
    return vol.Schema(
        {
            vol.Required(
                CONF_CAN_INTERFACE,
                default=defaults.get(CONF_CAN_INTERFACE, DEFAULT_CAN_INTERFACE),
            ): str,
            vol.Required(
                CONF_READ_ONLY,
                default=defaults.get(CONF_READ_ONLY, DEFAULT_READ_ONLY),
            ): bool,
            vol.Required(
                CONF_DISCOVERY_ONLY,
                default=defaults.get(CONF_DISCOVERY_ONLY, DEFAULT_DISCOVERY_ONLY),
            ): bool,
            vol.Optional(
                CONF_CONFIG_PATH,
                default=defaults.get(CONF_CONFIG_PATH, ""),
            ): str,
            vol.Optional(
                CONF_STATE_FILE,
                default=defaults.get(CONF_STATE_FILE, ""),
            ): str,
            vol.Required(
                CONF_MAX_MESSAGE_IDS,
                default=defaults.get(CONF_MAX_MESSAGE_IDS, DEFAULT_MAX_MESSAGE_IDS),
            ): vol.All(vol.Coerce(int), vol.Range(min=10, max=2000)),
        }
    )
