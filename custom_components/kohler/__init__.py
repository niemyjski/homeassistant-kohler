"""Kohler Integration"""

import logging

from datetime import timedelta
from typing import Optional

import async_timeout
import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_HOST, Platform, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from kohler import Kohler

from requests.exceptions import ConnectTimeout, HTTPError

from .const import CONF_ACCEPT_LIABILITY_TERMS, DATA_KOHLER, DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.SWITCH,
    Platform.WATER_HEATER,
]

MIN_TIME_BETWEEN_VALUE_UPDATES = timedelta(seconds=20)
MIN_TIME_BETWEEN_SYSTEM_UPDATES = timedelta(seconds=2)

NOTIFICATION_TITLE = "Kohler Setup"
NOTIFICATION_ID = "kohler_notification"

# Validation of the user's configuration
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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Kohler DTV from a config entry."""
    _LOGGER.debug("Setting up Kohler integration.")

    try:
        result = await hass.async_add_executor_job(
            initialize_integration,
            hass,
            entry,
        )
        if result:
            await hass.data[DATA_KOHLER].async_config_entry_first_refresh()
            await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
            return result
    except Exception as ex:
        _LOGGER.error("Error while setting up Kohler integration %s", ex)

    raise ConfigEntryNotReady(
        f"Timeout while connecting to {entry.data.get(CONF_HOST)}"
    )


async def async_setup(hass, config):
    # Config flow is done separately
    if DOMAIN not in config:
        return bool(hass.config_entries.async_entries(DOMAIN))
    # Create the entry from the config
    if not hass.config_entries.async_entries(DOMAIN):
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_IMPORT},
                data=config[DOMAIN],
            )
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data.pop(DOMAIN)
    return unload_ok


def initialize_integration(hass: HomeAssistant, conf: ConfigEntry):
    # In config flow, this should never happen
    if not conf.data.get(CONF_ACCEPT_LIABILITY_TERMS):
        _LOGGER.error(
            "Unable to setup Kohler integration. You will need to read and accept the Waiver Of liability."
        )
        hass.components.persistent_notification.create(
            "Please read and accept the Waiver Of liability.",
            title=NOTIFICATION_TITLE,
            notification_id=NOTIFICATION_ID,
        )
        return False

    host: str = conf.data.get(CONF_HOST)
    try:
        api = Kohler(kohlerHost=host)
        data = KohlerData(hass, api, conf)

        hass.data[DATA_KOHLER] = data
    except (ConnectTimeout, HTTPError) as ex:
        _LOGGER.error("Unable to connect to Kohler service: %s", str(ex))
        hass.components.persistent_notification.create(
            "Error: {}<br />" "You will need to restart hass after fixing." "".format(
                ex
            ),
            title=NOTIFICATION_TITLE,
            notification_id=NOTIFICATION_ID,
        )
        return False

    return True


class KohlerDataEntity:
    def __init__(
        self, id: str, deviceId: str, name: str = None, installed: bool = False
    ):
        self.id = id
        self.deviceId = deviceId
        self.name = name
        self.installed = installed


class KohlerDataLight(KohlerDataEntity):
    def __init__(
        self, id: str, deviceId: str, name: str = None, installed: bool = False
    ):
        super().__init__(id, deviceId, name, installed)
        self.brightness = 0


class KohlerDataBinarySensor(KohlerDataEntity):
    def __init__(
        self,
        id: str,
        deviceId: str,
        deviceClass: Optional[str],
        iconOn: str,
        iconOff: str,
        name: str,
        installed: bool,
        systemKey: str = None,
        valueKey: str = None,
    ):
        super().__init__(id, deviceId, name, installed)
        self.deviceClass = deviceClass
        self.state = False
        self.iconOn = iconOn
        self.iconOff = iconOff
        self.systemKey = systemKey
        self.valueKey = valueKey


class KohlerDataOutletBinarySensor(KohlerDataBinarySensor):
    def __init__(
        self,
        id: str,
        deviceId: str,
        deviceClass: Optional[str],
        iconOn: str,
        iconOff: str,
        name: str,
        installed: bool,
        valve: int,
        outlet: int,
        systemKey: str = None,
        valueKey: str = None,
    ):
        super().__init__(
            id,
            deviceId,
            deviceClass,
            iconOn,
            iconOff,
            name,
            installed,
            systemKey,
            valueKey,
        )
        self.valve = valve
        self.outlet = outlet


class KohlerData(DataUpdateCoordinator):
    """Kohler data object."""

    def __init__(self, hass, api: Kohler, conf):
        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="Kohler Data Coordinator",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=20),
            # Set always_update to `False` if the data returned from the
            # api can be compared via `__eq__` to avoid duplicate updates
            # being dispatched to listeners
            always_update=True,
            config_entry=conf,
        )

        """Init Kohler data object."""
        self._hass = hass
        self._api = api
        self._conf = conf.data
        self._sysInfo = {}
        self._target_temperature = None
        self._valve1_outlet_mappings = []
        self._valve2_outlet_mappings = []

    async def _async_setup(self):
        """Set up the coordinator

        This is the place to set up your coordinator,
        or to load data, that only needs to be loaded once.

        This method will be called automatically during
        coordinator.async_config_entry_first_refresh.
        """
        await self._hass.async_add_executor_job(self.update)

        self._lights = self._getLights()
        self._binarySensors = self._getBinarySensors()

    async def _async_update_data(self):
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        try:
            # Note: asyncio.TimeoutError and aiohttp.ClientError are already
            # handled by the data update coordinator.
            async with async_timeout.timeout(10):
                return await self._hass.async_add_executor_job(self.update)
        except (ConnectTimeout, HTTPError) as err:
            raise UpdateFailed(f"Error communicating with API: {err}")

    def update(self):
        self._updateValues()
        self._updateSystemInfo()
        self._mapOutlets()

    def _updateValues(self):
        try:
            self._values = self._api.values()
            _LOGGER.debug("Updated values %s", self._values)
        except (ConnectTimeout, HTTPError) as ex:
            _LOGGER.error("Unable to update values: %s", str(ex))

    def _mapOutlets(self):
        """Map the outlets to the order on the UI."""
        valve1_port_count = int(self.getValue("valve1PortsAvailable"))
        valve2_port_count = int(self.getValue("valve2PortsAvailable"))
        _valve1_outlet_mappings = [0] * valve1_port_count
        _valve2_outlet_mappings = [0] * valve2_port_count

        if valve1_port_count > 0:
            for port_num in range(1, valve1_port_count + 1):
                _valve1_outlet_mappings[port_num - 1] = self.getValue(
                    f"valve1_outlet{port_num}_func"
                )["id"]

        if valve2_port_count > 0:
            for port_num in range(1, valve2_port_count + 1):
                _valve2_outlet_mappings[port_num - 1] = self.getValue(
                    f"valve2_outlet{port_num}_func"
                )["id"]

        self._valve1_outlet_mappings = _valve1_outlet_mappings
        self._valve2_outlet_mappings = _valve2_outlet_mappings

    def getConf(self, key: str):
        return self._conf[key]

    def getValue(self, key: str, defaultValue=None):
        return defaultValue if key not in self._values else self._values[key]

    def _updateSystemInfo(self):
        try:
            self._sysInfo = self._api.systemInfo()
            _LOGGER.debug("Updated system info %s", self._sysInfo)
        except (ConnectTimeout, HTTPError) as ex:
            _LOGGER.error("Unable to update  system info: %s", str(ex))

    def getSystemInfo(self, key, defaultValue=None):
        return defaultValue if key not in self._sysInfo else self._sysInfo[key]

    def setSystemInfo(self, key, value):
        self._sysInfo[key] = value

    @property
    def lights(self):
        """Return a list of lights."""
        return self._lights

    def _getLights(self):
        lights: list[KohlerDataLight] = []
        for lightId in range(1, 3):
            lights.append(KohlerDataLight(str(lightId), f"light{lightId}"))

        for light in lights:
            self.updateLight(light)

        return lights

    def updateLight(self, light: KohlerDataLight):
        installedKey = f"{light.deviceId}_installed"
        light.installed = self.getValue(installedKey, defaultValue=False)
        light.name = "Kohler " + self.getValue(f"{light.deviceId}_name")
        light.brightness = self.getValue(f"{light.deviceId}_level", 100)

    def turnlightOn(self, lightId: str, intensity: int):
        self._api.lightOn(int(lightId), intensity)

    def turnlightOff(self, lightId: str):
        self._api.lightOff(int(lightId))

    @property
    def binarySensors(self):
        """Return a list of binary sensors."""
        return self._binarySensors

    def _getBinarySensors(self):
        sensors: list[KohlerDataBinarySensor] = []
        for valve in range(1, 3):
            valveId = f"valve{valve}"
            self._updateUniqueId(
                self._hass, "binary_sensor", valveId, self.macAddress() + "_" + valveId
            )
            sensors.append(
                KohlerDataBinarySensor(
                    self.macAddress() + "_" + valveId,
                    self.macAddress() + "_" + valveId,
                    None,
                    "mdi:valve-open",
                    "mdi:valve-closed",
                    f"Kohler Valve {valve}",
                    self.isValveInstalled(valve),
                    f"valve{valve}_Currentstatus",
                )
            )

            for outlet in range(1, 7):
                outletId = f"{valveId}outlet{outlet}"
                self._updateUniqueId(
                    self._hass,
                    "binary_sensor",
                    outletId,
                    self.macAddress() + "_" + outletId,
                )
                sensors.append(
                    KohlerDataOutletBinarySensor(
                        self.macAddress() + "_" + outletId,
                        self.macAddress() + "_" + outletId,
                        None,
                        "mdi:valve-open",
                        "mdi:valve-closed",
                        f"Kohler Valve {valve} Outlet {outlet}",
                        self.isOutletInstalled(valve, outlet),
                        valve,
                        outlet,
                        outletId,
                    )
                )

        self._updateUniqueId(
            self._hass, "binary_sensor", "shower", self.macAddress() + "_shower"
        )
        sensors.append(
            KohlerDataBinarySensor(
                self.macAddress() + "_shower",
                self.macAddress() + "_shower",
                None,
                "mdi:shower",
                "mdi:shower",
                "Kohler Shower Status",
                True,
                None,
                "shower_on",
            )
        )

        self._updateUniqueId(
            self._hass, "binary_sensor", "steam", self.macAddress() + "_steam"
        )
        sensors.append(
            KohlerDataBinarySensor(
                self.macAddress() + "_steam",
                self.macAddress() + "_steam",
                "moisture",
                "mdi:radiator",
                "mdi:radiator-disabled",
                "Kohler Steam Status",
                self.isSteamInstalled(),
                None,
                "steam_running",
            )
        )

        for sensor in sensors:
            self.updateBinarySensor(sensor)

        return sensors

    def _updateUniqueId(self, hass, platform, old_uid, new_uid):
        er = entity_registry.async_get(hass)
        entity_id = er.async_get_entity_id(platform, DOMAIN, old_uid)
        if entity_id is not None:
            er.async_update_entity(entity_id, new_unique_id=new_uid)

    def updateBinarySensor(self, sensor: KohlerDataBinarySensor):
        state = None
        if isinstance(sensor, KohlerDataOutletBinarySensor):
            outletSensor: KohlerDataOutletBinarySensor = sensor
            outletSensor.state = self.isOutletOn(
                outletSensor.valve, outletSensor.outlet
            )
        else:
            if sensor.systemKey:
                state = self.getSystemInfo(sensor.systemKey)
                _LOGGER.debug(
                    f"Updating system info sensor {sensor.systemKey} to {state}."
                )
            elif sensor.valueKey:
                state = self.getValue(sensor.valueKey)
                _LOGGER.debug(
                    f"Updating value key sensor {sensor.valueKey} to {state}."
                )

            sensor.state = state is True or state == "True" or state == "On"
        _LOGGER.debug(f"Sensor {sensor.id} state is {sensor.state}.")

    def unitOfMeasurement(self):
        unit = self.getSystemInfo("degree_symbol")
        if unit == "&degF":
            return UnitOfTemperature.FAHRENHEIT

        return UnitOfTemperature.CELSIUS

    def macAddress(self):
        return self.getValue("MAC")

    def firmwareVersion(self):
        return self.getValue("controller_version_string")

    def getInstalledValveOutlets(self, valve: int = 1):
        outlet_count = int(self.getValue(f"valve{valve}PortsAvailable", 0))
        if outlet_count < 1:
            return 0

        outlets = ""
        for outlet in range(1, outlet_count):
            # NOTE: Turn on last used outlets for now.
            if self.isOutletOn(valve, outlet):
                outlets += str(outlet)

        return 0 if not outlets else int(outlets)

    def getOpenValveOutlets(self, valve: int = 1):
        outlet_count = int(self.getValue(f"valve{valve}PortsAvailable", 0))
        if outlet_count < 1:
            return ""

        outlets = ""
        for outlet in range(1, outlet_count):
            if self.isOutletOn(valve, outlet):
                outlets += str(outlet)

        return outlets

    def genValveOutletOpen(self, valve: int, outletOn: int):
        outlet_count = int(self.getValue(f"valve{valve}PortsAvailable", 0))
        if outlet_count < 1:
            return ""

        outlets = ""
        for outlet in range(1, outlet_count):
            if self.isOutletOn(valve, outlet) or (outlet == outletOn):
                outlets += str(outlet)

        return outlets

    def genValveOutletClosed(self, valve: int, outletOff: int):
        outlet_count = int(self.getValue(f"valve{valve}PortsAvailable", 0))
        if outlet_count < 1:
            return ""

        outlets = ""
        for outlet in range(1, outlet_count):
            if self.isOutletOn(valve, outlet) and (outlet != outletOff):
                outlets += str(outlet)

        return outlets

    def isSteamInstalled(self) -> bool:
        return self.getValue("steam_installed", False)

    def isValveInstalled(self, valve: int) -> bool:
        return self.getValue(f"valve{valve}_installed", False)

    def isOutletInstalled(self, valve: int, outlet: int) -> bool:
        return self.getValue(f"valve{valve}_outlet{outlet}_func") is not None

    def isOutletOn(self, valve: int, outlet: int) -> bool:
        outlet_mappings = (
            self._valve1_outlet_mappings if valve == 1 else self._valve2_outlet_mappings
        )
        
        if outlet > len(outlet_mappings):
            return False
        
        mapped_outlet = outlet_mappings[outlet - 1]
        return self.getSystemInfo(f"valve{valve}outlet{mapped_outlet}", False)

    def isValveOn(self, valve: int) -> bool:
        return self.getSystemInfo(f"valve{valve}_Currentstatus", "Off") == "On"

    def getCurrentTemperature(self) -> Optional[float]:
        temps: list[float] = []
        for valve in range(1, 2):
            if not self.isValveInstalled(valve):
                continue

            temp = self.getSystemInfo(f"valve{valve}Temp")
            if temp is not None:
                temps.append(float(temp))

        if len(temps) == 0:
            return None
        else:
            return max(temps)

    def getTargetTemperature(self) -> Optional[float]:
        temps: list[float] = []
        for valve in range(1, 2):
            if not self.isValveInstalled(valve):
                continue

            if self.isValveOn(valve) or self._target_temperature is None:
                temp = self.getSystemInfo(f"valve{valve}Setpoint")
            else:
                temp = self._target_temperature

            if temp is not None:
                temps.append(float(temp))

        if len(temps) == 0:
            return self.getValue("def_temp")
        else:
            return max(temps)

    def setTargetTemperature(self, temperature):
        _LOGGER.debug("setTargetTemperature %s", temperature)
        self._target_temperature = float(temperature)

        if self.isShowerOn():
            valve1Outlets = self.getOpenValveOutlets(1)
            valve2Outlets = self.getOpenValveOutlets(2)

            self._api.quickShower(
                1, valve1Outlets, 0, temperature, valve2Outlets, 0, temperature
            )
            self._api.quickShower(
                2, valve1Outlets, 0, temperature, valve2Outlets, 0, temperature
            )

    def isShowerOn(self) -> bool:
        return self.isValveOn(1) or self.isValveOn(2)

    def turnOnShower(self, temp=None):
        _LOGGER.debug("turnOnShower %s", temp)
        valve1Outlets = self.getInstalledValveOutlets(1)
        valve2Outlets = self.getInstalledValveOutlets(2)
        if temp is None:
            temp = self.getTargetTemperature()

        self._api.quickShower(1, valve1Outlets, 0, temp, valve2Outlets, 0, temp)

    def turnOffShower(self):
        _LOGGER.debug("turnOffShower")
        self._api.stopShower()

    def openOutlet(self, valveId, outletId):
        _LOGGER.debug("openOutlet valveId=%s outletId=%s", valveId, outletId)
        valve1Outlets = (
            self.genValveOutletOpen(1, outletId)
            if valveId == 1
            else self.getOpenValveOutlets(1)
        )
        valve2Outlets = (
            self.genValveOutletOpen(2, outletId)
            if valveId == 2
            else self.getOpenValveOutlets(2)
        )

        temp = self.getTargetTemperature()

        self._api.quickShower(1, valve1Outlets, 0, temp, valve2Outlets, 0, temp)
        self._api.quickShower(2, valve1Outlets, 0, temp, valve2Outlets, 0, temp)

    def closeOutlet(self, valveId, outletId):
        _LOGGER.debug("closeOutlet valveId=%s outletId=%s", valveId, outletId)
        valve1Outlets = (
            self.genValveOutletClosed(1, outletId)
            if valveId == 1
            else self.getOpenValveOutlets(1)
        )
        valve2Outlets = (
            self.genValveOutletClosed(2, outletId)
            if valveId == 2
            else self.getOpenValveOutlets(2)
        )

        temp = self.getTargetTemperature()

        self._api.quickShower(1, valve1Outlets, 0, temp, valve2Outlets, 0, temp)
        self._api.quickShower(2, valve1Outlets, 0, temp, valve2Outlets, 0, temp)
