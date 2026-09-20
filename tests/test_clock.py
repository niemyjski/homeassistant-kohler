"""Clock ownership, DST, write verification, and retry regression coverage."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, call
from zoneinfo import ZoneInfo

import pytest
from homeassistant.exceptions import HomeAssistantError
from kohler import KohlerError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kohler import clock as clock_module
from custom_components.kohler.clock import KohlerClock, parse_device_time
from custom_components.kohler.const import CONF_AUTO_SYNC_CLOCK, DOMAIN
from custom_components.kohler.coordinator import KohlerDataUpdateCoordinator
from custom_components.kohler.entity_helpers import format_kohler_datetime

CHICAGO = ZoneInfo("America/Chicago")


@pytest.fixture
def now():
    return datetime(2026, 9, 20, 8, 31, 29, tzinfo=CHICAGO)


def values(now, **changes):
    return {
        "time": format_kohler_datetime(now, "mm/dd/yy", "hh:mm T z"),
        "date_format": "mm/dd/yy",
        "time_format": "hh:mm T z",
        "daylight": False,
        "shower_on": False,
        "steam_running": False,
        **changes,
    }


@pytest.mark.parametrize(
    "date_fmt,time_fmt",
    [
        ("m/d/yy", "hh:mm T z"),
        ("mm/dd/yy", "hh:mm T z"),
        ("dd/mm/yy", "HH:mm:ss Z"),
        ("mm-dd-y", "h:m tt z"),
        ("yy-mm-dd", "HH:mm:ss"),
    ],
)
@pytest.mark.parametrize(
    "instant",
    [
        "2026-01-01T00:00:00-06:00",
        "2026-09-20T12:30:00-05:00",
        "2026-03-08T01:59:00-06:00",
        "2026-03-08T03:00:00-05:00",
        "2026-11-01T01:59:00-05:00",
        "2026-11-01T01:00:00-06:00",
    ],
)
def test_clock_format_roundtrip(date_fmt, time_fmt, instant):
    local = datetime.fromisoformat(instant).astimezone(CHICAGO)
    data = values(
        local,
        date_format=date_fmt,
        time_format=time_fmt,
        time=format_kohler_datetime(local, date_fmt, time_fmt),
    )
    assert parse_device_time(data, local).timestamp() == local.timestamp()


async def test_dst_disabled_before_clock_and_verified_from_device(now):
    api = AsyncMock()
    clock = KohlerClock(api)
    raw = values(now, time="9/20/2026 09:31 A -0500", daylight=True)
    await clock.async_check(raw, now, enabled=True, idle=True)
    assert api.mock_calls == [
        call.save_variable(3, 0),
        call.save_variable(2, "09/20/2026 08:31 A -0500"),
        call.save_dt(),
    ]
    assert raw["time"] == "9/20/2026 09:31 A -0500"
    assert raw["daylight"] is True
    assert clock.diagnostics["status"] == "awaiting_verification"
    await clock.async_check(values(now), now, enabled=True, idle=True)
    assert clock.diagnostics["status"] == "synchronized"
    assert "verified_at" in clock.diagnostics


async def test_mismatch_does_not_retry_every_poll(now, monkeypatch):
    tick = 100.0
    monkeypatch.setattr(clock_module.time, "monotonic", lambda: tick)
    api = AsyncMock()
    clock = KohlerClock(api)
    raw = values(now, daylight=True)
    await clock.async_check(raw, now, enabled=True, idle=True)
    await clock.async_check(raw, now, enabled=True, idle=True)
    assert clock.diagnostics["status"] == "verification_failed"
    for _ in range(20):
        await clock.async_check(raw, now, enabled=True, idle=True)
    assert api.save_dt.await_count == 1
    tick += 3600
    await clock.async_check(raw, now, enabled=True, idle=True)
    assert api.save_dt.await_count == 2


@pytest.mark.parametrize(
    "failure_method,exception",
    [
        ("save_variable", KohlerError("failed")),
        ("save_dt", OSError("offline")),
        ("save_dt", TimeoutError()),
    ],
)
async def test_failed_writes_back_off_even_across_timezone_change(
    now, failure_method, exception
):
    api = AsyncMock()
    getattr(api, failure_method).side_effect = exception
    clock = KohlerClock(api)
    raw = values(now, daylight=True)
    await clock.async_check(raw, now, enabled=True, idle=True)
    assert clock.diagnostics["status"] == "write_failed"
    count = len(api.mock_calls)
    await clock.async_check(raw, now.astimezone(UTC), enabled=True, idle=True)
    assert len(api.mock_calls) == count
    assert "verified_at" not in clock.diagnostics


@pytest.mark.parametrize(
    "changes",
    [
        {"time": None},
        {"time": "invalid"},
        {"time": "02/30/2026 08:31 A -0500"},
        {"date_format": "MM d yy"},
        {"daylight": None},
    ],
)
async def test_invalid_readings_never_write(now, changes):
    api = AsyncMock()
    clock = KohlerClock(api)
    await clock.async_check(values(now, **changes), now, enabled=True, idle=True)
    assert clock.diagnostics["status"] == "invalid_device_time"
    assert not api.mock_calls


@pytest.mark.parametrize(
    "seconds,expected", [(0, False), (89, False), (90, False), (91, True), (-91, True)]
)
async def test_drift_threshold(now, seconds, expected):
    from datetime import timedelta

    api = AsyncMock()
    clock = KohlerClock(api)
    raw = values(
        now,
        time_format="HH:mm:ss Z",
        time=format_kohler_datetime(
            now + timedelta(seconds=seconds), "mm/dd/yy", "HH:mm:ss Z"
        ),
    )
    await clock.async_check(raw, now, enabled=True, idle=True)
    assert bool(api.save_dt.await_count) is expected


async def test_disabled_and_busy_checks_defer_until_idle(now):
    api = AsyncMock()
    clock = KohlerClock(api)
    raw = values(now, daylight=True)
    await clock.async_check(raw, now, enabled=False, idle=True)
    await clock.async_check(raw, now, enabled=True, idle=False)
    assert not api.mock_calls
    await clock.async_check(raw, now, enabled=True, idle=True)
    api.save_dt.assert_awaited_once()


@pytest.mark.parametrize(
    "before,after",
    [
        ("2026-03-08T01:59:00-06:00", "2026-03-08T03:00:00-05:00"),
        ("2026-11-01T01:59:00-05:00", "2026-11-01T01:00:00-06:00"),
    ],
)
async def test_offset_change_is_detected_by_normal_poll(before, after):
    old = datetime.fromisoformat(before).astimezone(CHICAGO)
    new = datetime.fromisoformat(after).astimezone(CHICAGO)
    api = AsyncMock()
    clock = KohlerClock(api)
    await clock.async_check(values(old), old, enabled=True, idle=True)
    await clock.async_check(values(new, daylight=True), new, enabled=True, idle=True)
    api.save_dt.assert_awaited_once()


async def test_successful_corrections_are_rate_limited_even_after_reenable(
    now, monkeypatch
):
    tick = 100.0
    monkeypatch.setattr(clock_module.time, "monotonic", lambda: tick)
    api = AsyncMock()
    clock = KohlerClock(api)
    await clock.async_check(values(now), now, enabled=True, idle=True)
    raw = values(now, daylight=True)
    await clock.async_check(raw, now, enabled=True, idle=True)
    api.save_dt.assert_awaited_once()
    await clock.async_check(values(now), now, enabled=False, idle=True)
    assert clock.diagnostics["status"] == "synchronized"
    await clock.async_check(raw, now, enabled=True, idle=True)
    api.save_dt.assert_awaited_once()
    tick += 3600
    await clock.async_check(raw, now, enabled=True, idle=True)
    assert api.save_dt.await_count == 2


async def test_poll_failure_isolated_and_manual_sync_uses_readback(hass, now):
    api = AsyncMock()
    raw = values(now, daylight=True)
    api.values.return_value = raw
    api.system_info.return_value = {}
    coordinator = KohlerDataUpdateCoordinator(hass, api, MockConfigEntry(domain=DOMAIN))
    coordinator._clock_now = lambda: now
    api.save_dt.side_effect = KohlerError("failed")
    data = await coordinator._async_update_data()
    assert data["values"] == raw
    assert coordinator.clock.diagnostics["status"] == "write_failed"
    api.save_dt.side_effect = None
    await coordinator.sync_time()
    assert coordinator.getDeviceTime() == raw["time"]
    assert coordinator.clock.diagnostics["status"] == "awaiting_verification"
    api.values.return_value = values(now)
    await coordinator._async_update_data()
    assert coordinator.clock.diagnostics["status"] == "synchronized"


@pytest.mark.parametrize(
    "active",
    [
        {"steam_running": True},
        {"steam_running": "true"},
        {"shower_on": True},
    ],
)
async def test_no_clock_write_during_shower_or_steam(hass, now, active):
    api = AsyncMock()
    api.values.return_value = values(now, daylight=True, **active)
    api.system_info.return_value = {}
    coordinator = KohlerDataUpdateCoordinator(hass, api, MockConfigEntry(domain=DOMAIN))
    coordinator._clock_now = lambda: now
    await coordinator._async_update_data()
    api.save_dt.assert_not_awaited()
    with pytest.raises(HomeAssistantError, match="off"):
        await coordinator.sync_time()
    api.save_dt.assert_not_awaited()


async def test_option_disabled_prevents_poll_writes(hass, now):
    api = AsyncMock()
    api.values.return_value = values(now, daylight=True)
    api.system_info.return_value = {}
    entry = MockConfigEntry(domain=DOMAIN, options={CONF_AUTO_SYNC_CLOCK: False})
    coordinator = KohlerDataUpdateCoordinator(hass, api, entry)
    coordinator._clock_now = lambda: now
    await coordinator._async_update_data()
    api.save_dt.assert_not_awaited()


async def test_correct_instant_with_wrong_wall_clock_offset_is_corrected(now):
    """An old UTC offset can encode the right instant but show the wrong hour."""
    api = AsyncMock()
    clock = KohlerClock(api)
    raw = values(now, time="9/20/2026 07:31 A -0600")
    await clock.async_check(raw, now, enabled=True, idle=True)
    api.save_variable.assert_awaited_once_with(2, "09/20/2026 08:31 A -0500")
    await clock.async_check(raw, now, enabled=True, idle=True)
    assert clock.diagnostics["status"] == "verification_failed"


async def test_clock_only_polls_do_not_change_entity_states(hass, now, monkeypatch):
    """Clock checks/corrections must not create state_changed history events."""
    import logging
    from datetime import timedelta

    from homeassistant.const import EVENT_STATE_CHANGED
    from homeassistant.helpers.entity_component import EntityComponent

    from custom_components.kohler.button import KohlerSyncTimeButton
    from custom_components.kohler.climate import KohlerThermostat
    from custom_components.kohler.entity_helpers import OutletDescriptor
    from custom_components.kohler.sensor import KohlerVersionSensor
    from custom_components.kohler.valve import KohlerValve

    api = AsyncMock()
    raw = values(
        now,
        controller_version_string="1.0",
        MAC="00:11:22:33:44:55",
        def_temp=98,
        valve1PortsAvailable=1,
        valve1_installed=True,
    )
    api.values.return_value = raw
    api.system_info.return_value = {"valve1_Currentstatus": "Off"}
    entry = MockConfigEntry(domain=DOMAIN, data={"host": "192.0.2.10"})
    coordinator = KohlerDataUpdateCoordinator(hass, api, entry)
    coordinator._clock_now = lambda: now
    await coordinator._async_update_data()
    entities = [
        (
            "sensor",
            KohlerVersionSensor(coordinator, "Controller", "controller_version_string"),
        ),
        ("climate", KohlerThermostat(coordinator)),
        ("button", KohlerSyncTimeButton(coordinator)),
        (
            "valve",
            KohlerValve(
                coordinator,
                "test_outlet",
                OutletDescriptor(
                    valve=1,
                    outlet=1,
                    display_name="Shower",
                    icon="mdi:shower",
                    function_name="Shower Head",
                ),
            ),
        ),
    ]
    for domain, entity in entities:
        component = EntityComponent(logging.getLogger(__name__), domain, hass)
        await component.async_add_entities([entity])
    coordinator.async_set_updated_data(await coordinator._async_update_data())
    await hass.async_block_till_done()
    events = []
    unsubscribe = hass.bus.async_listen(EVENT_STATE_CHANGED, events.append)
    try:
        tick = clock_module.time.monotonic()
        monkeypatch.setattr(clock_module.time, "monotonic", lambda: tick)
        for minutes in (1, 60, 1, 1):
            tick += minutes * 60
            now += timedelta(minutes=minutes)
            api.values.return_value = values(
                now,
                **{k: v for k, v in raw.items() if k not in ("time", "daylight")},
                daylight=minutes == 60,
            )
            coordinator.async_set_updated_data(await coordinator._async_update_data())
            await hass.async_block_till_done()
        api.save_dt.assert_awaited_once()
        assert coordinator.clock.diagnostics["status"] == "synchronized"
        ids = {entity.entity_id for _, entity in entities}
        assert not [event for event in events if event.data["entity_id"] in ids]
        assert hass.states.get(entities[2][1].entity_id).state == "unknown"
    finally:
        unsubscribe()
        for _, entity in entities:
            await entity.async_remove()


@pytest.mark.parametrize("zone", ["America/Chicago", "UTC", "Asia/Kolkata"])
async def test_manual_sync_uses_ha_timezone_when_automatic_disabled(
    hass, freezer, zone
):
    """Manual sync uses HA's timezone, not the host timezone, and remains available."""
    await hass.config.async_set_time_zone(zone)
    freezer.move_to("2026-09-20T13:31:29+00:00")
    api = AsyncMock()
    expected = datetime(2026, 9, 20, 13, 31, 29, tzinfo=UTC).astimezone(ZoneInfo(zone))
    api.values.return_value = values(expected, daylight=True)
    api.system_info.return_value = {}
    entry = MockConfigEntry(domain=DOMAIN, options={CONF_AUTO_SYNC_CLOCK: False})
    coordinator = KohlerDataUpdateCoordinator(hass, api, entry)
    await coordinator.sync_time()
    assert api.save_variable.await_args_list == [
        call(3, 0),
        call(2, format_kohler_datetime(expected, "mm/dd/yy", "hh:mm T z")),
    ]
    api.values.return_value = values(expected)
    await coordinator._async_update_data()
    assert coordinator.clock.diagnostics["status"] == "synchronized"
    assert coordinator.clock.diagnostics["automatic_sync_enabled"] is False


@pytest.mark.parametrize("status", ["On", "PurgeActive", "", None])
async def test_installed_valve_must_be_confirmed_off(hass, now, status):
    api = AsyncMock()
    api.values.return_value = values(now, daylight=True, valve1_installed=True)
    api.system_info.return_value = {"valve1_Currentstatus": status}
    coordinator = KohlerDataUpdateCoordinator(hass, api, MockConfigEntry(domain=DOMAIN))
    coordinator._clock_now = lambda: now
    await coordinator._async_update_data()
    api.save_dt.assert_not_awaited()


async def test_manual_invalid_reading_is_home_assistant_error(hass, now):
    api = AsyncMock()
    api.values.return_value = values(now, time=None)
    api.system_info.return_value = {}
    coordinator = KohlerDataUpdateCoordinator(hass, api, MockConfigEntry(domain=DOMAIN))
    with pytest.raises(HomeAssistantError, match="Cannot interpret"):
        await coordinator.sync_time()
    api.save_variable.assert_not_awaited()


async def test_existing_entry_without_option_defaults_to_enabled(hass, now):
    """Existing entries need neither migration nor an options save to sync."""
    api = AsyncMock()
    api.values.return_value = values(now, daylight=True)
    api.system_info.return_value = {}
    entry = MockConfigEntry(domain=DOMAIN, options={})
    coordinator = KohlerDataUpdateCoordinator(hass, api, entry)
    coordinator._clock_now = lambda: now
    await coordinator._async_update_data()
    api.save_dt.assert_awaited_once()
    assert coordinator.clock.diagnostics["automatic_sync_enabled"] is True
    assert entry.options == {}
