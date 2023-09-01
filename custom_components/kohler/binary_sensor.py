"""Kohler Binary Sensor Integration"""
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.entity import DeviceInfo
from .const import DOMAIN, MANUFACTURER, MODEL, DEFAULT_NAME
from homeassistant.const import CONF_HOST

from . import DATA_KOHLER, KohlerData, KohlerDataBinarySensor


async def async_setup_entry(hass, config, add_entities):
    """Set up the Kohler BinarySensorEntity platform."""
    data: KohlerData = hass.data[DATA_KOHLER]

    sensors: list[KohlerBinarySensor] = []
    for sensor in data.binarySensors:
        if sensor.installed:
            sensors.append(KohlerBinarySensor(data, sensor))

    add_entities(sensors)


class KohlerBinarySensor(BinarySensorEntity):
    """Representation of a single binary sensor in a Kohler device."""

    def __init__(self, data: KohlerData, sensor: KohlerDataBinarySensor):
        """Initialize a Kohler binary sensor."""
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
