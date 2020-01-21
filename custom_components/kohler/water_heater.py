from homeassistant.components.water_heater import (
    STATE_OFF,
    STATE_ON,
    SUPPORT_OPERATION_MODE,
    SUPPORT_TARGET_TEMPERATURE,
    WaterHeaterDevice
)

from homeassistant.const import (
    ATTR_TEMPERATURE,
    TEMP_CELSIUS,
    TEMP_FAHRENHEIT,
    PRECISION_WHOLE
)

SUPPORT_FLAGS_HEATER = (
    SUPPORT_TARGET_TEMPERATURE | SUPPORT_OPERATION_MODE
)

import logging
DOMAIN = 'kohler'
_LOGGER = logging.getLogger(__name__)

SUPPORT_WATER_HEATER = [STATE_ON, STATE_OFF]

def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Kohler platform."""
    Kohler = hass.data[DOMAIN]["kohler"]
    values = hass.data[DOMAIN]["kohler_init_values"]
    sysInfo = hass.data[DOMAIN]["kohler_init_system_info"]

    add_entities([KohlerWaterHeater(Kohler, sysInfo, values)])


class KohlerWaterHeater(WaterHeaterDevice):
    """Representation of a demo water_heater device."""
    def __init__(self, api, sysInfo, values):
        """Initialize the water_heater device."""
        self._name = "Kohler Shower"
        self._api = api
        self._current_mode = STATE_ON if values["shower_on"] else STATE_OFF

        self._unit_of_measurement = TEMP_CELSIUS
        if sysInfo["degree_symbol"] == "&degF":
            self._unit_of_measurement = TEMP_FAHRENHEIT

        self._valve1Outlets = self.getInstalledValveOutlets(sysInfo, values, 1)
        self._valve2Outlets = self.getInstalledValveOutlets(sysInfo, values, 2)
        self._target_temperature = self.getTargetTemp(sysInfo, values)
        self._current_temperature = self.getCurrentTemp(sysInfo, values)

    def update(self):
        """Let HA know there has been an update from the Kohler API."""
        try:
            sysInfo = self._api.systemInfo()
            values = self._api.values()

            self._current_temperature = self.getCurrentTemp(sysInfo, values)
            self._target_temperature = self.getTargetTemp(sysInfo, values)
            self._current_mode = STATE_ON if values["shower_on"] else STATE_OFF
        except:
            _LOGGER.error("Unable to retrieve data from Kohler server")

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return SUPPORT_FLAGS_HEATER

    @property
    def name(self):
        """Return the name of the water_heater device."""
        return self._name

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self._unit_of_measurement

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._current_temperature

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._target_temperature

    def set_temperature(self, **kwargs):
        """Set new target temperatures."""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            self._target_temperature = temp

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return 30 if self._unit_of_measurement == TEMP_CELSIUS else 86

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return 45 if self._unit_of_measurement == TEMP_CELSIUS else 113

    @property
    def precision(self):
        """Return the precision of the system."""
        return PRECISION_WHOLE

    @property
    def current_operation(self):
        """Return current operation ie. on, off."""
        return self._current_mode

    @property
    def operation_list(self):
        """Return the list of available operation modes."""
        return SUPPORT_WATER_HEATER

    def set_operation_mode(self, operation_mode):
        """Set operation mode."""
        if operation_mode == STATE_ON:
            # TODO: Do a better job at selecting valves and support steam.
            temp = self._target_temperature
            self._api.quickShower(
                1, self._valve1Outlets, 0, temp, self._valve2Outlets, 0, temp
            )
        else:
            self._api.stopShower()

    @property
    def icon(self):
        """Get the icon to use in the front end."""
        return "mdi:shower"

    def getInstalledValveOutlets(self, sysInfo, values, valve=1):
        name = f"valve{valve}PortsAvailable"
        outletCount = 0 if name not in values else int(values[name])
        if outletCount < 1:
            return 0

        outlets = ""
        for outlet in range(1, outletCount):
            if self.isOutletInstalled(sysInfo, valve, outlet):
                outlets += str(outlet)

        return 0 if not outlets else int(outlets)

    def isValveInstalled(self, values, valve):
        name = f"valve_{valve}_con_string"
        return False if name not in values else values[name] == "conn"

    def isOutletInstalled(self, sysInfo, valve, outlet):
        name = f"valve{valve}outlet{outlet}"
        return False if name not in sysInfo else sysInfo[name]

    def getCurrentTemp(self, sysInfo, values):
        temps = []
        for valve in range(1, 2):
            if not self.isValveInstalled(values, valve):
                continue

            name = f"valve{valve}Temp"
            if name in sysInfo:
                temps.append(int(sysInfo[name]))

        if len(temps) == 0:
            return self.min_temp
        else:
            return max(temps)

    def getTargetTemp(self, sysInfo, values):
        temps = []
        for valve in range(1, 2):
            if not self.isValveInstalled(values, valve):
                continue

            name = f"valve{valve}Setpoint"
            if name in sysInfo:
                temps.append(int(sysInfo[name]))

        if len(temps) == 0:
            return values["def_temp"]
        else:
            return max(temps)
