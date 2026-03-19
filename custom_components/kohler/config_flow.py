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
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from kohler import Kohler, KohlerError

from .const import CONF_ACCEPT_LIABILITY_TERMS, DOMAIN
from .entity_helpers import normalize_mac_address

_LOGGER = logging.getLogger(__package__)


class KohlerFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Kohler config flow."""

    VERSION = 3

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_host: str | None = None

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Handle a flow initialized by the user."""
        errors: dict[str, str] = {}
        default_host = self._discovered_host or ""

        if user_input is not None:
            host = user_input[CONF_HOST]
            self._async_abort_entries_match({CONF_HOST: host})

            if not user_input[CONF_ACCEPT_LIABILITY_TERMS]:
                errors[CONF_ACCEPT_LIABILITY_TERMS] = "accept_terms"
            else:
                unique_id = await self.test_connection(host)
                if unique_id is None:
                    errors[CONF_HOST] = "cannot_connect"
                else:
                    await self.async_set_unique_id(unique_id, raise_on_progress=False)
                    self._abort_if_unique_id_configured(
                        updates=user_input,
                        reload_on_update=True,
                    )
                    return self.async_create_entry(title=host, data=user_input)

        data_schema = {
            vol.Required(CONF_HOST, default=default_host): cv.string,
            vol.Required(CONF_ACCEPT_LIABILITY_TERMS): cv.boolean,
        }

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(data_schema),
            errors=errors,
        )

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo) -> FlowResult:
        """Handle a flow initialized by DHCP discovery."""
        host = discovery_info.ip
        discovered_mac = normalize_mac_address(discovery_info.macaddress)

        self._async_abort_entries_match({CONF_HOST: host})

        if discovered_mac is not None:
            await self.async_set_unique_id(discovered_mac, raise_on_progress=False)
            self._abort_if_unique_id_configured(
                updates={CONF_HOST: host},
                reload_on_update=True,
            )

        if await self.test_connection(host) is None:
            return self.async_abort(reason="cannot_connect")

        self._discovered_host = host
        return await self.async_step_user()

    async def async_step_import(self, config: dict[str, Any]) -> FlowResult:
        """Import a config entry."""

        user_input = {
            CONF_HOST: config[CONF_HOST],
            CONF_ACCEPT_LIABILITY_TERMS: config.get(CONF_ACCEPT_LIABILITY_TERMS),
        }
        return await self.async_step_user(user_input)

    async def test_connection(self, host: str) -> str | None:
        """Test connection to the Kohler device and return its MAC address."""
        try:
            api = Kohler(kohler_host=host, timeout=5.0)
            async with asyncio.timeout(10.0):
                values = await api.values()
            return normalize_mac_address(values.get("MAC"))
        except (KohlerError, OSError, asyncio.TimeoutError) as ex:
            _LOGGER.error("Error connecting to Kohler DTV+ %s", ex)
            return None
