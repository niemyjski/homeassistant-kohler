"""DataUpdateCoordinator for the Kohler integration."""

import asyncio
import logging
import time
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
import functools

from kohler import Kohler, KohlerError

from .entity_helpers import (
    DEFAULT_DATE_FORMAT,
    DEFAULT_TIME_FORMAT,
    format_kohler_datetime,
    translate_auto_purge_setting,
    translate_cold_water_setting,
    translate_connection_status,
    translate_max_run_time_setting,
)


def api_command(func):
    """Wrap an API command with a timeout and error handling."""

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            async with asyncio.timeout(10.0):
                return await func(*args, **kwargs)
        except asyncio.TimeoutError as err:
            raise HomeAssistantError(
                f"Timeout communicating with Kohler API: {err}"
            ) from err
        except KohlerError as err:
            raise HomeAssistantError(
                f"Error communicating with Kohler API: {err}"
            ) from err
        except OSError as err:
            raise HomeAssistantError(
                f"Network error communicating with Kohler API: {err}"
            ) from err

    return wrapper


_LOGGER = logging.getLogger(__name__)

DATE_TIME_SETTING_INDEX = 2


class KohlerDataUpdateCoordinator(DataUpdateCoordinator):
    """Kohler data object."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, api: Kohler, conf: ConfigEntry):
        """Init Kohler data object."""
        super().__init__(
            hass,
            _LOGGER,
            name="Kohler Data Coordinator",
            update_interval=timedelta(seconds=15),
            always_update=True,
        )
        self.api = api
        self.config_entry = conf
        self._values = {}
        self._sysInfo = {}
        self._target_temperature = None
        self._valve1_outlet_mappings = []
        self._valve2_outlet_mappings = []
        self._last_shower_on_time = 0

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:
            async with asyncio.timeout(10):
                self._values = await self.api.values()
                self._sysInfo = await self.api.system_info()
                self._mapOutlets()
                return {"values": self._values, "sysInfo": self._sysInfo}
        except (KohlerError, OSError) as err:
            raise UpdateFailed(f"Error communicating with Kohler API: {err}") from err
        except asyncio.TimeoutError as err:
            raise UpdateFailed(f"Timeout communicating with Kohler API: {err}") from err
        finally:
            current_time = time.time()
            if self.isShowerOn():
                self._last_shower_on_time = current_time
                self.update_interval = timedelta(seconds=5)
            else:
                time_since_last_on = current_time - self._last_shower_on_time
                if time_since_last_on < 120:
                    self.update_interval = timedelta(seconds=5)
                else:
                    self.update_interval = timedelta(seconds=15)

    def _mapOutlets(self):
        """Map the outlets to the order on the UI."""
        valve1_port_count = int(self.getValue("valve1PortsAvailable", 0))
        valve2_port_count = int(self.getValue("valve2PortsAvailable", 0))
        _valve1_outlet_mappings = [0] * valve1_port_count
        _valve2_outlet_mappings = [0] * valve2_port_count

        if valve1_port_count > 0:
            for port_num in range(1, valve1_port_count + 1):
                val = self.getValue(f"valve1_outlet{port_num}_func")
                if val and "id" in val:
                    _valve1_outlet_mappings[port_num - 1] = val["id"]

        if valve2_port_count > 0:
            for port_num in range(1, valve2_port_count + 1):
                val = self.getValue(f"valve2_outlet{port_num}_func")
                if val and "id" in val:
                    _valve2_outlet_mappings[port_num - 1] = val["id"]

        self._valve1_outlet_mappings = _valve1_outlet_mappings
        self._valve2_outlet_mappings = _valve2_outlet_mappings

    def getConf(self, key: str):
        return self.config_entry.data[key]

    def getValue(self, key: str, defaultValue=None):
        return defaultValue if key not in self._values else self._values[key]

    def getSystemInfo(self, key, defaultValue=None):
        return defaultValue if key not in self._sysInfo else self._sysInfo[key]

    def unitOfMeasurement(self):
        unit = self.getSystemInfo("degree_symbol")
        if unit == "&degF":
            return UnitOfTemperature.FAHRENHEIT
        if unit == "&degC":
            return UnitOfTemperature.CELSIUS
        units = self.getValue("units")
        if str(units) == "0":
            return UnitOfTemperature.FAHRENHEIT
        return UnitOfTemperature.CELSIUS

    def macAddress(self):
        return self.getValue("MAC", "unknown_mac")

    def firmwareVersion(self):
        return self.getValue("controller_version_string")

    def getInstalledValveOutlets(self, valve: int = 1):
        outlet_count = int(self.getValue(f"valve{valve}PortsAvailable", 0))
        if outlet_count < 1:
            return 0

        outlets = ""
        for outlet in range(1, outlet_count + 1):
            if self.isOutletOn(valve, outlet):
                outlets += str(outlet)

        return 0 if not outlets else int(outlets)

    def getOpenValveOutlets(self, valve: int = 1):
        outlet_count = int(self.getValue(f"valve{valve}PortsAvailable", 0))
        if outlet_count < 1:
            return ""

        outlets = ""
        for outlet in range(1, outlet_count + 1):
            if self.isOutletOn(valve, outlet):
                outlets += str(outlet)

        return outlets

    def genValveOutletOpen(self, valve: int, outletOn: int):
        outlet_count = int(self.getValue(f"valve{valve}PortsAvailable", 0))
        if outlet_count < 1:
            return ""

        outlets = ""
        for outlet in range(1, outlet_count + 1):
            if self.isOutletOn(valve, outlet) or (outlet == outletOn):
                outlets += str(outlet)

        return outlets

    def genValveOutletClosed(self, valve: int, outletOff: int):
        outlet_count = int(self.getValue(f"valve{valve}PortsAvailable", 0))
        if outlet_count < 1:
            return ""

        outlets = ""
        for outlet in range(1, outlet_count + 1):
            if self.isOutletOn(valve, outlet) and (outlet != outletOff):
                outlets += str(outlet)

        return outlets

    def isSteamInstalled(self) -> bool:
        return self.getValue("steam_installed", False)

    @api_command
    async def stop_user(self):
        """Stop arbitrary user profile operations."""
        await self.api.stop_user()

    @api_command
    async def start_user(self, user_id: int):
        """Start a quick shower via a specified user profile."""
        await self.api.start_user(user_id)

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

    def getDeviceTime(self) -> str | None:
        """Return the configured device time string."""
        return self.getValue("time")

    def getUnitsSetting(self) -> str:
        """Return the configured unit label."""
        return (
            "Fahrenheit"
            if self.unitOfMeasurement() == UnitOfTemperature.FAHRENHEIT
            else "Celsius"
        )

    def getDateFormat(self) -> str:
        """Return the device's configured date format."""
        return self.getValue("date_format", DEFAULT_DATE_FORMAT)

    def getTimeFormat(self) -> str:
        """Return the device's configured time format."""
        return self.getValue("time_format", DEFAULT_TIME_FORMAT)

    def isDaylightSavingsEnabled(self) -> bool | None:
        """Return whether daylight savings is enabled on the device."""
        daylight = self.getValue("daylight")
        if daylight is None:
            return None
        return bool(daylight)

    def getDefaultTemperatureSetting(self, valve: int) -> float | None:
        """Return the configured default temperature for a valve."""
        key = "def_temp" if valve == 1 else "v2_def_temp"
        value = self.getValue(key)
        if value is None:
            return None
        return float(value)

    def getMaxTemperatureSetting(self, valve: int) -> float | None:
        """Return the configured max temperature for a valve."""
        key = "max_temp" if valve == 1 else "v2_max_temp"
        value = self.getValue(key)
        if value is None:
            return None
        return float(value)

    def getColdWaterSetting(self, valve: int) -> str | None:
        """Return the translated cold-water timeout for a valve."""
        key = "cold_water" if valve == 1 else "v2_cold_water"
        return translate_cold_water_setting(self.getValue(key))

    def getAutoPurgeSetting(self, valve: int) -> str | None:
        """Return the translated auto-purge setting for a valve."""
        value_key = "auto_purge" if valve == 1 else "v2_auto_purge"
        return translate_auto_purge_setting(
            self.getValue(value_key),
            self.getValue("auto_purge_enable"),
        )

    def getMaxRunTimeSetting(self, valve: int) -> str | None:
        """Return the translated max run time for a valve."""
        value_key = "max_valve1_runtime" if valve == 1 else "max_valve2_runtime"
        enabled_key = (
            "max_valve1_runtime_enable" if valve == 1 else "max_valve2_runtime_enable"
        )
        return translate_max_run_time_setting(
            self.getValue(value_key),
            self.getValue(enabled_key),
        )

    def getValveSettingsAttributes(self, valve: int) -> dict[str, object]:
        """Return translated valve-level configuration attributes."""
        attributes: dict[str, object] = {
            "units": self.getUnitsSetting(),
            "default_temperature": self.getDefaultTemperatureSetting(valve),
            "max_temperature": self.getMaxTemperatureSetting(valve),
            "cold_water_off_after": self.getColdWaterSetting(valve),
            "auto_purge": self.getAutoPurgeSetting(valve),
            "max_run_time": self.getMaxRunTimeSetting(valve),
        }
        return {key: value for key, value in attributes.items() if value is not None}

    def getConnectionStatus(self, key: str) -> str | None:
        """Return a translated connection diagnostic state."""
        return translate_connection_status(self.getValue(key))

    def getCalibrationCode(self, valve: int) -> str | None:
        """Return the six-port calibration code for a valve when present."""
        key = "v1_cal_code" if valve == 1 else "v2_cal_code"
        value = self.getValue(key)
        if value in (None, "", "not_seen"):
            return None
        return str(value)

    def getCurrentTemperature(self) -> float | None:
        temps = []
        for valve in range(1, 3):
            if not self.isValveInstalled(valve):
                continue
            temp = self.getSystemInfo(f"valve{valve}Temp")
            if temp is not None:
                temps.append(float(temp))

        if not temps:
            return None
        return max(temps)

    def getTargetTemperature(self) -> float | None:
        temps = []
        for valve in range(1, 3):
            if not self.isValveInstalled(valve):
                continue

            if self.isValveOn(valve):
                temp = self.getSystemInfo(f"valve{valve}Setpoint")
            elif self._target_temperature is not None:
                temp = self._target_temperature
            else:
                temp = self.getValue(
                    f"valve{valve}_temp_string",
                    self.getDefaultTemperatureSetting(valve),
                )

            if temp is not None:
                temps.append(float(temp))

        if not temps:
            fallback = self.getDefaultTemperatureSetting(1)
            return fallback if fallback is not None else self.getValue("def_temp")
        return max(temps)

    @api_command
    async def setTargetTemperature(self, temperature):
        _LOGGER.debug("setTargetTemperature %s", temperature)
        self._target_temperature = float(temperature)

        if self.isShowerOn():
            valve1Outlets = self.getOpenValveOutlets(1) or 0
            valve2Outlets = self.getOpenValveOutlets(2) or 0

            await self.api.quick_shower(
                valve_num=1,
                valve1_outlet=int(valve1Outlets),
                valve1_temp=int(temperature),
                valve2_outlet=int(valve2Outlets),
                valve2_temp=int(temperature),
            )
            await self.api.quick_shower(
                valve_num=2,
                valve1_outlet=int(valve1Outlets),
                valve1_temp=int(temperature),
                valve2_outlet=int(valve2Outlets),
                valve2_temp=int(temperature),
            )

    def isShowerOn(self) -> bool:
        return self.isValveOn(1) or self.isValveOn(2)

    @api_command
    async def turnOnShower(self, temp=None):
        _LOGGER.debug("turnOnShower %s", temp)
        valve1Outlets = self.getInstalledValveOutlets(1)
        valve2Outlets = self.getInstalledValveOutlets(2)
        if temp is None:
            temp = self.getTargetTemperature() or 100

        await self.api.quick_shower(
            valve_num=1,
            valve1_outlet=int(valve1Outlets),
            valve1_temp=int(temp),
            valve2_outlet=int(valve2Outlets),
            valve2_temp=int(temp),
        )

    @api_command
    async def turnOffShower(self):
        _LOGGER.debug("turnOffShower")
        await self.api.stop_shower()

    @api_command
    async def openOutlet(self, valveId, outletId):
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

        temp = self.getTargetTemperature() or 100

        await self.api.quick_shower(
            valve_num=1,
            valve1_outlet=int(valve1Outlets or 0),
            valve1_temp=int(temp),
            valve2_outlet=int(valve2Outlets or 0),
            valve2_temp=int(temp),
        )
        await self.api.quick_shower(
            valve_num=2,
            valve1_outlet=int(valve1Outlets or 0),
            valve1_temp=int(temp),
            valve2_outlet=int(valve2Outlets or 0),
            valve2_temp=int(temp),
        )

    @api_command
    async def closeOutlet(self, valveId, outletId):
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

        temp = self.getTargetTemperature() or 100

        await self.api.quick_shower(
            valve_num=1,
            valve1_outlet=int(valve1Outlets or 0),
            valve1_temp=int(temp),
            valve2_outlet=int(valve2Outlets or 0),
            valve2_temp=int(temp),
        )
        await self.api.quick_shower(
            valve_num=2,
            valve1_outlet=int(valve1Outlets or 0),
            valve1_temp=int(temp),
            valve2_outlet=int(valve2Outlets or 0),
            valve2_temp=int(temp),
        )

    @api_command
    async def steam_on(self, temp=110, time=15):
        await self.api.steam_on(temp=temp, time=time)

    @api_command
    async def steam_off(self):
        await self.api.steam_off()

    @api_command
    async def massage_toggle(self):
        await self.api.massage_toggle()

    @api_command
    async def reset_controller_faults(self):
        await self.api.reset_controller_faults()

    @api_command
    async def reset_konnect_faults(self):
        await self.api.reset_konnect_faults()

    @api_command
    async def light_on(self, light_id, intensity):
        await self.api.light_on(light_id, intensity)

    @api_command
    async def light_off(self, light_id):
        await self.api.light_off(light_id)

    @api_command
    async def check_updates(self):
        return await self.api.check_updates()

    @api_command
    async def sync_time(self):
        """Sync the Kohler controller clock from Home Assistant's timezone."""
        timezone = dt_util.get_time_zone(self.hass.config.time_zone)
        now = datetime.now(timezone) if timezone is not None else dt_util.utcnow()
        formatted_time = format_kohler_datetime(
            now,
            date_format=self.getDateFormat(),
            time_format=self.getTimeFormat(),
        )

        _LOGGER.debug("sync_time %s", formatted_time)
        await self.api.save_variable(DATE_TIME_SETTING_INDEX, formatted_time)
        await self.api.save_dt()
        self._values["time"] = formatted_time
