"""Kohler Binary Sensor Integration"""

from homeassistant.core import callback
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import CONF_HOST
from .const import DOMAIN, MANUFACTURER, MODEL, DEFAULT_NAME

from . import (
    DATA_KOHLER,
    KohlerData,
    KohlerDataBinarySensor,
    KohlerDataOutletBinarySensor,
)


async def async_setup_entry(hass, config, add_entities):
    """Set up the Kohler BinarySensorEntity platform."""
    data: KohlerData = hass.data[DATA_KOHLER]

    sensors: list[KohlerBinarySensor] = []
    for sensor in data.binarySensors:
        if sensor.installed:
            if isinstance(sensor, KohlerDataOutletBinarySensor):
                sensors.append(KohlerOutletBinarySensor(data, sensor))
            else:
                sensors.append(KohlerBinarySensor(data, sensor))

    add_entities(sensors)


class KohlerBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of a single binary sensor in a Kohler device."""

    def __init__(self, data: KohlerData, sensor: KohlerDataBinarySensor):
        """Initialize a Kohler binary sensor."""
        super().__init__(data)
        self._data = data
        self._sensor = sensor
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
        self._data.updateBinarySensor(self._sensor)
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
        return self._sensor.state

    @property
    def icon(self):
        """Get the icon to use in the front end."""
        if self._sensor.state:
            return self._sensor.iconOn

        return self._sensor.iconOff


class KohlerOutletBinarySensor(KohlerBinarySensor):
    """Representation of a single binary sensor in a Kohler device."""

    def __init__(self, data: KohlerData, sensor: KohlerDataOutletBinarySensor):
        """Initialize a Kohler binary sensor."""
        super().__init__(data, sensor)
        self._valve = sensor.valve

    @property
    def is_on(self):
        """Return true if binary sensor is on."""
        return self._sensor.state and self._data.isValveOn(self._valve)
