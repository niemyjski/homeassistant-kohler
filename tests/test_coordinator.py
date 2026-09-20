"""Tests for coordinator helper behavior."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kohler import async_unload_entry
from custom_components.kohler import coordinator as coordinator_module
from custom_components.kohler.const import DATA_KOHLER, DOMAIN
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


def _build_command_test_coordinator(hass) -> KohlerDataUpdateCoordinator:
    coordinator = KohlerDataUpdateCoordinator(
        hass, AsyncMock(), MockConfigEntry(domain=DOMAIN)
    )
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
async def test_open_outlet_debounces_to_latest_desired_state(hass, monkeypatch):
    """Rapid outlet commands should collapse into one final quick_shower call."""
    monkeypatch.setattr(coordinator_module, "QUICK_SHOWER_DEBOUNCE_SECONDS", 0)
    coordinator = _build_command_test_coordinator(hass)

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
async def test_set_target_temperature_uses_single_quick_shower_request(
    hass, monkeypatch
):
    """Temperature changes while running should send one coalesced payload."""
    monkeypatch.setattr(coordinator_module, "QUICK_SHOWER_DEBOUNCE_SECONDS", 0)
    coordinator = _build_command_test_coordinator(hass)
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
async def test_turn_on_shower_uses_default_control_outlet(hass, monkeypatch):
    """Starting the shower while off should use the configured default outlet."""
    monkeypatch.setattr(coordinator_module, "QUICK_SHOWER_DEBOUNCE_SECONDS", 0)
    coordinator = _build_command_test_coordinator(hass)
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
async def test_open_outlet_while_off_starts_only_requested_outlet(hass, monkeypatch):
    """Opening one outlet while off should not inherit prior multi-outlet state."""
    monkeypatch.setattr(coordinator_module, "QUICK_SHOWER_DEBOUNCE_SECONDS", 0)
    coordinator = _build_command_test_coordinator(hass)
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
@pytest.mark.parametrize(
    ("command", "args", "api_method"),
    [
        ("turnOffShower", (), "stop_shower"),
        ("stop_user", (), "stop_user"),
        ("start_user", (1,), "start_user"),
    ],
)
async def test_command_clears_pending_quick_shower(
    hass, monkeypatch, command, args, api_method
):
    """Stop and profile commands supersede queued outlet changes."""
    monkeypatch.setattr(coordinator_module, "QUICK_SHOWER_DEBOUNCE_SECONDS", 0.05)
    coordinator = _build_command_test_coordinator(hass)

    outlet_task = asyncio.create_task(coordinator.openOutlet(1, 1))
    await asyncio.sleep(0)
    await getattr(coordinator, command)(*args)
    await outlet_task

    getattr(coordinator.api, api_method).assert_awaited_once_with(*args)
    coordinator.api.quick_shower.assert_not_awaited()
    assert coordinator._pending_quick_shower_task is None


@pytest.mark.asyncio
async def test_unload_cancels_pending_quick_shower(hass, monkeypatch):
    """Unloading the config entry should not leave the debounce task running."""
    monkeypatch.setattr(coordinator_module, "QUICK_SHOWER_DEBOUNCE_SECONDS", 0.05)
    coordinator = _build_command_test_coordinator(hass)
    entry = coordinator.config_entry
    entry.add_to_hass(hass)
    hass.data[DATA_KOHLER] = coordinator
    monkeypatch.setattr(
        hass.config_entries,
        "async_unload_platforms",
        AsyncMock(return_value=True),
    )

    outlet_task = asyncio.create_task(coordinator.openOutlet(1, 1))
    await asyncio.sleep(0)
    assert await async_unload_entry(hass, entry)
    await outlet_task

    coordinator.api.quick_shower.assert_not_awaited()
    assert coordinator._pending_quick_shower_task is None
    assert DATA_KOHLER not in hass.data


@pytest.mark.asyncio
async def test_post_command_refresh_is_coalesced(hass, monkeypatch):
    """Multiple command refresh requests should collapse into one poll."""
    monkeypatch.setattr(coordinator_module, "POST_COMMAND_REFRESH_DELAY_SECONDS", 0)
    coordinator = _build_command_test_coordinator(hass)
    coordinator.async_request_refresh = AsyncMock()

    await asyncio.gather(
        coordinator.async_request_post_command_refresh(),
        coordinator.async_request_post_command_refresh(),
        coordinator.async_request_post_command_refresh(),
    )

    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_unload_cancels_inflight_and_queued_commands(hass, monkeypatch):
    """Unload settles both the dispatched batch and the next queued batch."""
    monkeypatch.setattr(coordinator_module, "QUICK_SHOWER_DEBOUNCE_SECONDS", 0)
    coordinator = _build_command_test_coordinator(hass)
    entry = coordinator.config_entry
    entry.add_to_hass(hass)
    hass.data[DATA_KOHLER] = coordinator
    monkeypatch.setattr(
        hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True)
    )
    started = asyncio.Event()

    async def send(**kwargs):
        started.set()
        await asyncio.Event().wait()

    coordinator.api.quick_shower.side_effect = send
    active = asyncio.create_task(coordinator.openOutlet(1, 1))
    tasks = [active]
    try:
        await asyncio.wait_for(started.wait(), 1)
        queued = asyncio.create_task(coordinator.openOutlet(1, 2))
        tasks.append(queued)
        await asyncio.sleep(0)
        worker = coordinator._pending_quick_shower_task

        assert await async_unload_entry(hass, entry)
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(asyncio.shield(active), 1)
        await asyncio.wait_for(asyncio.shield(queued), 1)

        assert worker.cancelled()
        assert coordinator._pending_quick_shower_task is None
        assert DATA_KOHLER not in hass.data
        coordinator.api.quick_shower.assert_awaited_once()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await coordinator.async_shutdown()


@pytest.mark.asyncio
async def test_shutdown_preserves_home_assistant_cleanup(hass):
    """Shutdown cancels scheduled polling and ignores subsequent refreshes."""
    coordinator = _build_command_test_coordinator(hass)
    remove_listener = coordinator.async_add_listener(Mock())
    coordinator._async_update_data = AsyncMock()
    assert coordinator._unsub_refresh is not None

    try:
        await coordinator.async_shutdown()
        await coordinator.async_shutdown()
        await coordinator.async_request_refresh()

        assert coordinator._shutdown_requested
        assert coordinator._unsub_refresh is None
        coordinator._async_update_data.assert_not_awaited()
    finally:
        remove_listener()
