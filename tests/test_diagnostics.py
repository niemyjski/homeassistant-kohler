"""Tests for Kohler diagnostics export."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from kohler import KohlerError

from custom_components.kohler.const import DOMAIN
from custom_components.kohler.diagnostics import async_get_config_entry_diagnostics


async def test_diagnostics_include_error_logs():
    """Diagnostics export should include controller and Konnect logs."""
    coordinator = SimpleNamespace(
        _sysInfo={"status": "ok"},
        _values={"MAC": "00:11:22:33:44:55", "time": "3/18/2026 08:33 P -0600"},
        _valve1_outlet_mappings=[1, 2],
        _valve2_outlet_mappings=[],
        _target_temperature=101.0,
        api=SimpleNamespace(
            controller_error_logs=AsyncMock(return_value="controller log"),
            konnect_error_logs=AsyncMock(return_value="konnect log"),
        ),
    )
    hass = SimpleNamespace(data={DOMAIN: coordinator})

    diagnostics = await async_get_config_entry_diagnostics(
        hass, entry=SimpleNamespace()
    )

    assert diagnostics["values"]["MAC"] == "**REDACTED**"
    assert diagnostics["controller_error_log"] == "controller log"
    assert diagnostics["konnect_error_log"] == "konnect log"


async def test_diagnostics_capture_log_fetch_errors():
    """Diagnostics export should degrade cleanly when a log fetch fails."""
    coordinator = SimpleNamespace(
        _sysInfo={"status": "ok"},
        _values={"time": "3/18/2026 08:33 P -0600"},
        _valve1_outlet_mappings=[],
        _valve2_outlet_mappings=[],
        _target_temperature=None,
        api=SimpleNamespace(
            controller_error_logs=AsyncMock(side_effect=KohlerError("boom")),
            konnect_error_logs=AsyncMock(return_value="konnect log"),
        ),
    )
    hass = SimpleNamespace(data={DOMAIN: coordinator})

    diagnostics = await async_get_config_entry_diagnostics(
        hass, entry=SimpleNamespace()
    )

    assert diagnostics["controller_error_log"] == {"error": "boom"}
    assert diagnostics["konnect_error_log"] == "konnect log"
