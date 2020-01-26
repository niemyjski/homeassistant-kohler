"""Kohler Binary Sensor Integration"""
from homeassistant.components.binary_sensor import (
    BinarySensorDevice
)

from . import DATA_KOHLER


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Kohler Light platform."""
    data = hass.data[DATA_KOHLER]

    sensors = []
    for sensor in data.binarySensors:
        if sensor.installed:
            sensors.append(KohlerBinarySensor(data, sensor))

    add_entities(sensors)


class KohlerBinarySensor(BinarySensorDevice):
    """Representation of a single binary sensor in a Kohler device."""

    def __init__(self, data, sensor):
        """Initialize a Kohler binary sensor."""
        self._data = data
        self._sensor = sensor

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

    def update(self):
        """Request an update from the Kohler API."""
        self._data.updateBinarySensor(self._sensor)

    @property
    def icon(self):
        """Get the icon to use in the front end."""
        if self._sensor.state:
            return self._sensor.iconOn

        return self._sensor.iconOff
