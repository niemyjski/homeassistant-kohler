"""Valve entities for Kohler shower outlets."""

import logging

from homeassistant.components.valve import (
    ValveDeviceClass,
    ValveEntity,
    ValveEntityFeature,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL, DEFAULT_NAME
from .coordinator import KohlerDataUpdateCoordinator
from .entity_helpers import OutletDescriptor, build_outlet_descriptors

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config, add_entities):
    """Set up the Kohler Valve platforms."""
    _LOGGER.debug("async_setup_entry for valves.")
    coordinator: KohlerDataUpdateCoordinator = hass.data[DOMAIN]

    valves = [
        KohlerValve(
            coordinator=coordinator,
            uid=(
                f"{coordinator.macAddress()}_valve{descriptor.valve}outlet"
                f"{descriptor.outlet}"
            ),
            descriptor=descriptor,
        )
        for descriptor in build_outlet_descriptors(coordinator)
    ]

    add_entities(valves)


class KohlerValve(CoordinatorEntity, ValveEntity):
    """Representation of a single water outlet as a Valve."""

    _attr_device_class = ValveDeviceClass.WATER
    _attr_reports_position = False
    _attr_supported_features = ValveEntityFeature.OPEN | ValveEntityFeature.CLOSE
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: KohlerDataUpdateCoordinator,
        uid: str,
        descriptor: OutletDescriptor,
    ):
        super().__init__(coordinator)
        self.coordinator: KohlerDataUpdateCoordinator = coordinator
        self._uid = uid
        self._attr_name = descriptor.display_name
        self._valve = descriptor.valve
        self._outlet = descriptor.outlet
        self._attr_is_closed = True
        self._assigned_icon = descriptor.icon
        self._descriptor_attributes = descriptor.state_attributes

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
        is_on = self.coordinator.isOutletOn(
            self._valve, self._outlet
        ) and self.coordinator.isValveOn(self._valve)

        self._attr_is_closed = not is_on
        super()._handle_coordinator_update()

    @property
    def unique_id(self):
        return self._uid

    @property
    def icon(self):
        return self._assigned_icon

    @property
    def extra_state_attributes(self):
        """Return extra metadata for the outlet."""
        return {
            **self._descriptor_attributes,
            **self.coordinator.getValveSettingsAttributes(self._valve),
        }

    async def async_open_valve(self, **kwargs) -> None:
        """Open the valve."""
        await self.coordinator.openOutlet(self._valve, self._outlet)
        await self.coordinator.async_request_refresh()

    async def async_close_valve(self, **kwargs) -> None:
        """Close the valve."""
        await self.coordinator.closeOutlet(self._valve, self._outlet)
        await self.coordinator.async_request_refresh()
