"""Test the Kohler config flow."""

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_HOST
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kohler.const import DOMAIN, CONF_ACCEPT_LIABILITY_TERMS


async def test_form_valid(hass):
    """Test we get the form and create an entry if connection succeeds."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {}

    with (
        patch(
            "custom_components.kohler.config_flow.KohlerFlowHandler.test_connection",
            new=AsyncMock(return_value="00:11:22:33:44:55"),
        ),
        patch(
            "custom_components.kohler.async_setup_entry",
            return_value=True,
        ) as mock_setup_entry,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "1.1.1.1",
                CONF_ACCEPT_LIABILITY_TERMS: True,
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result2["title"] == "1.1.1.1"
    assert result2["data"] == {
        CONF_HOST: "1.1.1.1",
        CONF_ACCEPT_LIABILITY_TERMS: True,
    }
    assert len(mock_setup_entry.mock_calls) == 1


async def test_form_cannot_connect(hass):
    """Test we handle cannot connect error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.kohler.config_flow.KohlerFlowHandler.test_connection",
        new=AsyncMock(return_value=None),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "1.1.1.1",
                CONF_ACCEPT_LIABILITY_TERMS: True,
            },
        )

    assert result2["type"] == data_entry_flow.FlowResultType.FORM
    assert result2["errors"] == {CONF_HOST: "cannot_connect"}
    host_key = next(
        key
        for key in result2["data_schema"].schema
        if getattr(key, "schema", None) == CONF_HOST
    )
    assert host_key.default() == "1.1.1.1"


async def test_dhcp_discovery_prefills_user_form(hass):
    """DHCP discovery should route into the setup form with the host prefilled."""
    with patch(
        "custom_components.kohler.config_flow.KohlerFlowHandler.test_connection",
        new=AsyncMock(return_value="00:11:22:33:44:55"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_DHCP},
            data=DhcpServiceInfo(
                ip="192.0.2.20",
                hostname="kohler-controller",
                macaddress="001122334455",
            ),
        )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}
    host_key = next(
        key
        for key in result["data_schema"].schema
        if getattr(key, "schema", None) == CONF_HOST
    )
    assert host_key.default() == "192.0.2.20"


async def test_dhcp_updates_existing_entry_by_unique_id(hass):
    """DHCP discovery should update the host for an existing configured device."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Kohler",
        data={
            CONF_HOST: "192.0.2.10",
            CONF_ACCEPT_LIABILITY_TERMS: True,
        },
        unique_id="00:11:22:33:44:55",
        version=3,
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.kohler.config_flow.KohlerFlowHandler.test_connection",
        new=AsyncMock(return_value="00:11:22:33:44:55"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_DHCP},
            data=DhcpServiceInfo(
                ip="192.0.2.30",
                hostname="kohler-controller",
                macaddress="001122334455",
            ),
        )

    await hass.async_block_till_done()

    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == "192.0.2.30"
