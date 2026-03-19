"""Kohler Integration"""

import logging
import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers import entity_registry as er

from kohler import Kohler

from .const import (
    CONF_ACCEPT_LIABILITY_TERMS,
    DATA_KOHLER,
    DEFAULT_NAME,
    DOMAIN,
    MANUFACTURER,
    MODEL,
)
from .coordinator import KohlerDataUpdateCoordinator
from .entity_helpers import build_outlet_descriptors, normalize_mac_address

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.LIGHT,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.VALVE,
    Platform.WATER_HEATER,
]

NOTIFICATION_TITLE = "Kohler Setup"
NOTIFICATION_ID = "kohler_notification"

CONFIG_SCHEMA = vol.Schema(
    cv.deprecated(DOMAIN),
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_HOST): cv.string,
                vol.Required(CONF_ACCEPT_LIABILITY_TERMS): cv.boolean,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Kohler component."""
    if DOMAIN not in config:
        return True

    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data=config[DOMAIN],
        )
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Kohler from a config entry."""
    if not entry.data.get(CONF_ACCEPT_LIABILITY_TERMS):
        _LOGGER.error(
            "Unable to setup Kohler integration. You will need to read and accept the Waiver Of liability."
        )
        hass.components.persistent_notification.create(
            "Please read and accept the Waiver Of liability.",
            title=NOTIFICATION_TITLE,
            notification_id=NOTIFICATION_ID,
        )
        return False

    host: str = entry.data.get(CONF_HOST)
    api = Kohler(kohler_host=host, timeout=10.0)

    coordinator = KohlerDataUpdateCoordinator(hass, api=api, conf=entry)

    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady as ex:
        raise ConfigEntryNotReady(f"Timeout while connecting to {host}") from ex

    hass.data.setdefault(DOMAIN, {})
    hass.data[DATA_KOHLER] = coordinator

    normalized_mac = normalize_mac_address(coordinator.macAddress())
    if normalized_mac is not None:
        dr.async_get(hass).async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, normalized_mac)},
            connections={(CONNECTION_NETWORK_MAC, normalized_mac)},
            manufacturer=MANUFACTURER,
            configuration_url=f"http://{host}",
            model=MODEL,
            name=DEFAULT_NAME,
            hw_version=coordinator.firmwareVersion(),
            sw_version=coordinator.firmwareVersion(),
        )
        if entry.unique_id != normalized_mac:
            hass.config_entries.async_update_entry(entry, unique_id=normalized_mac)

    _async_update_outlet_entity_names(hass, entry, coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _async_delayed_refresh(_now):
        await coordinator.async_request_refresh()

    async_call_later(hass, 2, _async_delayed_refresh)

    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate older config entries and entity IDs."""
    if entry.version > 3:
        _LOGGER.error("Unsupported config entry version %s", entry.version)
        return False

    if entry.version == 1:
        entity_registry = er.async_get(hass)

        for entity_entry in er.async_entries_for_config_entry(
            entity_registry, entry.entry_id
        ):
            if (
                entity_entry.platform == DOMAIN
                and entity_entry.domain == Platform.CLIMATE.value
                and entity_entry.unique_id.endswith("_thermostat")
            ):
                new_entity_id = entity_registry.async_generate_entity_id(
                    Platform.CLIMATE.value,
                    "kohler_shower",
                    current_entity_id=entity_entry.entity_id,
                )
                entity_registry.async_update_entity(
                    entity_entry.entity_id,
                    new_entity_id=new_entity_id,
                    original_name="Shower",
                )

        hass.config_entries.async_update_entry(entry, version=2)

    if entry.version == 2:
        hass.config_entries.async_update_entry(entry, version=3)

    return True


def _async_update_outlet_entity_names(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: KohlerDataUpdateCoordinator,
) -> None:
    """Refresh entity registry metadata for existing Kohler entities."""
    entity_registry = er.async_get(hass)
    desired_names: dict[tuple[str, str], str] = {}
    desired_light_unique_ids: dict[str, str] = {}
    mac = coordinator.macAddress()
    sensor_unique_ids_to_remove = {f"{mac}_device_time"}

    for descriptor in build_outlet_descriptors(coordinator):
        unique_id = f"{mac}_valve{descriptor.valve}outlet{descriptor.outlet}"
        desired_names[(Platform.VALVE.value, unique_id)] = descriptor.display_name
        desired_names[(Platform.BINARY_SENSOR.value, unique_id)] = (
            f"{descriptor.display_name} Status"
        )

    for light_id in range(1, 3):
        legacy_unique_id = f"light{light_id}"
        if coordinator.getValue(f"{legacy_unique_id}_installed", False):
            desired_light_unique_ids[legacy_unique_id] = f"{mac}_{legacy_unique_id}"

    for entity_entry in er.async_entries_for_config_entry(
        entity_registry, entry.entry_id
    ):
        if (
            entity_entry.platform == DOMAIN
            and entity_entry.domain == Platform.SENSOR.value
            and entity_entry.unique_id in sensor_unique_ids_to_remove
        ):
            entity_registry.async_remove(entity_entry.entity_id)
            continue

        if (
            entity_entry.platform == DOMAIN
            and entity_entry.domain == Platform.LIGHT.value
            and (new_unique_id := desired_light_unique_ids.get(entity_entry.unique_id))
            and entity_entry.unique_id != new_unique_id
        ):
            entity_registry.async_update_entity(
                entity_entry.entity_id,
                new_unique_id=new_unique_id,
            )
            continue

        desired_name = desired_names.get((entity_entry.domain, entity_entry.unique_id))
        if (
            entity_entry.platform != DOMAIN
            or desired_name is None
            or entity_entry.name is not None
            or entity_entry.original_name == desired_name
        ):
            continue

        entity_registry.async_update_entity(
            entity_entry.entity_id,
            original_name=desired_name,
        )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        if DATA_KOHLER in hass.data:
            hass.data.pop(DATA_KOHLER)
    return unload_ok
