"""Private controller clock maintenance; never exposed as an entity state."""

import asyncio
import logging
import time
from datetime import datetime

from kohler import Kohler, KohlerError

from .entity_helpers import format_kohler_datetime, parse_kohler_datetime

_LOGGER = logging.getLogger(__name__)
CORRECTION_INTERVAL = 3600
MAX_DRIFT_SECONDS = 90
DATE_TIME_SETTING_INDEX = 2
DAYLIGHT_SETTING_INDEX = 3


def parse_device_time(values: dict) -> datetime:
    """Read the clock using the shared Kohler date/time format contract."""
    return parse_kohler_datetime(
        values.get("time"), values.get("date_format"), values.get("time_format")
    )


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
        self._next_attempt = 0.0
        self._pending_verification = False
        self.diagnostics: dict[str, object] = {"status": "not_checked"}

    async def async_check(
        self, values: dict, now: datetime, *, enabled: bool, idle: bool
    ) -> None:
        """Compare existing poll data; rate-limit writes and verify them next poll."""
        self.diagnostics["automatic_sync_enabled"] = enabled
        # Verification is read-only, even if disabled or the shower has started.
        if not self._pending_verification and (
            not enabled or not idle or time.monotonic() < self._next_attempt
        ):
            return
        try:
            device_time = parse_device_time(values)
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
        in_sync = abs(drift) <= MAX_DRIFT_SECONDS and not daylight and offset_matches
        if self._pending_verification:
            self._pending_verification = False
            if in_sync:
                self.diagnostics.update(
                    status="synchronized", verified_at=now.isoformat()
                )
            else:
                self.diagnostics["status"] = "verification_failed"
                _LOGGER.warning(
                    "Kohler clock correction was not confirmed by the controller"
                )
            return
        if in_sync:
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
        formatted = format_kohler_datetime(
            now, values.get("date_format"), values.get("time_format")
        )
        # Validate the outgoing format, not the potentially broken old clock.
        # This keeps manual sync usable for recovery without guessing formats.
        parse_device_time({**values, "time": formatted})
        self._next_attempt = time.monotonic() + CORRECTION_INTERVAL
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
        except asyncio.CancelledError:
            # The enclosing command timeout or unload can interrupt a partial write.
            # Preserve cancellation, but read back before trusting its outcome.
            self._pending_verification = True
            self.diagnostics["status"] = "write_interrupted"
            raise
        except KohlerError, OSError, TimeoutError:
            self.diagnostics["status"] = "write_failed"
            raise
        self._pending_verification = True
        self.diagnostics["status"] = "awaiting_verification"
