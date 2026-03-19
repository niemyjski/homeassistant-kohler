"""Config flow for Kohler DTV."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv

from kohler import Kohler, KohlerError

from .const import CONF_ACCEPT_LIABILITY_TERMS, DOMAIN

_LOGGER = logging.getLogger(__package__)


class KohlerFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Kohler config flow."""

    VERSION = 2

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Handle a flow initialized by the user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if not user_input[CONF_ACCEPT_LIABILITY_TERMS]:
                errors[CONF_ACCEPT_LIABILITY_TERMS] = "accept_terms"
            elif not await self.test_connection(user_input[CONF_HOST]):
                errors[CONF_HOST] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_HOST], data=user_input
                )

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

    async def test_connection(self, host: str) -> bool:
        """Test connection to the Kohler device."""
        try:
            api = Kohler(kohler_host=host, timeout=5.0)
            async with asyncio.timeout(10.0):
                await api.values()
            return True
        except (KohlerError, OSError, asyncio.TimeoutError) as ex:
            _LOGGER.error("Error connecting to Kohler DTV+ %s", ex)
            return False
