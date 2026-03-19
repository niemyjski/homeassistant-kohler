"""Sensor platform for Kohler integration."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.const import CONF_HOST, EntityCategory
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL, DEFAULT_NAME
from .coordinator import KohlerDataUpdateCoordinator

VERSION_SENSORS = [
    ("User Interface 1 Graphics", "amulet_version_string"),
    ("User Interface 1 OS", "coproc_version_string"),
    ("User Interface 1 Language", "language_version_string"),
    ("User Interface 1 TouchPanel", "touch_version_string"),
    ("Valve 1", "valve_1_version_string"),
    ("Valve 2", "valve_2_version_string"),
    ("Controller", "controller_version_string"),
]

CONNECTION_STATUS_SENSORS = [
    ("Interface 1 Connection", "ui1_con_string", "mdi:tablet-dashboard"),
    ("Interface 2 Connection", "ui2_con_string", "mdi:tablet-dashboard"),
    ("Interface 3 Connection", "ui3_con_string", "mdi:translate"),
    ("Valve 1 Connection", "valve_1_con_string", "mdi:valve"),
    ("Valve 2 Connection", "valve_2_con_string", "mdi:valve"),
    ("Controller Connection", "controller_con_string", "mdi:chip"),
    ("Music Module Connection", "music_module_con_string", "mdi:music"),
    ("Lighting Connection", "lighting_con_string", "mdi:lightbulb"),
    ("Steam Connection", "steam_con_string", "mdi:radiator"),
    ("Amplifier Connection", "amp_con_string", "mdi:amplifier"),
    ("WaterTile 1 Connection", "watertile_con_string", "mdi:shower"),
    ("WaterTile 2 Connection", "watertile2_con_string", "mdi:shower"),
]


async def async_setup_entry(hass, config, add_entities):
    """Set up the Kohler Sensor platform."""
    coordinator: KohlerDataUpdateCoordinator = hass.data[DOMAIN]

    sensors = []
    for name, key in VERSION_SENSORS:
        val = coordinator.getValue(key, "not_seen")
        if val and val != "not_seen":
            sensors.append(KohlerVersionSensor(coordinator, name, key))

    for name, key, icon in CONNECTION_STATUS_SENSORS:
        if coordinator.getConnectionStatus(key) is not None:
            sensors.append(KohlerConnectionStatusSensor(coordinator, name, key, icon))

    for valve in range(1, 3):
        if (
            coordinator.isValveInstalled(valve)
            and coordinator.getCalibrationCode(valve) is not None
        ):
            sensors.append(KohlerCalibrationCodeSensor(coordinator, valve))

    add_entities(sensors)


class KohlerVersionSensor(CoordinatorEntity, SensorEntity):
    """Representation of the Kohler firmware diagnostic sensor."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:source-branch"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: KohlerDataUpdateCoordinator, name: str, key: str):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._attr_name = f"{name} Firmware"
        self._attr_unique_id = f"{coordinator.macAddress()}_{key}"
        self._key = key

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
        self._attr_native_value = self.coordinator.getValue(self._key, "Unknown")
        super()._handle_coordinator_update()


class KohlerConnectionStatusSensor(CoordinatorEntity, SensorEntity):
    """Representation of a translated connection diagnostic sensor."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: KohlerDataUpdateCoordinator,
        name: str,
        key: str,
        icon: str,
    ):
        """Initialize the connection status sensor."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.macAddress()}_{key}"
        self._key = key
        self._connected_icon = icon

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
        self._attr_native_value = self.coordinator.getConnectionStatus(self._key)
        super()._handle_coordinator_update()

    @property
    def icon(self):
        """Return an icon matching the translated connection state."""
        if self.native_value == "Connected":
            return self._connected_icon
        if self.native_value == "Intermittent":
            return "mdi:lan-pending"
        if self.native_value == "Disconnected":
            return "mdi:lan-disconnect"
        return "mdi:lan"


class KohlerCalibrationCodeSensor(CoordinatorEntity, SensorEntity):
    """Representation of a six-port valve calibration code sensor."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:tune-variant"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: KohlerDataUpdateCoordinator, valve: int):
        """Initialize the calibration code sensor."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._valve = valve
        self._attr_name = f"Valve {valve} Calibration Code"
        self._attr_unique_id = f"{coordinator.macAddress()}_v{valve}_cal_code"

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
        self._attr_native_value = self.coordinator.getCalibrationCode(self._valve)
        super()._handle_coordinator_update()
