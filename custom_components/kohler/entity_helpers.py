"""Shared entity naming and formatting helpers for Kohler entities."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
import calendar
from typing import Protocol

DEFAULT_DATE_FORMAT = "m/d/yy"
DEFAULT_TIME_FORMAT = "hh:mm T z"

OUTLET_FUNCTIONS: dict[int, tuple[str, str]] = {
    1: ("Body Sprayer", "mdi:spray"),
    5: ("Shower Head", "mdi:shower-head"),
    7: ("Hand Shower", "mdi:shower"),
}

COLD_WATER_OPTIONS = {
    0: "2 Minutes",
    1: "5 Minutes",
    2: "7 Minutes",
    3: "10 Minutes",
    4: "Off",
}

AUTO_PURGE_OPTIONS = {
    0: "0 Seconds",
    1: "7 Seconds",
    2: "15 Seconds",
    3: "30 Seconds",
    4: "45 Seconds",
    5: "60 Seconds",
}

MAX_RUN_TIME_OPTIONS = {
    1: "No Limit",
    2: "20 Minutes",
    3: "30 Minutes",
    4: "40 Minutes",
    5: "50 Minutes",
}

CONNECTION_STATUS_OPTIONS = {
    "con": "Connected",
    "dis": "Disconnected",
    "intermittent": "Intermittent",
}


@dataclass(frozen=True, slots=True)
class OutletDescriptor:
    """Friendly metadata for a Kohler outlet entity."""

    valve: int
    outlet: int
    display_name: str
    icon: str
    function_id: int | None = None
    function_name: str | None = None
    mapped_outlet_id: int | None = None

    @property
    def state_attributes(self) -> dict[str, int | str]:
        """Return shared extra state attributes for outlet entities."""
        attributes: dict[str, int | str] = {
            "valve": self.valve,
            "outlet": self.outlet,
        }

        if self.function_id is not None:
            attributes["function_id"] = self.function_id

        if self.function_name is not None:
            attributes["function_name"] = self.function_name

        if self.mapped_outlet_id is not None:
            attributes["mapped_outlet_id"] = self.mapped_outlet_id

        return attributes


class OutletCoordinatorProtocol(Protocol):
    """Protocol for coordinator methods used by outlet helpers."""

    def isValveInstalled(self, valve: int) -> bool: ...

    def isOutletInstalled(self, valve: int, outlet: int) -> bool: ...

    def getValue(self, key: str, default: object = None) -> object: ...


def build_outlet_descriptors(
    coordinator: OutletCoordinatorProtocol,
) -> list[OutletDescriptor]:
    """Build friendly outlet descriptors from coordinator data."""
    raw_descriptors: list[OutletDescriptor] = []

    for valve in range(1, 3):
        if not coordinator.isValveInstalled(valve):
            continue

        for outlet in range(1, 7):
            if not coordinator.isOutletInstalled(valve, outlet):
                continue

            func_map = coordinator.getValue(f"valve{valve}_outlet{outlet}_func")
            function_id = _coerce_int(
                func_map.get("func") if isinstance(func_map, dict) else None
            )
            mapped_outlet_id = _coerce_int(
                func_map.get("id") if isinstance(func_map, dict) else None
            )

            function_name = None
            icon = "mdi:valve"
            if function_id in OUTLET_FUNCTIONS:
                function_name, icon = OUTLET_FUNCTIONS[function_id]

            raw_descriptors.append(
                OutletDescriptor(
                    valve=valve,
                    outlet=outlet,
                    display_name="",
                    icon=icon,
                    function_id=function_id,
                    function_name=function_name,
                    mapped_outlet_id=mapped_outlet_id,
                )
            )

    counts = Counter(
        descriptor.function_name
        for descriptor in raw_descriptors
        if descriptor.function_name is not None
    )
    indexes: Counter[str] = Counter()
    descriptors: list[OutletDescriptor] = []

    for descriptor in raw_descriptors:
        display_name = f"Valve {descriptor.valve} Outlet {descriptor.outlet}"
        if descriptor.function_name is not None:
            indexes[descriptor.function_name] += 1
            display_name = descriptor.function_name
            if counts[descriptor.function_name] > 1:
                display_name = f"{display_name} {indexes[descriptor.function_name]}"

        descriptors.append(
            OutletDescriptor(
                valve=descriptor.valve,
                outlet=descriptor.outlet,
                display_name=display_name,
                icon=descriptor.icon,
                function_id=descriptor.function_id,
                function_name=descriptor.function_name,
                mapped_outlet_id=descriptor.mapped_outlet_id,
            )
        )

    return descriptors


def format_kohler_datetime(
    value: datetime,
    date_format: str | None = None,
    time_format: str | None = None,
    separator: str = " ",
) -> str:
    """Format a datetime using the Kohler UI's jQuery date/time format tokens."""
    resolved_date_format = (
        date_format
        if isinstance(date_format, str) and date_format
        else DEFAULT_DATE_FORMAT
    )
    resolved_time_format = (
        time_format
        if isinstance(time_format, str) and time_format
        else DEFAULT_TIME_FORMAT
    )

    return (
        f"{_render_date_format(value, resolved_date_format)}"
        f"{separator}"
        f"{_render_time_format(value, resolved_time_format)}"
    ).strip()


def _render_date_format(value: datetime, format_string: str) -> str:
    weekday = value.weekday()
    month = value.month

    replacements = {
        "DD": calendar.day_name[weekday],
        "D": calendar.day_abbr[weekday],
        "MM": calendar.month_name[month],
        "M": calendar.month_abbr[month],
        "dd": f"{value.day:02d}",
        "d": str(value.day),
        "mm": f"{month:02d}",
        "m": str(month),
        "yy": f"{value.year:04d}",
        "y": f"{value.year % 100:02d}",
    }

    return _render_tokens(
        format_string,
        ("DD", "MM", "dd", "mm", "yy", "D", "M", "d", "m", "y"),
        replacements,
    )


def _render_time_format(value: datetime, format_string: str) -> str:
    hour_12 = value.hour % 12 or 12
    ampm = "AM" if value.hour < 12 else "PM"
    timezone_no_colon = value.strftime("%z")
    timezone_iso = (
        f"{timezone_no_colon[:3]}:{timezone_no_colon[3:]}" if timezone_no_colon else ""
    )

    replacements = {
        "HH": f"{value.hour:02d}",
        "H": str(value.hour),
        "hh": f"{hour_12:02d}",
        "h": str(hour_12),
        "mm": f"{value.minute:02d}",
        "m": str(value.minute),
        "ss": f"{value.second:02d}",
        "s": str(value.second),
        "l": f"{value.microsecond // 1000:03d}",
        "c": f"{value.microsecond % 1000:03d}",
        "z": timezone_no_colon,
        "Z": timezone_iso,
        "TT": ampm,
        "T": ampm[0],
        "tt": ampm.lower(),
        "t": ampm[0].lower(),
    }

    return _render_tokens(
        format_string,
        (
            "HH",
            "hh",
            "mm",
            "ss",
            "TT",
            "tt",
            "H",
            "h",
            "m",
            "s",
            "l",
            "c",
            "z",
            "Z",
            "T",
            "t",
        ),
        replacements,
    )


def _render_tokens(
    format_string: str,
    tokens: tuple[str, ...],
    replacements: dict[str, str],
) -> str:
    parts: list[str] = []
    index = 0

    while index < len(format_string):
        if format_string[index] == "'":
            end_index = format_string.find("'", index + 1)
            if end_index == -1:
                parts.append(format_string[index + 1 :])
                break

            parts.append(format_string[index + 1 : end_index])
            index = end_index + 1
            continue

        token = next(
            (
                candidate
                for candidate in tokens
                if format_string.startswith(candidate, index)
            ),
            None,
        )
        if token is None:
            parts.append(format_string[index])
            index += 1
            continue

        parts.append(replacements[token])
        index += len(token)

    return "".join(parts)


def translate_cold_water_setting(value: object) -> str | None:
    """Translate a raw cold-water timeout setting."""
    return _translate_option(value, COLD_WATER_OPTIONS)


def translate_auto_purge_setting(value: object, enabled: object) -> str | None:
    """Translate a raw auto-purge duration setting."""
    if not _coerce_bool(enabled):
        return "Off"
    return _translate_option(value, AUTO_PURGE_OPTIONS)


def translate_max_run_time_setting(value: object, enabled: object) -> str | None:
    """Translate a raw max-run-time setting."""
    if not _coerce_bool(enabled):
        return "Off"
    return _translate_option(value, MAX_RUN_TIME_OPTIONS)


def translate_connection_status(value: object) -> str | None:
    """Translate a raw controller connection status string."""
    if value in (None, "not_seen"):
        return None

    normalized = str(value).strip().lower()
    return CONNECTION_STATUS_OPTIONS.get(normalized, str(value))


def _coerce_int(value: object) -> int | None:
    """Coerce a value to an int when possible."""
    if value is None:
        return None

    try:
        return int(value)
    except TypeError, ValueError:
        return None


def _coerce_bool(value: object) -> bool:
    """Coerce common device truthy values into bools."""
    if isinstance(value, bool):
        return value

    if value is None:
        return False

    if isinstance(value, (int, float)):
        return value != 0

    return str(value).strip().lower() not in {"", "0", "false", "off", "none"}


def _translate_option(value: object, options: dict[int, str]) -> str | None:
    """Translate a numeric option using a mapping table."""
    key = _coerce_int(value)
    if key is None:
        return None
    return options.get(key, str(value))
