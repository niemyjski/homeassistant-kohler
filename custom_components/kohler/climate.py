"""Kohler Climate Integration"""

import logging

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import ClimateEntityFeature, HVACMode
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import (
    ATTR_TEMPERATURE,
    PRECISION_WHOLE,
    CONF_HOST,
    UnitOfTemperature,
)

from .const import DOMAIN, MANUFACTURER, MODEL, DEFAULT_NAME
from .coordinator import KohlerDataUpdateCoordinator

SUPPORTED_MODES = [HVACMode.OFF, HVACMode.HEAT]

SUPPORTED_FEATURES = (
    ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.TURN_OFF
    | ClimateEntityFeature.TURN_ON
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config, add_entities):
    """Set up the Kohler platform."""
    _LOGGER.debug("Setting up Kohler ClimateEntity")

    coordinator: KohlerDataUpdateCoordinator = hass.data[DOMAIN]
    add_entities([KohlerThermostat(coordinator)])


class KohlerThermostat(CoordinatorEntity, ClimateEntity):
    """Representation of a Kohler Thermostat."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: KohlerDataUpdateCoordinator):
        """Initialize the thermostat device."""
        super().__init__(coordinator)

        self.coordinator: KohlerDataUpdateCoordinator = coordinator
        self._attr_name = "Shower"
        self._id = self.coordinator.macAddress() + "_thermostat"
        self._hvac_mode = None

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
        self._hvac_mode = (
            HVACMode.HEAT if self.coordinator.isShowerOn() else HVACMode.OFF
        )
        _LOGGER.debug("_handle_coordinator_update. _hvac_mode = %s", self._hvac_mode)

        super()._handle_coordinator_update()

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._id

    @property
    def suggested_object_id(self) -> str | None:
        """Return a stable object ID for the primary shower climate entity."""
        return "kohler_shower"

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return SUPPORTED_FEATURES

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self.coordinator.unitOfMeasurement()

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return (
            self.coordinator.getCurrentTemperature()
            or self.coordinator.getTargetTemperature()
        )

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self.coordinator.getTargetTemperature()

    async def async_set_temperature(self, **kwargs):
        """Set new target temperatures."""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            await self.coordinator.setTargetTemperature(temp)
        await self.coordinator.async_request_refresh()

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return (
            30
            if self.coordinator.unitOfMeasurement() == UnitOfTemperature.CELSIUS
            else 86
        )

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        temps = [
            self.coordinator.getMaxTemperatureSetting(valve)
            for valve in range(1, 3)
            if self.coordinator.isValveInstalled(valve)
        ]
        values = [temp for temp in temps if temp is not None]
        if values:
            return max(values)
        return (
            45
            if self.coordinator.unitOfMeasurement() == UnitOfTemperature.CELSIUS
            else 113
        )

    @property
    def precision(self):
        """Return the precision of the system."""
        return PRECISION_WHOLE

    @property
    def hvac_mode(self):
        """Return current operation ie. on, off."""
        return self._hvac_mode

    @property
    def hvac_modes(self):
        """Return the list of available operation modes."""
        return SUPPORTED_MODES

    async def async_set_hvac_mode(self, mode):
        """Set operation mode."""
        self._hvac_mode = mode
        if mode == HVACMode.OFF:
            await self.coordinator.turnOffShower()
        else:
            await self.coordinator.turnOnShower(self.coordinator.getTargetTemperature())
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self):
        await self.coordinator.turnOnShower(self.coordinator.getTargetTemperature())
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self):
        await self.coordinator.turnOffShower()
        await self.coordinator.async_request_refresh()

    @property
    def icon(self):
        """Get the icon to use in the front end."""
        return "mdi:shower"

    @property
    def extra_state_attributes(self):
        """Expose translated valve settings on the primary shower entity."""
        attributes = {"units": self.coordinator.getUnitsSetting()}
        for valve in range(1, 3):
            if not self.coordinator.isValveInstalled(valve):
                continue
            for key, value in self.coordinator.getValveSettingsAttributes(
                valve
            ).items():
                attributes[f"valve_{valve}_{key}"] = value
        return attributes
