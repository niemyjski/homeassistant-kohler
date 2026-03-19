"""Tests for Kohler valve entities."""

from __future__ import annotations

from homeassistant.components.valve import ValveState

from custom_components.kohler.entity_helpers import OutletDescriptor
from custom_components.kohler.valve import KohlerValve


class FakeCoordinator:
    """Minimal coordinator stub for valve entity tests."""

    last_update_success = True

    def __init__(self) -> None:
        self.outlet_on = False
        self.valve_on = False

    def macAddress(self) -> str:
        return "00:11:22:33:44:55"

    def getConf(self, key: str):
        return "192.0.2.10"

    def firmwareVersion(self) -> str:
        return "1.0.0"

    def isOutletOn(self, valve: int, outlet: int) -> bool:
        return self.outlet_on

    def isValveOn(self, valve: int) -> bool:
        return self.valve_on

    def getValveSettingsAttributes(self, valve: int) -> dict:
        return {"valve": valve, "default_temperature": 98}


def test_kohler_valve_reports_open_closed_without_position():
    """Kohler outlet valves should be modeled as binary open/closed valves."""
    coordinator = FakeCoordinator()
    entity = KohlerValve(
        coordinator=coordinator,
        uid="test-valve",
        descriptor=OutletDescriptor(
            valve=1,
            outlet=1,
            display_name="Shower Head 1",
            icon="mdi:shower-head",
            function_name="Shower Head",
        ),
    )
    entity.async_write_ha_state = lambda: None

    entity._handle_coordinator_update()

    assert entity.reports_position is False
    assert entity.state == ValveState.CLOSED

    coordinator.outlet_on = True
    coordinator.valve_on = True
    entity._handle_coordinator_update()

    assert entity.state == ValveState.OPEN
