"""Kohler Climate Integration"""

import logging

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import ClimateEntityFeature
from homeassistant.components.climate.const import HVACMode
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo

from homeassistant.const import (
    ATTR_TEMPERATURE,
    PRECISION_WHOLE,
    CONF_HOST,
    UnitOfTemperature,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DATA_KOHLER, KohlerData
from .const import DOMAIN, MANUFACTURER, MODEL, DEFAULT_NAME

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

    data: KohlerData = hass.data[DATA_KOHLER]
    add_entities([KohlerThermostat(data)])


class KohlerThermostat(CoordinatorEntity, ClimateEntity):
    """Representation of a Kohler Thermostat."""

    def __init__(self, data: KohlerData):
        """Initialize the thermostat device."""
        super().__init__(data)
        self._name = "Kohler Thermostat"
        self._data = data
        self._id = self._data.macAddress() + "_thermostat"
        self._hvac_mode = None

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._data.macAddress())},
            manufacturer=MANUFACTURER,
            configuration_url="http://" + data.getConf(CONF_HOST),
            name=DEFAULT_NAME,
            model=MODEL,
            hw_version=self._data.firmwareVersion(),
            sw_version=self._data.firmwareVersion(),
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._hvac_mode = HVACMode.HEAT if self._data.isShowerOn() else HVACMode.OFF
        _LOGGER.debug("_handle_coordinator_update. _hvac_mode = %s", self._hvac_mode)

        super()._handle_coordinator_update()

    @property
    def unique_id(self):
        """Return a unique ID."""
        _LOGGER.debug("_id = %s", self._id)
        return self._id

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return SUPPORTED_FEATURES

    @property
    def name(self):
        """Return the name of the climate device."""
        _LOGGER.debug("_name = %s", self._name)
        return self._name

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        _LOGGER.debug("temperature_unit = %s", self._data.unitOfMeasurement())
        return self._data.unitOfMeasurement()

    @property
    def current_temperature(self):
        """Return the current temperature."""
        _LOGGER.debug(
            "current_temperature = %s, target_temperature = %s",
            self._data.getCurrentTemperature(),
            self._data.getTargetTemperature(),
        )
        return self._data.getCurrentTemperature() or self._data.getTargetTemperature()

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        _LOGGER.debug("target_temperature = %s", self._data.getTargetTemperature())
        return self._data.getTargetTemperature()

    async def async_set_temperature(self, **kwargs):
        """Set new target temperatures."""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            await self.hass.async_add_executor_job(
                self._data.setTargetTemperature, temp
            )
        await self.coordinator.async_request_refresh()

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return 30 if self._data.unitOfMeasurement() == UnitOfTemperature.CELSIUS else 86

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return (
            45 if self._data.unitOfMeasurement() == UnitOfTemperature.CELSIUS else 113
        )

    @property
    def precision(self):
        """Return the precision of the system."""
        return PRECISION_WHOLE

    @property
    def hvac_mode(self):
        """Return current operation ie. on, off."""
        _LOGGER.debug("hvac_mode = %s", self._hvac_mode)
        return self._hvac_mode

    @property
    def hvac_modes(self):
        """Return the list of available operation modes."""
        return SUPPORTED_MODES

    async def async_set_hvac_mode(self, mode):
        """Set operation mode."""
        self._hvac_mode = mode
        if mode == HVACMode.OFF:
            await self.hass.async_add_executor_job(self._data.turnOffShower)
        else:
            await self.hass.async_add_executor_job(
                self._data.turnOnShower, self._data.getTargetTemperature()
            )
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self):
        await self.hass.async_add_executor_job(
            self._data.turnOnShower, self._data.getTargetTemperature()
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self):
        await self.hass.async_add_executor_job(self._data.turnOffShower)
        await self.coordinator.async_request_refresh()

    @property
    def icon(self):
        """Get the icon to use in the front end."""
        return "mdi:shower"
