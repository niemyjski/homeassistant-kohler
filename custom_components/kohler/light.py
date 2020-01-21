"""Kohler Light Integration"""
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    PLATFORM_SCHEMA,
    SUPPORT_BRIGHTNESS,
    Light
)

import logging
DOMAIN = 'kohler'
_LOGGER = logging.getLogger(__name__)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Kohler Light platform."""
    Kohler = hass.data[DOMAIN]["kohler"]
    values = hass.data[DOMAIN]["kohler_init_values"]
    sysInfo = hass.data[DOMAIN]["kohler_init_system_info"]

    # Add devices
    lights = []
    for lightId in range(1, 3):
        name = f"light{lightId}_installed"
        installed = False if name not in values else values[name]
        if not installed:
            continue

        lights.append(KohlerLight(Kohler, lightId, sysInfo, values))

    if len(lights) > 0:
        add_entities(lights)


class KohlerLight(Light):
    """Representation of an Kohler Light."""

    def __init__(self, Kohler, lightId, sysInfo, values):
        """Initialize a Kohler Light."""
        self._api = Kohler
        self._lightId = lightId
        self._deviceId = f"light{lightId}"
        self._name = "Kohler " + values[f"light{lightId}_name"]
        self._last_brightness = to_hass_level(values[f"light{lightId}_level"])

    @property
    def name(self):
        """Return the display name of this light."""
        return self._name

    @property
    def is_on(self):
        """Return true if light is on."""
        return True if self._last_brightness > 0 else False

    def turn_on(self, **kwargs):
        """Instruct the light to turn on."""
        brightness = kwargs.get(ATTR_BRIGHTNESS, self._last_brightness)
        intensity = self.to_kohler_level(brightness)
        self._api.lightOn(self._lightId, intensity)
        self._last_brightness = brightness

    def turn_off(self, **kwargs):
        """Instruct the light to turn off."""
        intensity = self.to_kohler_level(self._last_brightness)
        self._api.lightOff(self._lightId, intensity)
        self._last_brightness = 0

    @property
    def supported_features(self):
        """Flag supported features."""
        return SUPPORT_BRIGHTNESS

    @property
    def brightness(self):
        """Return the brightness of the light."""
        return self._last_brightness

    def update(self):
        """Fetch new state data for this light.
        This is the only method that should fetch new data for Home Assistant.
        """
        try:
            values = self._api.values()
            brightness = to_hass_level(values[f"light{self._lightId}_level"])
            self._last_brightness = brightness
        except:
            _LOGGER.error("Unable to retrieve data from Kohler server")

    @property
    def unique_id(self):
        """Get the unique identifier of the device."""
        return self._deviceId

    @property
    def device_id(self):
        """Return the ID of this light."""
        return self.unique_id

    def to_kohler_level(level):
        """Convert the given Home Assistant light level (0-255) to Kohler (0.0-100)."""
        return int((level * 100) / 255)

    def to_hass_level(level):
        """Convert the given Kohler (0.0-100. light level to Home Assistant (0-255)."""
        return int((level * 255) / 100)
