"""Tests for Kohler light entities."""

from __future__ import annotations

from custom_components.kohler.light import KohlerLight


class FakeCoordinator:
    """Minimal coordinator stub for light entity tests."""

    last_update_success = True

    def macAddress(self) -> str:
        return "00:11:22:33:44:55"

    def getConf(self, key: str):
        return "192.0.2.10"

    def firmwareVersion(self) -> str:
        return "1.0.0"

    def getValue(self, key: str, default=None):
        values = {
            "light1_name": "Kohler Ceiling Light",
            "light1_level": 50,
        }
        return values.get(key, default)


def test_light_unique_id_is_scoped_to_controller():
    """Light entity IDs should stay unique across multiple controllers."""
    entity = KohlerLight(FakeCoordinator(), light_id=1, device_id="light1")

    assert entity.unique_id == "00:11:22:33:44:55_light1"
