"""Select platform for Kohler integration."""

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL, DEFAULT_NAME
from .coordinator import KohlerDataUpdateCoordinator


async def async_setup_entry(hass, config, add_entities):
    """Set up the Kohler Select platform."""
    coordinator: KohlerDataUpdateCoordinator = hass.data[DOMAIN]
    add_entities([KohlerUserPresetSelect(coordinator)])


class KohlerUserPresetSelect(CoordinatorEntity, SelectEntity):
    """Representation of the Kohler Active User Preset dropdown."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:account-badge"

    def __init__(self, coordinator: KohlerDataUpdateCoordinator):
        """Initialize the select entity."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._attr_name = "Active User Preset"
        self._attr_unique_id = f"{coordinator.macAddress()}_active_user_select"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.macAddress())},
            manufacturer=MANUFACTURER,
            configuration_url="http://" + coordinator.getConf(CONF_HOST),
            name=DEFAULT_NAME,
            model=MODEL,
            hw_version=self.coordinator.firmwareVersion(),
            sw_version=self.coordinator.firmwareVersion(),
        )
        self._options_map = {}
        self._update_options()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_options()

        user_id = str(self.coordinator.getValue("CurrentUser", "0"))
        if user_id == "0":
            self._attr_current_option = "System Default"
        else:
            self._attr_current_option = self._options_map.get(
                user_id, f"User {user_id}"
            )

        super()._handle_coordinator_update()

    def _update_options(self):
        opts = []
        opts_map = {}
        for i in range(1, 7):
            if (
                str(self.coordinator.getValue(f"user_{i}_enabled", "false")).lower()
                == "true"
            ):
                name = self.coordinator.getValue(f"user_{i}", f"User {i}")
                opts.append(name)
                opts_map[str(i)] = name

        self._options_map = opts_map
        if "System Default" not in opts:
            opts.insert(0, "System Default")
        self._attr_options = opts

    async def async_select_option(self, option: str) -> None:
        """Change the selected active profile."""
        if option == "System Default":
            await self.coordinator.stop_user()
        else:
            user_id = next(
                (k for k, v in self._options_map.items() if v == option), "1"
            )
            await self.coordinator.start_user(int(user_id))

        await self.coordinator.async_request_post_command_refresh()
