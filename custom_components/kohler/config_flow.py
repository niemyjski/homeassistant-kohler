"""Config flow for Kohler DTV."""
from __future__ import annotations

import logging
from typing import Any


import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv

from .const import CONF_ACCEPT_LIABILITY_TERMS, DOMAIN

_LOGGER = logging.getLogger(__package__)


class KohlerFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Kohler config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Handle a flow initialized by the user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input[CONF_ACCEPT_LIABILITY_TERMS]:
                return self.async_create_entry(
                    title=user_input[CONF_HOST], data=user_input
                )
            else:
                errors[CONF_ACCEPT_LIABILITY_TERMS] = "accept_terms"

        # Validation of the user's configuration
        data_schema = {
            vol.Required(CONF_HOST): cv.string,
            vol.Required(CONF_ACCEPT_LIABILITY_TERMS): cv.boolean,
        }

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(data_schema),
            errors=errors,
        )

    async def async_step_import(self, config: dict[str, Any]) -> FlowResult:
        """Import a config entry."""

        user_input = {
            CONF_HOST: config[CONF_HOST],
            CONF_ACCEPT_LIABILITY_TERMS: config.get(CONF_ACCEPT_LIABILITY_TERMS),
        }
        return await self.async_step_user(user_input)
