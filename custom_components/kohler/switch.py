"""Switches kohler outlet on/off """

import logging
import re

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity


from .const import DOMAIN, MANUFACTURER, MODEL, DEFAULT_NAME
from . import DATA_KOHLER, KohlerData, KohlerDataBinarySensor

_LOGGER = logging.getLogger(__name__)

OUTLET_ID_PATTERN = re.compile(".*_valve([0-9])outlet([0-9])")


async def async_setup_entry(hass, config, add_entities):
    """Set up the Kohler SwitchEntity platform."""
    _LOGGER.debug(f"async_setup_entry for switches.")
    data: KohlerData = hass.data[DATA_KOHLER]

    switches: list[KohlerSwitch] = []
    for sensor in data.binarySensors:
        if sensor.installed:
            _LOGGER.debug(f"Checking whether to add a switch for {sensor.id}")
            sensor_id_match = OUTLET_ID_PATTERN.fullmatch(sensor.id)
            if sensor_id_match:
                _LOGGER.debug(f"Adding a switch for {sensor.id}")
                switches.append(
                    KohlerSwitch(
                        data,
                        sensor,
                        int(sensor_id_match.group(1)),
                        int(sensor_id_match.group(2)),
                    )
                )

    add_entities(switches)


class KohlerSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of a single outlet in a Kohler device."""

    def __init__(
        self, data: KohlerData, sensor: KohlerDataBinarySensor, valve: int, outlet: int
    ):
        """Initialize a Kohler binary sensor."""
        super().__init__(data)
        self._data = data
        self._sensor = sensor
        self._valve = valve
        self._outlet = outlet
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
        super()._handle_coordinator_update()

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._sensor.id

    @property
    def name(self):
        """Return the name of the Kohler device and this sensor."""
        return self._sensor.name

    @property
    def device_class(self):
        """Return the class of this sensor, from DEVICE_CLASSES."""
        return self._sensor.deviceClass

    @property
    def is_on(self):
        """Return true if binary sensor is on."""
        return self._sensor.state and self._data.isValveOn(self._valve)

    @property
    def icon(self):
        """Get the icon to use in the front end."""
        if self.is_on:
            return self._sensor.iconOn

        return self._sensor.iconOff

    async def async_turn_on(self, **kwargs):
        """Open outlet."""
        await self.hass.async_add_executor_job(
            self._data.openOutlet, self._valve, self._outlet
        )
        self.coordinator.async_update_listeners()

    async def async_turn_off(self, **kwargs):
        """Close outlet."""
        await self.hass.async_add_executor_job(
            self._data.closeOutlet, self._valve, self._outlet
        )
        self.coordinator.async_update_listeners()
