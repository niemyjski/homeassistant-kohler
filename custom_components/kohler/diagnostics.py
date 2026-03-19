"""Diagnostics support for Kohler API."""

from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import KohlerDataUpdateCoordinator
from kohler import KohlerError

TO_REDACT = {"MAC"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: KohlerDataUpdateCoordinator = hass.data[DOMAIN]
    controller_error_log, konnect_error_log = await asyncio.gather(
        _async_get_error_log(coordinator, "controller"),
        _async_get_error_log(coordinator, "konnect"),
    )

    return {
        "device_info": async_redact_data(coordinator._sysInfo, TO_REDACT),
        "values": async_redact_data(coordinator._values, TO_REDACT),
        "valve1_outlet_mappings": coordinator._valve1_outlet_mappings,
        "valve2_outlet_mappings": coordinator._valve2_outlet_mappings,
        "target_temperature": coordinator._target_temperature,
        "controller_error_log": controller_error_log,
        "konnect_error_log": konnect_error_log,
    }


async def _async_get_error_log(
    coordinator: KohlerDataUpdateCoordinator,
    log_type: str,
) -> str | dict[str, str]:
    """Fetch a controller or Konnect error log for diagnostics export."""
    try:
        async with asyncio.timeout(10):
            if log_type == "controller":
                return await coordinator.api.controller_error_logs()
            return await coordinator.api.konnect_error_logs()
    except (KohlerError, OSError, asyncio.TimeoutError) as err:
        return {"error": str(err)}
