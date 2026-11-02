"""Config flow and sensor tests with a mocked API."""

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.budapest_departures.api import FutarAuthError
from custom_components.budapest_departures.const import DOMAIN

STOPS = [
    {"id": "BKK_F04706", "name": "Templom tér", "locality": "2083", "direction": "Ny", "type": "BUS", "routes": ["64", "164"]},
    {"id": "BKK_F04707", "name": "Templom tér", "locality": "2083", "direction": "Ny", "type": "BUS", "routes": ["64B"]},
]
API = "custom_components.budapest_departures.api.FutarApi"


async def test_full_flow(hass: HomeAssistant):
    with patch(f"{API}.search_stops", AsyncMock(return_value=STOPS)):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        assert result["step_id"] == "user"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: " abc "})
        assert result["step_id"] == "search"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"query": "te"})
        assert result["errors"] == {"query": "query_too_short"}
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"query": "Templom tér"})
        assert result["step_id"] == "stop"
        with patch("custom_components.budapest_departures.async_setup_entry", AsyncMock(return_value=True)):
            result = await hass.config_entries.flow.async_configure(result["flow_id"], {"stop_id": "BKK_F04706"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Templom tér → Ny"
    assert result["data"] == {"api_key": "abc", "stop_id": "BKK_F04706", "stop_name": "Templom tér"}


async def test_invalid_key(hass: HomeAssistant):
    with patch(f"{API}.search_stops", AsyncMock(side_effect=FutarAuthError)):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: "bad"})
    assert result["errors"] == {"base": "invalid_auth"}


async def test_sensor(hass: HomeAssistant, departures_response, loop_trip, plain_trip):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="BKK_F04706",
        data={"api_key": "abc", "stop_id": "BKK_F04706", "stop_name": "Templom tér"},
        options={"max_departures": 2},
    )
    entry.add_to_hass(hass)

    async def trip_details(trip_id):
        return loop_trip if trip_id == "T3" else plain_trip

    with patch(f"{API}.departures", AsyncMock(return_value=departures_response)), patch(
        f"{API}.trip_details", AsyncMock(side_effect=trip_details)
    ) as trip_mock:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    states = [s for s in hass.states.async_all("sensor")]
    assert len(states) == 1
    state = states[0]
    assert state.state == "0"
    assert state.attributes["stop_name"] == "Templom tér"
    assert state.attributes["alert"] == "57: Terelés"
    deps = state.attributes["departures"]
    assert len(deps) == 2  # max_departures option
    assert deps[0]["route"] == "57"
    assert "trip_id" not in deps[0]
    # 3 distinct route|headsign|seq keys -> 3 lookups, cached afterwards
    assert trip_mock.await_count == 3


async def test_auth_failure_starts_reauth(hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="X", data={"api_key": "abc", "stop_id": "X", "stop_name": "X"})
    entry.add_to_hass(hass)
    with patch(f"{API}.departures", AsyncMock(side_effect=FutarAuthError)):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is config_entries.ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" for f in flows)
