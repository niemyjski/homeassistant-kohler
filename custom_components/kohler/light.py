"""Kohler LightEntity Integration"""

import logging

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import CONF_HOST

from .const import DOMAIN, MANUFACTURER, MODEL, DEFAULT_NAME
from .coordinator import KohlerDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config, add_entities):
    """Set up the Kohler LightEntity platform."""
    coordinator: KohlerDataUpdateCoordinator = hass.data[DOMAIN]

    lights = []

    for light_id in range(1, 3):
        device_id = f"light{light_id}"
        installed_key = f"{device_id}_installed"
        installed = coordinator.getValue(installed_key, False)
        if installed:
            lights.append(KohlerLight(coordinator, light_id, device_id))

    add_entities(lights)


class KohlerLight(CoordinatorEntity, LightEntity):
    """Representation of a Kohler Light."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: KohlerDataUpdateCoordinator, light_id: int, device_id: str
    ):
        """Initialize a Kohler Light."""
        super().__init__(coordinator)
        self.coordinator: KohlerDataUpdateCoordinator = coordinator
        self._light_id = light_id
        self._device_id = device_id

        self._attr_name = (
            str(self.coordinator.getValue(f"{self._device_id}_name", "Light"))
            .replace("Kohler ", "")
            .strip()
        )
        self._attr_unique_id = f"{self.coordinator.macAddress()}_{self._device_id}"
        self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
        self._attr_color_mode = ColorMode.BRIGHTNESS

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.macAddress())},
            manufacturer=MANUFACTURER,
            configuration_url="http://" + coordinator.getConf(CONF_HOST),
            default_name=DEFAULT_NAME,
            model=MODEL,
            hw_version=self.coordinator.firmwareVersion(),
            sw_version=self.coordinator.firmwareVersion(),
        )

        self._update_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_state()
        super()._handle_coordinator_update()

    def _update_state(self):
        """Update local state from coordinator before writing to HA state machine."""
        brightness_level = self.coordinator.getValue(f"{self._device_id}_level", 0)
        self._attr_brightness = self.to_hass_level(brightness_level)
        self._attr_is_on = brightness_level > 0

    async def async_turn_on(self, **kwargs):
        """Instruct the light to turn on."""
        brightness = kwargs.get(ATTR_BRIGHTNESS, self.brightness or 255)
        intensity = self.to_kohler_level(brightness)
        await self.coordinator.light_on(self._light_id, intensity)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        """Instruct the light to turn off."""
        await self.coordinator.light_off(self._light_id)
        await self.coordinator.async_request_refresh()

    def to_kohler_level(self, level):
        """Convert the given Home Assistant light level (0-255) to Kohler (0-100)."""
        return int((level * 100) / 255)

    def to_hass_level(self, level):
        """Convert the given Kohler (0-100) light level to Home Assistant (0-255)."""
        return int(level * 2.55)
