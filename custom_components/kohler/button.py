"""Buttons for Kohler DTV+"""

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.const import CONF_HOST, EntityCategory

from .const import DOMAIN, MANUFACTURER, MODEL, DEFAULT_NAME
from .coordinator import KohlerDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config, add_entities):
    """Set up the Kohler ButtonEntity platform."""
    coordinator: KohlerDataUpdateCoordinator = hass.data[DOMAIN]

    buttons = [
        KohlerSyncTimeButton(coordinator),
        KohlerMassageButton(coordinator),
        KohlerResetControllerFaultsButton(coordinator),
        KohlerResetKonnectFaultsButton(coordinator),
        KohlerCheckUpdatesButton(coordinator),
    ]

    add_entities(buttons)


class KohlerButton(ButtonEntity):
    """Base button for Kohler."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: KohlerDataUpdateCoordinator, name: str, key: str):
        """Initialize."""
        self.coordinator = coordinator
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.macAddress()}_{key}"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.macAddress())},
            manufacturer=MANUFACTURER,
            configuration_url="http://" + coordinator.getConf(CONF_HOST),
            name=DEFAULT_NAME,
            model=MODEL,
            hw_version=self.coordinator.firmwareVersion(),
            sw_version=self.coordinator.firmwareVersion(),
        )


class KohlerMassageButton(KohlerButton):
    """Button to toggle massage mode."""

    def __init__(self, coordinator: KohlerDataUpdateCoordinator):
        super().__init__(coordinator, "Massage Toggle", "massage_toggle")
        self._attr_icon = "mdi:spa"

    async def async_press(self) -> None:
        """Press the button."""
        await self.coordinator.massage_toggle()
        await self.coordinator.async_request_post_command_refresh()


class KohlerSyncTimeButton(KohlerButton):
    """Button to sync the device time from Home Assistant."""

    def __init__(self, coordinator: KohlerDataUpdateCoordinator):
        super().__init__(coordinator, "Sync Time", "sync_time")
        self._attr_icon = "mdi:clock-sync"
        self._attr_entity_category = EntityCategory.CONFIG

    async def async_press(self) -> None:
        """Press the button."""
        await self.coordinator.sync_time()
        await self.coordinator.async_request_post_command_refresh()


class KohlerResetControllerFaultsButton(KohlerButton):
    """Button to reset controller faults."""

    def __init__(self, coordinator: KohlerDataUpdateCoordinator):
        super().__init__(
            coordinator, "Reset Controller Faults", "reset_controller_faults"
        )
        self._attr_icon = "mdi:restart-alert"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    async def async_press(self) -> None:
        """Press the button."""
        await self.coordinator.reset_controller_faults()
        await self.coordinator.async_request_post_command_refresh()


class KohlerResetKonnectFaultsButton(KohlerButton):
    """Button to reset konnect faults."""

    def __init__(self, coordinator: KohlerDataUpdateCoordinator):
        super().__init__(coordinator, "Reset Konnect Faults", "reset_konnect_faults")
        self._attr_icon = "mdi:restart-alert"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    async def async_press(self) -> None:
        """Press the button."""
        await self.coordinator.reset_konnect_faults()
        await self.coordinator.async_request_post_command_refresh()


class KohlerCheckUpdatesButton(KohlerButton):
    """Button to check for firmware updates."""

    def __init__(self, coordinator: KohlerDataUpdateCoordinator):
        super().__init__(coordinator, "Check for Updates", "check_updates")
        self._attr_icon = "mdi:update"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    async def async_press(self) -> None:
        """Press the button."""
        await self.coordinator.check_updates()
        await self.coordinator.async_request_post_command_refresh()
