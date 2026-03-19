"""DataUpdateCoordinator for the Kohler integration."""

import asyncio
from dataclasses import dataclass
import functools
import logging
import time
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

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
            coordinator = args[0]
            async with coordinator._api_lock:
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
QUICK_SHOWER_DEBOUNCE_SECONDS = 0.35
POST_COMMAND_REFRESH_DELAY_SECONDS = 1.0


@dataclass(slots=True)
class QuickShowerState:
    """Queued quick shower payload."""

    valve1_outlet: int
    valve2_outlet: int
    temperature: int


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
        self._api_lock = asyncio.Lock()
        self._pending_quick_shower: QuickShowerState | None = None
        self._pending_quick_shower_task: asyncio.Task[None] | None = None
        self._pending_quick_shower_waiters: list[asyncio.Future[None]] = []
        self._post_command_refresh_task: asyncio.Task[None] | None = None
        self._selected_outlet_state: dict[int, int] = {1: 0, 2: 0}

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:
            async with self._api_lock:
                async with asyncio.timeout(10):
                    self._values = await self.api.values()
                    self._sysInfo = await self.api.system_info()
                self._mapOutlets()
                self._sync_selected_outlet_state()
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

    @staticmethod
    def _decode_outlet_state(outlet_state: int) -> set[int]:
        """Convert a Kohler outlet integer like 124 into outlet numbers."""
        if outlet_state == 0:
            return set()
        return {int(outlet) for outlet in str(outlet_state)}

    @staticmethod
    def _encode_outlet_state(outlets: set[int]) -> int:
        """Convert outlet numbers into the Kohler integer payload format."""
        if not outlets:
            return 0
        return int("".join(str(outlet) for outlet in sorted(outlets)))

    def _current_outlet_state(self, valve: int) -> int:
        """Return the currently open outlets in Kohler payload format."""
        return int(self.getOpenValveOutlets(valve) or 0)

    def _default_outlet_state(self, valve: int) -> int:
        """Return the controller's configured default control outlet."""
        key = "def_control_outlet" if valve == 1 else "v2_def_control_outlet"
        outlet_count = int(self.getValue(f"valve{valve}PortsAvailable", 0))
        default_outlet = self.getValue(key)

        try:
            outlet = int(default_outlet)
        except TypeError, ValueError:
            return 0

        if outlet_count < 1 or outlet < 1 or outlet > outlet_count:
            return 0
        return outlet

    def _sync_selected_outlet_state(self) -> None:
        """Keep the remembered off-state outlet selection in sync."""
        if self.isShowerOn():
            self._selected_outlet_state[1] = self._current_outlet_state(1)
            self._selected_outlet_state[2] = self._current_outlet_state(2)
            return

        for valve in range(1, 3):
            if self._selected_outlet_state.get(valve, 0) == 0:
                self._selected_outlet_state[valve] = self._default_outlet_state(valve)

    def _desired_quick_shower_state(self) -> QuickShowerState:
        """Return the last queued state, live state, or off-state selection."""
        if self._pending_quick_shower is not None:
            return QuickShowerState(
                valve1_outlet=self._pending_quick_shower.valve1_outlet,
                valve2_outlet=self._pending_quick_shower.valve2_outlet,
                temperature=self._pending_quick_shower.temperature,
            )

        if self.isShowerOn():
            valve1_outlet = self._current_outlet_state(1)
            valve2_outlet = self._current_outlet_state(2)
        else:
            valve1_outlet = self._selected_outlet_state.get(
                1, self._default_outlet_state(1)
            )
            valve2_outlet = self._selected_outlet_state.get(
                2, self._default_outlet_state(2)
            )

        return QuickShowerState(
            valve1_outlet=valve1_outlet,
            valve2_outlet=valve2_outlet,
            temperature=int(self.getTargetTemperature() or 100),
        )

    @staticmethod
    def _with_outlet_state(
        outlet_state: int,
        outlet_id: int,
        opened: bool,
    ) -> int:
        """Update an outlet payload to reflect a single outlet change."""
        outlets = KohlerDataUpdateCoordinator._decode_outlet_state(outlet_state)
        if opened:
            outlets.add(outlet_id)
        else:
            outlets.discard(outlet_id)
        return KohlerDataUpdateCoordinator._encode_outlet_state(outlets)

    def _clear_pending_quick_shower(self, err: Exception | None = None) -> None:
        """Clear queued quick shower work and resolve all pending callers."""
        self._pending_quick_shower = None
        waiters = self._pending_quick_shower_waiters
        self._pending_quick_shower_waiters = []
        for waiter in waiters:
            if waiter.done():
                continue
            if err is None:
                waiter.set_result(None)
            else:
                waiter.set_exception(err)

    async def _async_send_quick_shower(self, state: QuickShowerState) -> None:
        """Send the latest coalesced quick shower payload."""
        try:
            async with self._api_lock:
                async with asyncio.timeout(10.0):
                    await self.api.quick_shower(
                        valve_num=1,
                        valve1_outlet=state.valve1_outlet,
                        valve1_temp=state.temperature,
                        valve2_outlet=state.valve2_outlet,
                        valve2_temp=state.temperature,
                    )
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

    async def _async_process_pending_quick_shower(self) -> None:
        """Serialize and debounce quick shower updates."""
        while True:
            await asyncio.sleep(QUICK_SHOWER_DEBOUNCE_SECONDS)

            state = self._pending_quick_shower
            waiters = self._pending_quick_shower_waiters
            self._pending_quick_shower = None
            self._pending_quick_shower_waiters = []

            if state is None:
                return

            try:
                await self._async_send_quick_shower(state)
            except Exception as err:
                for waiter in waiters:
                    if not waiter.done():
                        waiter.set_exception(err)
                self._clear_pending_quick_shower(err)
                return

            for waiter in waiters:
                if not waiter.done():
                    waiter.set_result(None)

            if self._pending_quick_shower is None:
                return

    async def _async_queue_quick_shower(self, state: QuickShowerState) -> None:
        """Queue a quick shower update and coalesce rapid successive changes."""
        self._pending_quick_shower = state
        waiter = asyncio.get_running_loop().create_future()
        self._pending_quick_shower_waiters.append(waiter)

        if (
            self._pending_quick_shower_task is None
            or self._pending_quick_shower_task.done()
        ):
            self._pending_quick_shower_task = asyncio.create_task(
                self._async_process_pending_quick_shower()
            )

        await waiter

    async def async_request_post_command_refresh(
        self, delay: float = POST_COMMAND_REFRESH_DELAY_SECONDS
    ) -> None:
        """Coalesce command-triggered refreshes into one delayed poll."""

        async def _delayed_refresh() -> None:
            await asyncio.sleep(delay)
            await self.async_request_refresh()

        task = self._post_command_refresh_task
        if task is None or task.done():
            task = asyncio.create_task(_delayed_refresh())
            self._post_command_refresh_task = task

        try:
            await asyncio.shield(task)
        finally:
            if self._post_command_refresh_task is task and task.done():
                self._post_command_refresh_task = None

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
        self._clear_pending_quick_shower()
        await self.api.stop_user()

    @api_command
    async def start_user(self, user_id: int):
        """Start a quick shower via a specified user profile."""
        self._clear_pending_quick_shower()
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

    async def setTargetTemperature(self, temperature):
        _LOGGER.debug("setTargetTemperature %s", temperature)
        self._target_temperature = float(temperature)

        if self.isShowerOn():
            state = self._desired_quick_shower_state()
            state.temperature = int(temperature)
            await self._async_queue_quick_shower(state)

    def isShowerOn(self) -> bool:
        return self.isValveOn(1) or self.isValveOn(2)

    async def turnOnShower(self, temp=None):
        _LOGGER.debug("turnOnShower %s", temp)
        if temp is None:
            temp = self.getTargetTemperature() or 100

        state = self._desired_quick_shower_state()
        if state.valve1_outlet == 0 and state.valve2_outlet == 0:
            state.valve1_outlet = self._default_outlet_state(1)
            state.valve2_outlet = self._default_outlet_state(2)

        self._target_temperature = float(temp)
        state.temperature = int(temp)
        self._selected_outlet_state[1] = state.valve1_outlet
        self._selected_outlet_state[2] = state.valve2_outlet
        await self._async_queue_quick_shower(state)

    @api_command
    async def turnOffShower(self):
        _LOGGER.debug("turnOffShower")
        if self.isShowerOn():
            self._selected_outlet_state[1] = self._current_outlet_state(1)
            self._selected_outlet_state[2] = self._current_outlet_state(2)
        self._clear_pending_quick_shower()
        await self.api.stop_shower()

    async def openOutlet(self, valveId, outletId):
        _LOGGER.debug("openOutlet valveId=%s outletId=%s", valveId, outletId)
        if self.isShowerOn():
            state = self._desired_quick_shower_state()
        else:
            state = QuickShowerState(
                valve1_outlet=0,
                valve2_outlet=0,
                temperature=int(self.getTargetTemperature() or 100),
            )

        if valveId == 1:
            state.valve1_outlet = self._with_outlet_state(
                state.valve1_outlet, outletId, True
            )
        else:
            state.valve2_outlet = self._with_outlet_state(
                state.valve2_outlet, outletId, True
            )

        self._selected_outlet_state[1] = state.valve1_outlet
        self._selected_outlet_state[2] = state.valve2_outlet
        await self._async_queue_quick_shower(state)

    async def closeOutlet(self, valveId, outletId):
        _LOGGER.debug("closeOutlet valveId=%s outletId=%s", valveId, outletId)
        state = self._desired_quick_shower_state()
        if valveId == 1:
            state.valve1_outlet = self._with_outlet_state(
                state.valve1_outlet, outletId, False
            )
        else:
            state.valve2_outlet = self._with_outlet_state(
                state.valve2_outlet, outletId, False
            )

        self._selected_outlet_state[1] = state.valve1_outlet
        self._selected_outlet_state[2] = state.valve2_outlet

        if not self.isShowerOn():
            return

        await self._async_queue_quick_shower(state)

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
