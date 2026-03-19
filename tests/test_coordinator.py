"""Tests for coordinator helper behavior."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from custom_components.kohler import coordinator as coordinator_module
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


def _build_command_test_coordinator() -> KohlerDataUpdateCoordinator:
    coordinator = object.__new__(KohlerDataUpdateCoordinator)
    coordinator.api = AsyncMock()
    coordinator._api_lock = asyncio.Lock()
    coordinator._pending_quick_shower = None
    coordinator._pending_quick_shower_task = None
    coordinator._pending_quick_shower_waiters = []
    coordinator._post_command_refresh_task = None
    coordinator._selected_outlet_state = {1: 0, 2: 0}
    coordinator._target_temperature = None
    coordinator._values = {
        "valve1PortsAvailable": 4,
        "valve2PortsAvailable": 0,
        "def_temp": 98,
        "def_control_outlet": 2,
    }
    coordinator._sysInfo = {
        "valve1_Currentstatus": "On",
        "valve2_Currentstatus": "Off",
        "valve1outlet1": False,
        "valve1outlet2": False,
        "valve1outlet3": False,
        "valve1outlet4": False,
    }
    coordinator._valve1_outlet_mappings = [1, 2, 3, 4]
    coordinator._valve2_outlet_mappings = []
    return coordinator


@pytest.mark.asyncio
async def test_open_outlet_debounces_to_latest_desired_state(monkeypatch):
    """Rapid outlet commands should collapse into one final quick_shower call."""
    monkeypatch.setattr(coordinator_module, "QUICK_SHOWER_DEBOUNCE_SECONDS", 0)
    coordinator = _build_command_test_coordinator()

    await asyncio.gather(
        coordinator.openOutlet(1, 1),
        coordinator.openOutlet(1, 2),
    )

    coordinator.api.quick_shower.assert_awaited_once_with(
        valve_num=1,
        valve1_outlet=12,
        valve1_temp=98,
        valve2_outlet=0,
        valve2_temp=98,
    )


@pytest.mark.asyncio
async def test_set_target_temperature_uses_single_quick_shower_request(monkeypatch):
    """Temperature changes while running should send one coalesced payload."""
    monkeypatch.setattr(coordinator_module, "QUICK_SHOWER_DEBOUNCE_SECONDS", 0)
    coordinator = _build_command_test_coordinator()
    coordinator._sysInfo["valve1outlet1"] = True

    await coordinator.setTargetTemperature(102)

    coordinator.api.quick_shower.assert_awaited_once_with(
        valve_num=1,
        valve1_outlet=1,
        valve1_temp=102,
        valve2_outlet=0,
        valve2_temp=102,
    )


@pytest.mark.asyncio
async def test_turn_on_shower_uses_default_control_outlet(monkeypatch):
    """Starting the shower while off should use the configured default outlet."""
    monkeypatch.setattr(coordinator_module, "QUICK_SHOWER_DEBOUNCE_SECONDS", 0)
    coordinator = _build_command_test_coordinator()
    coordinator._sysInfo["valve1_Currentstatus"] = "Off"

    await coordinator.turnOnShower()

    coordinator.api.quick_shower.assert_awaited_once_with(
        valve_num=1,
        valve1_outlet=2,
        valve1_temp=98,
        valve2_outlet=0,
        valve2_temp=98,
    )


@pytest.mark.asyncio
async def test_open_outlet_while_off_starts_only_requested_outlet(monkeypatch):
    """Opening one outlet while off should not inherit prior multi-outlet state."""
    monkeypatch.setattr(coordinator_module, "QUICK_SHOWER_DEBOUNCE_SECONDS", 0)
    coordinator = _build_command_test_coordinator()
    coordinator._sysInfo["valve1_Currentstatus"] = "Off"
    coordinator._selected_outlet_state[1] = 234

    await coordinator.openOutlet(1, 1)

    coordinator.api.quick_shower.assert_awaited_once_with(
        valve_num=1,
        valve1_outlet=1,
        valve1_temp=98,
        valve2_outlet=0,
        valve2_temp=98,
    )


@pytest.mark.asyncio
async def test_turn_off_shower_clears_pending_quick_shower(monkeypatch):
    """Stopping the shower should win over any queued outlet change."""
    monkeypatch.setattr(coordinator_module, "QUICK_SHOWER_DEBOUNCE_SECONDS", 0.05)
    coordinator = _build_command_test_coordinator()

    outlet_task = asyncio.create_task(coordinator.openOutlet(1, 1))
    await asyncio.sleep(0)
    await coordinator.turnOffShower()
    await outlet_task

    coordinator.api.stop_shower.assert_awaited_once()
    coordinator.api.quick_shower.assert_not_awaited()


@pytest.mark.asyncio
async def test_post_command_refresh_is_coalesced(monkeypatch):
    """Multiple command refresh requests should collapse into one poll."""
    monkeypatch.setattr(coordinator_module, "POST_COMMAND_REFRESH_DELAY_SECONDS", 0)
    coordinator = _build_command_test_coordinator()
    coordinator.async_request_refresh = AsyncMock()

    await asyncio.gather(
        coordinator.async_request_post_command_refresh(),
        coordinator.async_request_post_command_refresh(),
        coordinator.async_request_post_command_refresh(),
    )

    coordinator.async_request_refresh.assert_awaited_once()
