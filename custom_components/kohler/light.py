"""Kohler Light Integration"""
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    SUPPORT_BRIGHTNESS,
    Light
)

from . import DATA_KOHLER, KohlerData, KohlerDataLight


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Kohler Light platform."""
    data: KohlerData = hass.data[DATA_KOHLER]

    # Add devices
    lights: list[KohlerLight] = []
    for light in data.lights:
        if light.installed:
            lights.append(KohlerLight(data, light))

    add_entities(lights)


class KohlerLight(Light):
    """Representation of an Kohler Light."""

    def __init__(self, data: KohlerData, light: KohlerDataLight):
        """Initialize a Kohler Light."""
        self._data = data
        self._light = light

    @property
    def name(self):
        """Return the display name of this light."""
        return self._light.name

    @property
    def is_on(self):
        """Return true if light is on."""
        return True if self._light.brightness > 0 else False

    def turn_on(self, **kwargs):
        """Instruct the light to turn on."""
        brightness = kwargs.get(ATTR_BRIGHTNESS, self.brightness)
        intensity = self.to_kohler_level(brightness)
        self._data.turnlightOn(self._light.id, intensity)
        self._light.brightness = intensity

    def turn_off(self, **kwargs):
        """Instruct the light to turn off."""
        self._data.turnlightOff(self._light.id)

    @property
    def supported_features(self):
        """Flag supported features."""
        return SUPPORT_BRIGHTNESS

    @property
    def brightness(self):
        """Return the brightness of the light."""
        return self.to_hass_level(self._light.brightness)

    def update(self):
        """Fetch new state data for this light.
        This is the only method that should fetch new data for Home Assistant.
        """
        self._data.updateLight(self._light)

    @property
    def unique_id(self):
        """Get the unique identifier of the device."""
        return self._light.deviceId

    @property
    def device_id(self):
        """Return the ID of this light."""
        return self.unique_id

    def to_kohler_level(self, level):
        """Convert the given Home Assistant light level (0-255) to Kohler (0.0-100)."""
        return int((level * 100) / 255)

    def to_hass_level(self, level):
        """Convert the given Kohler (0.0-100. light level to Home Assistant (0-255)."""
        return int(level * 2.55)
