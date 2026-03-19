"""Switches kohler outlet on/off"""

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL, DEFAULT_NAME
from .coordinator import KohlerDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config, add_entities):
    """Set up the Kohler SwitchEntity platform."""
    _LOGGER.debug("async_setup_entry for switches.")
    coordinator: KohlerDataUpdateCoordinator = hass.data[DOMAIN]

    switches = []

    if coordinator.isSteamInstalled():
        switches.append(KohlerSteamSwitch(coordinator))

    add_entities(switches)


class KohlerSteamSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of the Steam system in a Kohler device."""

    def __init__(self, coordinator: KohlerDataUpdateCoordinator):
        """Initialize a Kohler Steam switch."""
        super().__init__(coordinator)
        self.coordinator: KohlerDataUpdateCoordinator = coordinator
        self._uid = f"{coordinator.macAddress()}_steam_switch"
        self._attr_name = "Kohler Steam"
        self._attr_is_on = False

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.macAddress())},
            manufacturer=MANUFACTURER,
            configuration_url="http://" + coordinator.getConf(CONF_HOST),
            name=DEFAULT_NAME,
            model=MODEL,
            hw_version=self.coordinator.firmwareVersion(),
            sw_version=self.coordinator.firmwareVersion(),
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        state = self.coordinator.getValue("steam_running")
        self._attr_is_on = state is True or state == "True" or state == "On"
        super()._handle_coordinator_update()

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._uid

    @property
    def icon(self):
        """Get the icon to use in the front end."""
        return "mdi:radiator" if self.is_on else "mdi:radiator-disabled"

    async def async_turn_on(self, **kwargs):
        """Turn Steam on."""
        await self.coordinator.steam_on(temp=110, time=15)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        """Turn Steam off."""
        await self.coordinator.steam_off()
        await self.coordinator.async_request_refresh()
