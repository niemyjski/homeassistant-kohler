"""Tests for coordinator helper behavior."""

from __future__ import annotations

from custom_components.kohler.coordinator import KohlerDataUpdateCoordinator


def test_get_installed_valve_outlets_includes_highest_open_port():
    """Installed outlet bitmask should include the last available outlet."""
    coordinator = object.__new__(KohlerDataUpdateCoordinator)
    coordinator._values = {"valve1PortsAvailable": 4}
    coordinator._sysInfo = {
        "valve1outlet1": False,
        "valve1outlet2": True,
        "valve1outlet3": False,
        "valve1outlet4": True,
    }
    coordinator._valve1_outlet_mappings = [1, 2, 3, 4]
    coordinator._valve2_outlet_mappings = []

    assert coordinator.getInstalledValveOutlets(1) == 24
