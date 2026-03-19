"""Test the Kohler config flow."""

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_HOST

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
            new=AsyncMock(return_value=True),
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
        new=AsyncMock(return_value=False),
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
