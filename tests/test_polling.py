"""Polling failures must not keep a stale active state on fast polling."""

import asyncio
import logging
from datetime import timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.helpers.update_coordinator import CoordinatorEntity, UpdateFailed
from kohler import KohlerError
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.kohler.const import DOMAIN
from custom_components.kohler.coordinator import KohlerDataUpdateCoordinator


@pytest.fixture
def coordinator(hass):
    api = AsyncMock()
    api.values.return_value = {"valve1PortsAvailable": 0}
    api.system_info.return_value = {"valve1_Currentstatus": "On"}
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    result = KohlerDataUpdateCoordinator(hass, api, entry)
    result.clock.async_check = AsyncMock()
    return result


@pytest.mark.parametrize("endpoint", ["values", "system_info"])
@pytest.mark.parametrize("error", [TimeoutError, OSError, KohlerError])
async def test_failure_backoff_preserves_complete_snapshot(
    coordinator, endpoint, error
):
    """Either failed read backs off without publishing partial data or stale activity."""
    await coordinator._async_update_data()
    old_values = coordinator._values
    old_info = coordinator._sysInfo
    last_on = coordinator._last_shower_on_time
    coordinator.api.values.return_value = {"def_temp": 101}
    getattr(coordinator.api, endpoint).side_effect = error("private response body")
    coordinator.clock.async_check.reset_mock()

    for expected_interval in (30, 60, 120, 120):
        with pytest.raises(UpdateFailed) as exc:
            await coordinator._async_update_data()
        assert endpoint in str(exc.value)
        assert error.__name__ in str(exc.value)
        assert "private response body" not in str(exc.value)
        assert exc.value.retry_after == expected_interval
        assert coordinator.update_interval.total_seconds() == 5
        assert coordinator._last_shower_on_time == last_on
        assert coordinator._values is old_values
        assert coordinator._sysInfo is old_info
    coordinator.clock.async_check.assert_not_awaited()


@pytest.mark.parametrize("active", [True, False])
async def test_success_restores_polling_and_availability(coordinator, active):
    """HA marks failures unavailable and returns to normal cadence on recovery."""
    entity = CoordinatorEntity(coordinator)
    remove_listener = coordinator.async_add_listener(Mock())
    try:
        coordinator.api.values.side_effect = TimeoutError()
        await coordinator.async_refresh()
        assert not entity.available
        assert coordinator._unsub_refresh is not None
        assert coordinator.last_exception.retry_after == 30

        coordinator.api.values.side_effect = None
        coordinator.api.system_info.return_value = {
            "valve1_Currentstatus": "On" if active else "Off"
        }
        await coordinator.async_refresh()
        assert entity.available
        assert coordinator.update_interval.total_seconds() == (5 if active else 15)
        coordinator.api.values.side_effect = TimeoutError()
        await coordinator.async_refresh()
        assert not entity.available
        assert coordinator.last_exception.retry_after == 30
    finally:
        remove_listener()
        await coordinator.async_shutdown()


async def test_cancellation_is_not_a_poll_failure(coordinator):
    """Unload cancellation propagates and does not reset activity or backoff."""
    coordinator.api.values.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await coordinator._async_update_data()
    assert coordinator.update_interval.total_seconds() == 15
    assert coordinator._last_shower_on_time == 0


async def test_values_failure_skips_second_request(coordinator):
    """Do not add another read when the controller has already failed to respond."""
    coordinator.api.values.side_effect = TimeoutError()
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    coordinator.api.system_info.assert_not_awaited()


async def test_success_preserves_post_shower_fast_polling(coordinator, monkeypatch):
    """The existing two-minute cooldown is based only on successful observations."""
    monkeypatch.setattr("custom_components.kohler.coordinator.time.time", lambda: 1000)
    await coordinator._async_update_data()
    coordinator.api.system_info.return_value = {"valve1_Currentstatus": "Off"}
    monkeypatch.setattr("custom_components.kohler.coordinator.time.time", lambda: 1119)
    await coordinator._async_update_data()
    assert coordinator.update_interval.total_seconds() == 5
    monkeypatch.setattr("custom_components.kohler.coordinator.time.time", lambda: 1120)
    await coordinator._async_update_data()
    assert coordinator.update_interval.total_seconds() == 15


@pytest.mark.parametrize("active", [True, False])
async def test_scheduled_retries_and_recovery(hass, freezer, coordinator, active):
    """Real scheduled callbacks obey backoff and restore the healthy cadence."""
    remove_listener = coordinator.async_add_listener(Mock())

    async def advance(seconds):
        freezer.tick(timedelta(seconds=seconds))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()

    try:
        coordinator.api.values.side_effect = TimeoutError()
        await coordinator.async_refresh()
        calls = 1
        for delay in (30, 60, 120, 120):
            # Stay outside HA's sub-second scheduling jitter, then cross the deadline.
            await advance(delay - 2)
            assert coordinator.api.values.await_count == calls
            await advance(3)
            calls += 1
            assert coordinator.api.values.await_count == calls

        coordinator.api.values.side_effect = None
        coordinator.api.system_info.return_value = {
            "valve1_Currentstatus": "On" if active else "Off"
        }
        await advance(118)
        assert coordinator.api.values.await_count == calls
        await advance(3)
        calls += 1
        assert coordinator.api.values.await_count == calls
        assert coordinator.last_update_success

        healthy_delay = 5 if active else 15
        await advance(healthy_delay - 2)
        assert coordinator.api.values.await_count == calls
        await advance(3)
        calls += 1
        assert coordinator.api.values.await_count == calls
    finally:
        remove_listener()
        await coordinator.async_shutdown()


async def test_shutdown_cancels_scheduled_retry(hass, freezer, coordinator):
    """An unloaded integration must never send its pending retry."""
    remove_listener = coordinator.async_add_listener(Mock())
    try:
        coordinator.api.values.side_effect = TimeoutError()
        await coordinator.async_refresh()
        await coordinator.async_shutdown()
        freezer.tick(timedelta(seconds=180))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        coordinator.api.values.assert_awaited_once()
    finally:
        remove_listener()
        await coordinator.async_shutdown()


@pytest.mark.parametrize("endpoint", ["values", "system_info"])
async def test_debug_traceback_omits_sdk_response(coordinator, caplog, endpoint):
    """HA's debug exception formatter must not expose the original SDK body."""
    getattr(coordinator.api, endpoint).side_effect = KohlerError(
        "RAW_RESPONSE_SENTINEL"
    )
    with caplog.at_level(logging.DEBUG, logger="custom_components.kohler.coordinator"):
        await coordinator.async_refresh()
    assert "Full error:" in caplog.text
    assert endpoint in caplog.text
    assert "KohlerError" in caplog.text
    assert "RAW_RESPONSE_SENTINEL" not in caplog.text
    await coordinator.async_shutdown()
