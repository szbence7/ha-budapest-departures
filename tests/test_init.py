"""Config flow, subentry flow, sensor and migration tests with a mocked API."""

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.budapest_departures.api import FutarAuthError
from custom_components.budapest_departures.const import DOMAIN

R = lambda n, c="#009EE3": {"name": n, "color": c, "text_color": "#FFFFFF", "type": "BUS"}  # noqa: E731
STOPS = [
    {"id": "BKK_F04706", "name": "Templom tér", "locality": "2083", "place": "Solymár", "direction": "Ny", "type": "BUS", "routes": [R("64"), R("164")]},
    {"id": "BKK_F04707", "name": "Templom tér", "locality": "2083", "place": "Solymár", "direction": "K", "type": "BUS", "routes": [R("64B")]},
]
API = "custom_components.budapest_departures.api.FutarApi"


def stop_sub(stop_id, title="Templom tér → Ny"):
    return ConfigSubentryData(
        data={"stop_id": stop_id, "stop_name": "Templom tér", "direction": "Ny"},
        subentry_type="stop",
        title=title,
        unique_id=stop_id,
    )


async def test_full_flow_multi_select(hass: HomeAssistant):
    with patch(f"{API}.search_stops", AsyncMock(return_value=STOPS)):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        assert result["step_id"] == "user"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: " abc "})
        assert result["type"] is FlowResultType.MENU and result["step_id"] == "start"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "search"})
        assert result["step_id"] == "search"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"query": "te"})
        assert result["errors"] == {"query": "query_too_short"}
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"query": "Templom tér"})
        assert result["step_id"] == "stops"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"stops": []})
        assert result["errors"] == {"base": "select_one"}
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"stops": ["BKK_F04706", "BKK_F04707"]}
        )
        assert result["type"] is FlowResultType.MENU
        with patch("custom_components.budapest_departures.async_setup_entry", AsyncMock(return_value=True)):
            result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "finish"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"api_key": "abc"}
    entry = result["result"]
    titles = sorted(s.title for s in entry.subentries.values())
    assert titles == ["Templom tér → K · Solymár", "Templom tér → Ny · Solymár"]


async def test_single_instance(hass: HomeAssistant):
    MockConfigEntry(domain=DOMAIN, version=2, data={"api_key": "x"}).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_invalid_key(hass: HomeAssistant):
    with patch(f"{API}.search_stops", AsyncMock(side_effect=FutarAuthError)):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: "bad"})
    assert result["errors"] == {"base": "invalid_auth"}


async def test_sensor_and_add_stop(hass: HomeAssistant, departures_response, loop_trip, plain_trip):
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        data={"api_key": "abc"},
        options={"max_departures": 2},
        subentries_data=[stop_sub("BKK_F04706")],
    )
    entry.add_to_hass(hass)

    async def trip_details(trip_id):
        return loop_trip if trip_id == "T3" else plain_trip

    with patch(f"{API}.departures", AsyncMock(return_value=departures_response)), patch(
        f"{API}.trip_details", AsyncMock(side_effect=trip_details)
    ) as trip_mock, patch(f"{API}.search_stops", AsyncMock(return_value=STOPS)):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        state = hass.states.get("sensor.templom_ter_ny_kovetkezo_indulas")
        assert state is not None, [s.entity_id for s in hass.states.async_all()]
        assert state.state == "0"
        assert state.attributes["stop_name"] == "Templom tér"
        assert state.attributes["direction"] == "Ny"
        assert state.attributes["alert"] == "57: Terelés"
        deps = state.attributes["departures"]
        assert len(deps) == 2
        assert deps[0]["route"] == "57"
        assert "trip_id" not in deps[0]
        assert trip_mock.await_count == 3

        # "Megálló hozzáadása": already added stop is hidden from the list
        result = await hass.config_entries.subentries.async_init(
            (entry.entry_id, "stop"), context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"query": "Templom tér"})
        assert result["step_id"] == "pick"
        options = result["data_schema"].schema["stop_id"].config["options"]
        assert [o["value"] for o in options] == ["BKK_F04707"]
        result = await hass.config_entries.subentries.async_configure(result["flow_id"], {"stop_id": "BKK_F04707"})
        assert result["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()

    assert len(entry.subentries) == 2
    assert len(hass.states.async_all("sensor")) == 2


async def test_auth_failure_starts_reauth(hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, version=2, data={"api_key": "abc"}, subentries_data=[stop_sub("X")])
    entry.add_to_hass(hass)
    with patch(f"{API}.departures", AsyncMock(side_effect=FutarAuthError)):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is config_entries.ConfigEntryState.SETUP_ERROR
    assert any(f["context"]["source"] == "reauth" for f in hass.config_entries.flow.async_progress())


async def test_migrate_v1(hass: HomeAssistant, departures_response, plain_trip):
    entry = MockConfigEntry(
        domain=DOMAIN, version=1, unique_id="BKK_F04706",
        data={"api_key": "abc", "stop_id": "BKK_F04706", "stop_name": "Templom tér"},
    )
    entry.add_to_hass(hass)
    with patch(f"{API}.departures", AsyncMock(return_value=departures_response)), patch(
        f"{API}.trip_details", AsyncMock(return_value=plain_trip)
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.version == 2
    assert entry.data == {"api_key": "abc"}
    assert [s.unique_id for s in entry.subentries.values()] == ["BKK_F04706"]


async def test_finish_without_stops(hass: HomeAssistant):
    with patch(f"{API}.search_stops", AsyncMock(return_value=STOPS)):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: "abc"})
        with patch("custom_components.budapest_departures.async_setup_entry", AsyncMock(return_value=True)):
            result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "finish"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert not result["result"].subentries


async def test_websocket_search_and_add(hass: HomeAssistant, hass_ws_client, departures_response, plain_trip):
    entry = MockConfigEntry(domain=DOMAIN, version=2, data={"api_key": "abc"}, subentries_data=[stop_sub("BKK_F04706")])
    entry.add_to_hass(hass)
    with patch(f"{API}.departures", AsyncMock(return_value=departures_response)), patch(
        f"{API}.trip_details", AsyncMock(return_value=plain_trip)
    ), patch(f"{API}.search_stops", AsyncMock(return_value=[dict(s) for s in STOPS])):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        client = await hass_ws_client(hass)

        await client.send_json_auto_id({"type": "budapest_departures/search", "query": "Templom"})
        res = await client.receive_json()
        assert res["success"], res
        stops = res["result"]["stops"]
        assert stops[0]["place"] == "Solymár"
        assert stops[0]["added"] is True and stops[0]["entity_id"] == "sensor.templom_ter_ny_kovetkezo_indulas"
        assert stops[1]["added"] is False

        await client.send_json_auto_id({"type": "budapest_departures/add_stop", "stop_id": "BKK_F04707"})
        res = await client.receive_json()
        assert res["success"], res
        assert res["result"]["entity_id"] == "sensor.templom_ter_k_solymar_kovetkezo_indulas"
    assert len(entry.subentries) == 2
