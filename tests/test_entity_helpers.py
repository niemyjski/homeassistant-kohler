"""Tests for Kohler entity helper utilities."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from custom_components.kohler.entity_helpers import (
    build_outlet_descriptors,
    format_kohler_datetime,
    normalize_mac_address,
    translate_auto_purge_setting,
    translate_cold_water_setting,
    translate_connection_status,
    translate_max_run_time_setting,
)


class FakeCoordinator:
    """Minimal coordinator stub for outlet metadata tests."""

    def __init__(self, values: dict):
        self._values = values

    def isValveInstalled(self, valve: int) -> bool:
        return bool(self._values.get(f"valve{valve}_installed", False))

    def isOutletInstalled(self, valve: int, outlet: int) -> bool:
        return self._values.get(f"valve{valve}_outlet{outlet}_func") is not None

    def getValue(self, key: str, default=None):
        return self._values.get(key, default)


def test_build_outlet_descriptors_numbers_duplicate_mapped_outlets():
    """Duplicate mapped outlet names should be numbered consistently."""
    coordinator = FakeCoordinator(
        {
            "valve1_installed": True,
            "valve1_outlet1_func": {"func": 5, "id": 1},
            "valve1_outlet2_func": {"func": 5, "id": 2},
            "valve1_outlet3_func": {"func": 7, "id": 3},
            "valve2_installed": True,
            "valve2_outlet1_func": {"func": 1, "id": 1},
            "valve2_outlet2_func": {"func": 7, "id": 2},
        }
    )

    descriptors = build_outlet_descriptors(coordinator)

    assert [descriptor.display_name for descriptor in descriptors] == [
        "Shower Head 1",
        "Shower Head 2",
        "Hand Shower 1",
        "Body Sprayer",
        "Hand Shower 2",
    ]
    assert descriptors[0].state_attributes == {
        "valve": 1,
        "outlet": 1,
        "function_id": 5,
        "function_name": "Shower Head",
        "mapped_outlet_id": 1,
    }


def test_build_outlet_descriptors_keeps_fallback_name_for_unknown_outlet_types():
    """Unknown outlet functions should keep the valve/outlet based fallback name."""
    coordinator = FakeCoordinator(
        {
            "valve1_installed": True,
            "valve1_outlet1_func": {"func": 9, "id": 4},
        }
    )

    descriptors = build_outlet_descriptors(coordinator)

    assert len(descriptors) == 1
    assert descriptors[0].display_name == "Valve 1 Outlet 1"
    assert descriptors[0].icon == "mdi:valve"


def test_format_kohler_datetime_matches_kohler_ui_tokens():
    """The datetime formatter should match the device UI's token conventions."""
    value = datetime(
        2026,
        3,
        18,
        20,
        33,
        45,
        123000,
        tzinfo=timezone(timedelta(hours=-6)),
    )

    assert format_kohler_datetime(value, "m/d/yy", "hh:mm T z") == (
        "3/18/2026 08:33 P -0600"
    )
    assert format_kohler_datetime(value, "mm-dd-y", "HH:mm:ss Z") == (
        "03-18-26 20:33:45 -06:00"
    )


def test_translate_controller_settings_to_ui_labels():
    """Raw controller settings should translate to the labels shown in the UI."""
    assert translate_cold_water_setting(1) == "5 Minutes"
    assert translate_auto_purge_setting(4, True) == "45 Seconds"
    assert translate_auto_purge_setting(4, False) == "Off"
    assert translate_max_run_time_setting(2, True) == "20 Minutes"
    assert translate_max_run_time_setting(2, False) == "Off"
    assert translate_connection_status("con") == "Connected"
    assert translate_connection_status("intermittent") == "Intermittent"


def test_normalize_mac_address_accepts_supported_formats():
    """MAC addresses should normalize across the common formats we encounter."""
    assert normalize_mac_address("00:11:22:33:44:55") == "00:11:22:33:44:55"
    assert normalize_mac_address("00-11-22-33-44-55") == "00:11:22:33:44:55"
    assert normalize_mac_address("001122334455") == "00:11:22:33:44:55"
    assert normalize_mac_address("AA-bb-CC-dd-EE-ff") == "aa:bb:cc:dd:ee:ff"


def test_normalize_mac_address_rejects_invalid_values():
    """Invalid MAC address values should be rejected cleanly."""
    assert normalize_mac_address("00:11:22:33:44") is None
    assert normalize_mac_address("00:11:22:33:44:gg") is None
    assert normalize_mac_address(12345) is None
