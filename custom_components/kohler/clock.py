"""Private controller clock maintenance; never exposed as an entity state."""

import asyncio
import logging
import re
import time
from datetime import datetime, timedelta

from kohler import Kohler, KohlerError

from .entity_helpers import (
    DEFAULT_DATE_FORMAT,
    DEFAULT_TIME_FORMAT,
    format_kohler_datetime,
)

_LOGGER = logging.getLogger(__name__)
CHECK_INTERVAL = 3600
MAX_DRIFT_SECONDS = 90
DATE_TIME_SETTING_INDEX = 2
DAYLIGHT_SETTING_INDEX = 3


def parse_device_time(values: dict, now: datetime) -> datetime:
    """Read numeric Kohler UI formats, including one-letter AM/PM and offsets."""
    date_tokens = {"yy": "%Y", "y": "%y", "mm": "%m", "m": "%m", "dd": "%d", "d": "%d"}
    time_tokens = {
        "HH": "%H",
        "H": "%H",
        "hh": "%I",
        "h": "%I",
        "mm": "%M",
        "m": "%M",
        "ss": "%S",
        "s": "%S",
        "TT": "%p",
        "T": "%p",
        "tt": "%p",
        "t": "%p",
        "z": "%z",
        "Z": "%z",
    }

    def convert(fmt, tokens):
        if not isinstance(fmt, str) or "%" in fmt:
            raise ValueError("Unsupported device clock format")

        def replace(match):
            try:
                return tokens[match[0]]
            except KeyError as err:
                raise ValueError("Unsupported device clock format") from err

        return re.sub(r"([a-zA-Z])\1*", replace, fmt)

    fmt = (
        convert(values.get("date_format") or DEFAULT_DATE_FORMAT, date_tokens)
        + " "
        + convert(values.get("time_format") or DEFAULT_TIME_FORMAT, time_tokens)
    )
    value = values.get("time")
    if not isinstance(value, str):
        raise TypeError("Missing device clock")
    value = re.sub(
        r"\b([ap])\b", lambda m: m[1].upper() + "M", value, flags=re.IGNORECASE
    )
    # Offset-bearing formats retain their device offset; others use HA local time.
    parsed = datetime.strptime(value, fmt)  # noqa: DTZ007
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=now.tzinfo, fold=now.fold)
    return parsed


def daylight_enabled(values: dict) -> bool:
    """Accept firmware booleans and numeric strings without bool('0')."""
    value = values.get("daylight")
    if value in (True, 1, "1", "true"):
        return True
    if value in (False, 0, "0", "false"):
        return False
    raise ValueError("Missing or invalid device daylight setting")


class KohlerClock:
    """Maintain the clock using the coordinator's existing API lock and polls."""

    def __init__(self, api: Kohler):
        self.api = api
        self._next_check = 0.0
        self._retry_after = 0.0
        self._timezone: tuple[str, timedelta | None] | None = None
        self._enabled = False
        self._pending_verification = False
        self.diagnostics: dict[str, object] = {"status": "not_checked"}

    async def async_check(
        self, values: dict, now: datetime, *, enabled: bool, idle: bool
    ) -> None:
        """Verify prior writes, then check hourly or when the timezone changes."""
        tick = time.monotonic()
        timezone = (str(now.tzinfo), now.utcoffset())
        due = self._pending_verification or (
            enabled
            and (
                not self._enabled
                or timezone != self._timezone
                or tick >= self._next_check
            )
        )
        if not enabled:
            self._enabled = False
        self.diagnostics["automatic_sync_enabled"] = enabled
        if not due:
            return
        # Verification is read-only and may complete even if the shower starts.
        if not self._pending_verification and (not idle or tick < self._retry_after):
            return
        self._enabled = enabled
        self._timezone = timezone
        self._next_check = tick + CHECK_INTERVAL
        try:
            device_time = parse_device_time(values, now)
            drift = device_time.timestamp() - now.timestamp()
            offset_matches = device_time.utcoffset() == now.utcoffset()
            daylight = daylight_enabled(values)
        except ValueError, TypeError, OverflowError:
            self._pending_verification = False
            self.diagnostics.update(
                status="invalid_device_time", checked_at=now.isoformat()
            )
            return
        self.diagnostics.update(
            checked_at=now.isoformat(), drift_seconds=round(drift, 1)
        )
        if self._pending_verification:
            self._pending_verification = False
            if abs(drift) <= MAX_DRIFT_SECONDS and not daylight and offset_matches:
                self._retry_after = 0.0
                self.diagnostics.update(
                    status="synchronized", verified_at=now.isoformat()
                )
            else:
                self.diagnostics["status"] = "verification_failed"
                _LOGGER.warning(
                    "Kohler clock correction was not confirmed by the controller"
                )
            return
        if abs(drift) <= MAX_DRIFT_SECONDS and not daylight and offset_matches:
            self.diagnostics["status"] = "in_sync"
            return
        try:
            await self.async_sync(values, now)
        except KohlerError, OSError, TimeoutError:
            # Clock maintenance must not fail the regular shower poll.
            _LOGGER.warning("Unable to synchronize Kohler clock; retrying in an hour")

    async def async_sync(self, values: dict, now: datetime) -> None:
        """Write HA local time with device DST off; require a later readback."""
        daylight = daylight_enabled(values)
        # Validate formats before writing either setting.
        parse_device_time(values, now)
        formatted = format_kohler_datetime(
            now, values.get("date_format"), values.get("time_format")
        )
        self._retry_after = self._next_check = time.monotonic() + CHECK_INTERVAL
        self._timezone = (str(now.tzinfo), now.utcoffset())
        self._pending_verification = False
        self.diagnostics.update(status="writing", attempted_at=now.isoformat())
        try:
            async with asyncio.timeout(10):
                if daylight:
                    await self.api.save_variable(DAYLIGHT_SETTING_INDEX, 0)
                # The device accepts date strings; the SDK annotates only numbers.
                await self.api.save_variable(
                    DATE_TIME_SETTING_INDEX,
                    formatted,  # type: ignore[arg-type]
                )
                await self.api.save_dt()
        except KohlerError, OSError, TimeoutError:
            self.diagnostics["status"] = "write_failed"
            raise
        self._pending_verification = True
        self.diagnostics["status"] = "awaiting_verification"
