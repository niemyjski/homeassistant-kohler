"""Switches kohler water heater"""

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.const import (
    STATE_OFF,
    STATE_ON,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.core import callback

from homeassistant.const import (
    ATTR_TEMPERATURE,
    PRECISION_WHOLE,
    CONF_HOST,
    UnitOfTemperature,
)

from . import DATA_KOHLER, KohlerData
from .const import DOMAIN, MANUFACTURER, MODEL, DEFAULT_NAME

SUPPORTED_FEATURES = (
    WaterHeaterEntityFeature.TARGET_TEMPERATURE
    | WaterHeaterEntityFeature.OPERATION_MODE
)

SUPPORT_WATER_HEATER = [STATE_ON, STATE_OFF]


async def async_setup_entry(hass, config, add_entities):
    """Set up the Kohler platform."""
    data: KohlerData = hass.data[DATA_KOHLER]
    add_entities([KohlerWaterHeater(data)])


class KohlerWaterHeater(CoordinatorEntity, WaterHeaterEntity):
    """Representation of a Kohler Shower."""

    def __init__(self, data: KohlerData):
        """Initialize the shower device."""
        super().__init__(data)

        self._name = "Kohler Shower"
        self._data = data
        self._current_mode = None
        self._current_temperature = None
        self._unit_of_measurement = UnitOfTemperature.CELSIUS

        self._id = self._data.macAddress() + "_waterheater"
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
        self._current_mode = STATE_ON if self._data.isShowerOn() else STATE_OFF
        self._current_temperature = self._data.getCurrentTemperature()
        self._unit_of_measurement = self._data.unitOfMeasurement()

        super()._handle_coordinator_update()

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._id

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return SUPPORTED_FEATURES

    @property
    def name(self):
        """Return the name of the water_heater device."""
        return self._name

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self._unit_of_measurement

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._current_temperature

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
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
        return 30 if self._unit_of_measurement == UnitOfTemperature.CELSIUS else 86

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return 45 if self._unit_of_measurement == UnitOfTemperature.CELSIUS else 113

    @property
    def precision(self):
        """Return the precision of the system."""
        return PRECISION_WHOLE

    @property
    def current_operation(self):
        """Return current operation ie. on, off."""
        return self._current_mode

    @property
    def operation_list(self):
        """Return the list of available operation modes."""
        return SUPPORT_WATER_HEATER

    async def async_set_operation_mode(self, operation_mode):
        """Set operation mode."""
        if operation_mode == STATE_ON:
            await self.hass.async_add_executor_job(
                self._data.turnOnShower, self._data.getTargetTemperature()
            )
        else:
            await self.hass.async_add_executor_job(
                self._data.turnOffShower, self._data.getTargetTemperature()
            )

        await self.coordinator.async_request_refresh()

    @property
    def icon(self):
        """Get the icon to use in the front end."""
        return "mdi:shower"
