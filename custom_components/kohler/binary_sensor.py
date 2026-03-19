"""Kohler Binary Sensor Integration"""

import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import CONF_HOST, EntityCategory

from .const import DOMAIN, MANUFACTURER, MODEL, DEFAULT_NAME
from .coordinator import KohlerDataUpdateCoordinator
from .entity_helpers import OutletDescriptor, build_outlet_descriptors

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config, add_entities):
    """Set up the Kohler BinarySensorEntity platform."""
    coordinator: KohlerDataUpdateCoordinator = hass.data[DOMAIN]

    sensors = []
    mac = coordinator.macAddress()
    outlet_descriptors = {
        (descriptor.valve, descriptor.outlet): descriptor
        for descriptor in build_outlet_descriptors(coordinator)
    }

    # Valves and Outlets
    for valve in range(1, 3):
        if coordinator.isValveInstalled(valve):
            valve_id = f"valve{valve}"
            uid = f"{mac}_{valve_id}"
            sensors.append(
                KohlerBinarySensor(
                    coordinator,
                    uid=uid,
                    name=f"Valve {valve} Status",
                    device_class=None,
                    icon_on="mdi:valve-open",
                    icon_off="mdi:valve-closed",
                    system_key=f"{valve_id}_Currentstatus",
                    enabled_default=False,
                    entity_category=EntityCategory.DIAGNOSTIC,
                    extra_state_attributes={
                        "valve": valve,
                        **coordinator.getValveSettingsAttributes(valve),
                    },
                )
            )

            for outlet in range(1, 7):
                if coordinator.isOutletInstalled(valve, outlet):
                    outlet_id = f"{valve_id}outlet{outlet}"
                    uid = f"{mac}_{outlet_id}"
                    sensors.append(
                        KohlerOutletBinarySensor(
                            coordinator,
                            uid=uid,
                            descriptor=outlet_descriptors[(valve, outlet)],
                            device_class=None,
                            icon_on="mdi:valve-open",
                            icon_off="mdi:valve-closed",
                        )
                    )

    # Shower Status
    sensors.append(
        KohlerBinarySensor(
            coordinator,
            uid=f"{mac}_shower",
            name="Shower Status",
            device_class=None,
            icon_on="mdi:shower",
            icon_off="mdi:shower",
            system_key=None,
            value_key="shower_on",
            is_shower=True,
        )
    )

    # Steam Status
    if coordinator.isSteamInstalled():
        sensors.append(
            KohlerBinarySensor(
                coordinator,
                uid=f"{mac}_steam",
                name="Steam Status",
                device_class="moisture",
                icon_on="mdi:radiator",
                icon_off="mdi:radiator-disabled",
                system_key=None,
                value_key="steam_running",
            )
        )

    add_entities(sensors)


class KohlerBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of a single binary sensor in a Kohler device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: KohlerDataUpdateCoordinator,
        uid: str,
        name: str,
        device_class: str | None,
        icon_on: str,
        icon_off: str,
        system_key: str | None = None,
        value_key: str | None = None,
        is_shower: bool = False,
        *,
        enabled_default: bool = True,
        entity_category: EntityCategory | None = None,
        extra_state_attributes: dict | None = None,
    ):
        """Initialize a Kohler binary sensor."""
        super().__init__(coordinator)
        self.coordinator: KohlerDataUpdateCoordinator = coordinator
        self._uid = uid
        self._attr_name = name
        self._attr_device_class = device_class
        self._icon_on = icon_on
        self._icon_off = icon_off
        self._system_key = system_key
        self._value_key = value_key
        self._is_shower = is_shower
        self._attr_is_on = False
        self._attr_entity_registry_enabled_default = enabled_default
        self._attr_entity_category = entity_category
        self._extra_state_attributes = extra_state_attributes or {}

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
        if self._is_shower:
            self._attr_is_on = self.coordinator.isShowerOn()
        elif self._system_key:
            state = self.coordinator.getSystemInfo(self._system_key)
            self._attr_is_on = state is True or state == "True" or state == "On"
        elif self._value_key:
            state = self.coordinator.getValue(self._value_key)
            self._attr_is_on = state is True or state == "True" or state == "On"

        super()._handle_coordinator_update()

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._uid

    @property
    def icon(self):
        """Get the icon to use in the front end."""
        if self.is_on:
            return self._icon_on
        return self._icon_off

    @property
    def extra_state_attributes(self):
        """Return extra sensor attributes."""
        return self._extra_state_attributes or None


class KohlerOutletBinarySensor(KohlerBinarySensor):
    """Representation of an outlet binary sensor."""

    def __init__(
        self,
        coordinator: KohlerDataUpdateCoordinator,
        uid: str,
        descriptor: OutletDescriptor,
        device_class: str | None,
        icon_on: str,
        icon_off: str,
    ):
        super().__init__(
            coordinator,
            uid,
            f"{descriptor.display_name} Status",
            device_class,
            icon_on,
            icon_off,
            enabled_default=False,
            entity_category=EntityCategory.DIAGNOSTIC,
            extra_state_attributes={
                **descriptor.state_attributes,
                **coordinator.getValveSettingsAttributes(descriptor.valve),
            },
        )
        self._valve = descriptor.valve
        self._outlet = descriptor.outlet

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_is_on = self.coordinator.isOutletOn(
            self._valve, self._outlet
        ) and self.coordinator.isValveOn(self._valve)

        # We need to manually call the parent of KohlerBinarySensor here,
        # which is CoordinatorEntity._handle_coordinator_update
        super(KohlerBinarySensor, self)._handle_coordinator_update()
