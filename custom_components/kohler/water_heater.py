"""Kohler Water Heater Integration"""

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

from .const import DOMAIN, MANUFACTURER, MODEL, DEFAULT_NAME
from .coordinator import KohlerDataUpdateCoordinator

SUPPORTED_FEATURES = (
    WaterHeaterEntityFeature.TARGET_TEMPERATURE
    | WaterHeaterEntityFeature.OPERATION_MODE
)

SUPPORT_WATER_HEATER = [STATE_ON, STATE_OFF]


async def async_setup_entry(hass, config, add_entities):
    """Set up the Kohler platform."""
    coordinator: KohlerDataUpdateCoordinator = hass.data[DOMAIN]
    add_entities([KohlerWaterHeater(coordinator)])


class KohlerWaterHeater(CoordinatorEntity, WaterHeaterEntity):
    """Representation of a Kohler Shower."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: KohlerDataUpdateCoordinator):
        """Initialize the shower device."""
        super().__init__(coordinator)

        self.coordinator: KohlerDataUpdateCoordinator = coordinator
        self._attr_name = "Shower"
        self._current_mode = None
        self._current_temperature = None
        self._unit_of_measurement = UnitOfTemperature.CELSIUS

        self._id = self.coordinator.macAddress() + "_waterheater"
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
        self._current_mode = STATE_ON if self.coordinator.isShowerOn() else STATE_OFF
        self._current_temperature = self.coordinator.getCurrentTemperature()
        self._unit_of_measurement = self.coordinator.unitOfMeasurement()

        super()._handle_coordinator_update()

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._id

    @property
    def suggested_object_id(self) -> str | None:
        """Return a stable object ID for the shower water heater entity."""
        return "kohler_shower"

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return SUPPORTED_FEATURES

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
        return self.coordinator.getTargetTemperature()

    async def async_set_temperature(self, **kwargs):
        """Set new target temperatures."""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            await self.coordinator.setTargetTemperature(temp)

        await self.coordinator.async_request_post_command_refresh()

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return 30 if self._unit_of_measurement == UnitOfTemperature.CELSIUS else 86

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
            await self.coordinator.turnOnShower(self.coordinator.getTargetTemperature())
        else:
            await self.coordinator.turnOffShower()

        await self.coordinator.async_request_post_command_refresh()

    @property
    def icon(self):
        """Get the icon to use in the front end."""
        return "mdi:shower"

    @property
    def extra_state_attributes(self):
        """Expose translated valve settings on the shower water heater."""
        attributes = {"units": self.coordinator.getUnitsSetting()}
        for valve in range(1, 3):
            if not self.coordinator.isValveInstalled(valve):
                continue
            for key, value in self.coordinator.getValveSettingsAttributes(
                valve
            ).items():
                attributes[f"valve_{valve}_{key}"] = value
        return attributes
