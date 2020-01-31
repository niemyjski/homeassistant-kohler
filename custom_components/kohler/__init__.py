from datetime import timedelta
import homeassistant.helpers.config_validation as cv
import logging
import requests
import voluptuous as vol
from homeassistant.const import (
    CONF_HOST,
    TEMP_CELSIUS,
    TEMP_FAHRENHEIT
)
from homeassistant.helpers import discovery
from homeassistant.util import Throttle
from requests.exceptions import HTTPError, ConnectTimeout

_LOGGER = logging.getLogger(__name__)

DOMAIN = "kohler"
DATA_KOHLER = "kohler"
MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=5)

NOTIFICATION_TITLE = "Kohler Setup"
NOTIFICATION_ID = "kohler_notification"

# Validation of the user's configuration
CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_HOST): cv.string
    })
}, extra=vol.ALLOW_EXTRA)


def setup(hass, config):
    from kohler import Kohler

    conf = config[DOMAIN]
    host = conf.get(CONF_HOST)

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
            notification_id=NOTIFICATION_ID
        )
        return False

    for component in ["binary_sensor", "light", "water_heater"]:
        discovery.load_platform(hass, component, DOMAIN, {}, config)

    return True


class KohlerData:
    """Kohler data object."""

    def __init__(self, hass, api):
        """Init Kohler data object."""
        self._hass = hass
        self._api = api
        self._lights = self._getLights()
        self._binarySensors = self._getBinarySensors()
        self._values = {}
        self._sysInfo = {}

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def _updateValues(self):
        try:
            self._values = self._api.values()
            _LOGGER.debug("Updated values")
        except (ConnectTimeout, HTTPError) as ex:
            _LOGGER.error("Unable to update values: %s", str(ex))

    def getValue(self, key, defaultValue=None):
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

    @property
    def binarySensors(self):
        """Return a list of binary sensors."""
        return self._binarySensors

    def _getLights(self):
        lights = []
        for lightId in range(1, 3):
            lights.append(KohlerLight(lightId, f"light{lightId}"))

        for light in lights:
            self.updateLight(light)

        return lights

    def updateLight(self, light):
        installedKey = f"{light.deviceId}_installed"
        light.installed = self.getValue(installedKey, defaultValue=False)
        light.name = "Kohler " + self.getValue(f"{light.deviceId}_name")
        light.brightness = self.getValue(f"{light.deviceId}_level", 100)

    def _getBinarySensors(self):
        sensors = []
        for valve in range(1, 2):
            valveId = f"valve{valve}"
            sensors.append(KohlerBinarySensor(
                valveId,
                valveId,
                None,
                "On",
                "mdi:valve-open",
                "mdi:valve-closed",
                f"Kohler Valve {valve}",
                self.isValveInstalled(valve),
                f"valve{valve}_Currentstatus"
            ))

            for outlet in range(1, 6):
                outletId = f"{valveId}outlet{outlet}"
                sensors.append(KohlerBinarySensor(
                    outletId,
                    outletId,
                    None,
                    "On",
                    "mdi:valve-open",
                    "mdi:valve-closed",
                    f"Kohler Valve {valve} Outlet {outlet}",
                    self.isOutletInstalled(valve, outlet),
                    outletId
                ))

        sensors.append(KohlerBinarySensor(
            "shower",
            "shower",
            None,
            True,
            "mdi:shower",
            "mdi:shower",
            f"Kohler Shower Status",
            True,
            None,
            "shower_on"
        ))

        sensors.append(KohlerBinarySensor(
            "steam",
            "steam",
            "moisture",
            True,
            "mdi:radiator",
            "mdi:radiator-disabled",
            f"Kohler Steam Status",
            self.isSteamInstalled(),
            None,
            "steam_running"
        ))

        for sensor in sensors:
            self.updateBinarySensor(sensor)

        return sensors

    def updateBinarySensor(self, sensor):
        state = None
        if sensor.systemKey:
            state = self.getSystemInfo(sensor.systemKey)
        else:
            state = self.getValue(sensor.valueKey)
        sensor.state = state == sensor.stateOn

    def unitOfMeasurement(self):
        unit = self.getSystemInfo("degree_symbol")
        if unit == "&degF":
            return TEMP_FAHRENHEIT

        return TEMP_CELSIUS

    def getInstalledValveOutlets(self, valve=1):
        outletCount = int(self.getValue(f"valve{valve}PortsAvailable", 0))
        if outletCount < 1:
            return 0

        outlets = ""
        for outlet in range(1, outletCount):
            # NOTE: Turn on last used outlets for now.
            if self.isOutletOn(valve, outlet):
                outlets += str(outlet)

        return 0 if not outlets else int(outlets)

    def isSteamInstalled(self):
        return self.getValue("steam_installed", False)

    def isValveInstalled(self, valve):
        return self.getValue(f"valve{valve}_installed", False)

    def isOutletInstalled(self, valve, outlet):
        return self.getValue(f"valve{valve}_outlet{outlet}_func") is not None

    def isOutletOn(self, valve, outlet):
        return self.getSystemInfo(f"valve{valve}outlet{outlet}", False)

    def getCurrentTemperature(self):
        temps = []
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

    def getTargetTemperature(self):
        temps = []
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

    def isShowerOn(self):
        return self.getValue("shower_on", False)

    def turnOnShower(self, temp=None):
        # TODO: Do a better job at selecting valves and support steam.
        valve1Outlets = self.getInstalledValveOutlets(1)
        valve2Outlets = self.getInstalledValveOutlets(2)
        if temp is None:
            temp = self.getTargetTemperature()

        self._api.quickShower(
            1, valve1Outlets, 0, temp, valve2Outlets, 0, temp
        )

    def turnOffShower(self):
        self._api.stopShower()


class KohlerEntity():
    def __init__(self, id, deviceId, name=None, installed=None):
        self.id = id
        self.deviceId = deviceId
        self.name = name
        self.installed = installed


class KohlerLight(KohlerEntity):
    def __init__(self, id, deviceId, name=None, installed=None):
        super().__init__(id, deviceId, name, installed)
        self.brightness = None


class KohlerBinarySensor(KohlerEntity):
    def __init__(
        self,
        id,
        deviceId,
        deviceClass,
        stateOn,
        iconOn,
        iconOff,
        name,
        installed,
        systemKey = None,
        valueKey = None
    ):
        super().__init__(id, deviceId, name, installed)
        self.deviceClass = deviceClass
        self.stateOn = stateOn
        self.state = None
        self.iconOn = iconOn
        self.iconOff = iconOff
        self.systemKey = systemKey
        self.valueKey = valueKey
