"""Tests for Kohler sensor entities."""

from __future__ import annotations

from types import SimpleNamespace

from custom_components.kohler.const import DOMAIN
from custom_components.kohler.sensor import async_setup_entry


class FakeCoordinator:
    """Minimal coordinator stub for sensor tests."""

    last_update_success = True

    def macAddress(self) -> str:
        return "00:11:22:33:44:55"

    def getConf(self, key: str):
        return "192.0.2.10"

    def firmwareVersion(self) -> str:
        return "1.0.0"


async def test_sensor_setup_skips_calibration_for_uninstalled_valves():
    """Calibration diagnostics should only be created for installed valves."""

    class SetupCoordinator(FakeCoordinator):
        def __init__(self) -> None:
            self._values = {"valve1_installed": True, "valve2_installed": False}

        def getValue(self, key: str, default=None):
            values = {
                "v1_cal_code": "172",
                "v2_cal_code": "999",
            }
            return values.get(key, default)

        def getConnectionStatus(self, key: str):
            return None

        def getCalibrationCode(self, valve: int):
            return "172" if valve == 1 else "999"

        def isValveInstalled(self, valve: int) -> bool:
            return valve == 1

    entities = []
    hass = SimpleNamespace(data={DOMAIN: SetupCoordinator()})

    await async_setup_entry(hass, config=None, add_entities=entities.extend)

    assert [
        entity.name for entity in entities if "Calibration Code" in entity.name
    ] == ["Valve 1 Calibration Code"]
