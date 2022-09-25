from datetime import timedelta
from typing import Optional, Union

import homeassistant.helpers.config_validation as cv
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
import voluptuous as vol
from homeassistant.const import CONF_HOST, TEMP_CELSIUS, TEMP_FAHRENHEIT
from homeassistant.helpers import discovery
from homeassistant.util import Throttle

import requests
from requests.exceptions import HTTPError, ConnectTimeout

from kohler import Kohler

import logging

_LOGGER = logging.getLogger(__name__)

from .const import CONF_ACCEPT_LIABILITY_TERMS, DOMAIN, DATA_KOHLER

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=5)

NOTIFICATION_TITLE = "Kohler Setup"
NOTIFICATION_ID = "kohler_notification"

# Validation of the user's configuration
CONFIG_SCHEMA = vol.Schema(
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

    return await hass.async_add_executor_job(initialize_integration, hass, entry.data)
    # (initialize_integration(hass, entry.data)


def setup(hass, config):
    # Config flow is done separately
    if DOMAIN not in config:
        return True

    conf = config[DOMAIN]

    return initialize_integration(hass, conf)


def initialize_integration(hass, conf):

    if not conf.get(CONF_ACCEPT_LIABILITY_TERMS):
        _LOGGER.error(
            "Unable to setup Kohler integration. You will need to read and accept the Waiver Of liability."
        )
        hass.components.persistent_notification.create(
            "Please read and accept the Waiver Of liability.",
            title=NOTIFICATION_TITLE,
            notification_id=NOTIFICATION_ID,
        )
        return False

    host: str = conf.get(CONF_HOST)
    try:
        api = Kohler(kohlerHost=host)
        data = KohlerData(hass, api)

        hass.data[DATA_KOHLER] = data
    except (ConnectTimeout, HTTPError) as ex:
        _LOGGER.error("Unable to connect to Kohler service: %s", str(ex))
        hass.components.persistent_notification.create(
            "Error: {}<br />"
            "You will need to restart hass after fixing."
            "".format(ex),
            title=NOTIFICATION_TITLE,
            notification_id=NOTIFICATION_ID,
        )
        return False

    for component in ["binary_sensor", "water_heater"]:
        discovery.load_platform(hass, component, DOMAIN, {}, conf)

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
        stateOn: Union[str, bool, int, float],
        iconOn: str,
        iconOff: str,
        name: str,
        installed: bool,
        systemKey: str = None,
        valueKey: str = None,
    ):
        super().__init__(id, deviceId, name, installed)
        self.deviceClass = deviceClass
        self.stateOn = stateOn
        self.state = False
        self.iconOn = iconOn
        self.iconOff = iconOff
        self.systemKey = systemKey
        self.valueKey = valueKey


class KohlerData:
    """Kohler data object."""

    def __init__(self, hass, api: Kohler):
        """Init Kohler data object."""
        self._hass = hass
        self._api = api
        self._lights = self._getLights()
        self._binarySensors = self._getBinarySensors()
        self._values = {}
        self._sysInfo = {}
        self._values = self._api.values()

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def _updateValues(self):
        try:
            self._values = self._api.values()
            _LOGGER.debug("Updated values")
        except (ConnectTimeout, HTTPError) as ex:
            _LOGGER.error("Unable to update values: %s", str(ex))

    def getValue(self, key: str, defaultValue=None):
        self._updateValues()
        return defaultValue if key not in self._values else self._values[key]

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def _updateSystemInfo(self):
        try:
            self._sysInfo = self._api.systemInfo()
            _LOGGER.debug("Updated system info")
        except (ConnectTimeout, HTTPError) as ex:
            _LOGGER.error("Unable to update  system info: %s", str(ex))

    def getSystemInfo(self, key, defaultValue=None):
        self._updateSystemInfo()
        return defaultValue if key not in self._sysInfo else self._sysInfo[key]

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
            sensors.append(
                KohlerDataBinarySensor(
                    self.macAddress() + valveId,
                    self.macAddress() + valveId,
                    None,
                    "On",
                    "mdi:valve-open",
                    "mdi:valve-closed",
                    f"Kohler Valve {valve}",
                    self.isValveInstalled(valve),
                    f"valve{valve}_Currentstatus",
                )
            )

            for outlet in range(1, 7):
                outletId = f"{valveId}outlet{outlet}"
                sensors.append(
                    KohlerDataBinarySensor(
                        self.macAddress() + outletId,
                        self.macAddress() + outletId,
                        None,
                        "On",
                        "mdi:valve-open",
                        "mdi:valve-closed",
                        f"Kohler Valve {valve} Outlet {outlet}",
                        self.isOutletInstalled(valve, outlet),
                        outletId,
                    )
                )

        sensors.append(
            KohlerDataBinarySensor(
                self.macAddress() + "shower",
                self.macAddress() + "shower",
                None,
                True,
                "mdi:shower",
                "mdi:shower",
                f"Kohler Shower Status",
                True,
                None,
                "shower_on",
            )
        )

        sensors.append(
            KohlerDataBinarySensor(
                self.macAddress() + "steam",
                self.macAddress() + "steam",
                "moisture",
                True,
                "mdi:radiator",
                "mdi:radiator-disabled",
                f"Kohler Steam Status",
                self.isSteamInstalled(),
                None,
                "steam_running",
            )
        )

        for sensor in sensors:
            self.updateBinarySensor(sensor)

        return sensors

    def updateBinarySensor(self, sensor: KohlerDataBinarySensor):
        state = None

        if sensor.systemKey:
            state = self.getSystemInfo(sensor.systemKey)
        elif sensor.valueKey:
            state = self.getValue(sensor.valueKey)

        sensor.state = state == sensor.stateOn

    def unitOfMeasurement(self):
        unit = self.getSystemInfo("degree_symbol")
        if unit == "&degF":
            return TEMP_FAHRENHEIT

        return TEMP_CELSIUS

    def macAddress(self):
        return self.getValue("MAC")

    def getInstalledValveOutlets(self, valve: int = 1):
        outletCount = int(self.getValue(f"valve{valve}PortsAvailable", 0))
        if outletCount < 1:
            return 0

        outlets = ""
        for outlet in range(1, outletCount):
            # NOTE: Turn on last used outlets for now.
            if self.isOutletOn(valve, outlet):
                outlets += str(outlet)

        return 0 if not outlets else int(outlets)

    def isSteamInstalled(self) -> bool:
        return self.getValue("steam_installed", False)

    def isValveInstalled(self, valve: int) -> bool:
        return self.getValue(f"valve{valve}_installed", False)

    def isOutletInstalled(self, valve: int, outlet: int) -> bool:
        return self.getValue(f"valve{valve}_outlet{outlet}_func") is not None

    def isOutletOn(self, valve: int, outlet: int) -> bool:
        return self.getSystemInfo(f"valve{valve}outlet{outlet}", False)

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

            temp = self.getSystemInfo(f"valve{valve}Setpoint")
            if temp is not None:
                temps.append(float(temp))

        if len(temps) == 0:
            return self.getValue("def_temp")
        else:
            return max(temps)

    def setTargetTemperature(self, temperature):
        for valve in range(1, 2):
            if not self.isValveInstalled(valve):
                continue

            self._api.saveVariable(38, temperature, valve=valve)

    def isShowerOn(self) -> bool:
        return self.getValue("shower_on", False)

    def turnOnShower(self, temp=None):
        # TODO: Do a better job at selecting valves and support steam.
        valve1Outlets = self.getInstalledValveOutlets(1)
        valve2Outlets = self.getInstalledValveOutlets(2)
        if temp is None:
            temp = self.getTargetTemperature()

        self._api.quickShower(1, valve1Outlets, 0, temp, valve2Outlets, 0, temp)

    def turnOffShower(self):
        self._api.stopShower()
