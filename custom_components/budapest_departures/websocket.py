"""Websocket API for the card editor: live stop search and one-click add.

Home Assistant config flow forms cannot search while typing, so the
Dotmatrix card editor uses these commands for a live, badge-styled search.
"""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState, ConfigSubentry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .api import FutarError
from .config_flow import stop_subentry
from .const import DOMAIN, SUBENTRY_STOP

CACHE_KEY = f"{DOMAIN}_search_cache"
MAX_RESULTS = 30


@callback
def async_register(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_search)
    websocket_api.async_register_command(hass, ws_add_stop)


def _entry(hass: HomeAssistant):
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED:
            return entry
    return None


def _entity_id(hass: HomeAssistant, stop_id: str) -> str | None:
    return er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{stop_id}_next_departure")


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/search", vol.Required("query"): str})
@websocket_api.async_response
async def ws_search(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Search stops: settlement, direction, coloured routes, already-added flag."""
    entry = _entry(hass)
    if entry is None:
        connection.send_error(msg["id"], "not_loaded", "A Budapesti Indulások integráció nincs beállítva.")
        return
    query = msg["query"].strip()
    if len(query) < 3:
        connection.send_result(msg["id"], {"stops": []})
        return
    try:
        stops = (await entry.runtime_data.api.search_stops(query))[:MAX_RESULTS]
    except FutarError as err:
        connection.send_error(msg["id"], "api_error", str(err))
        return
    cache: dict[str, dict[str, Any]] = hass.data.setdefault(CACHE_KEY, {})
    configured = {s.unique_id for s in entry.subentries.values()}
    for stop in stops:
        cache[stop["id"]] = stop
        stop["added"] = stop["id"] in configured
        stop["entity_id"] = _entity_id(hass, stop["id"]) if stop["added"] else None
    connection.send_result(msg["id"], {"stops": stops})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/add_stop", vol.Required("stop_id"): str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_add_stop(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Add a stop (from the last search) and return its sensor entity_id."""
    entry = _entry(hass)
    if entry is None:
        connection.send_error(msg["id"], "not_loaded", "A Budapesti Indulások integráció nincs beállítva.")
        return
    stop_id = msg["stop_id"]
    if stop_id not in {s.unique_id for s in entry.subentries.values()}:
        stop = hass.data.get(CACHE_KEY, {}).get(stop_id)
        if stop is None:
            connection.send_error(msg["id"], "unknown_stop", "Keresd meg újra a megállót.")
            return
        data = stop_subentry(stop)
        hass.config_entries.async_add_subentry(
            entry,
            ConfigSubentry(data=data["data"], subentry_type=SUBENTRY_STOP, title=data["title"], unique_id=stop_id),
        )
    # the entry reloads; wait until the new sensor exists
    for _ in range(80):
        if entity_id := _entity_id(hass, stop_id):
            connection.send_result(msg["id"], {"entity_id": entity_id})
            return
        await asyncio.sleep(0.25)
    connection.send_error(msg["id"], "timeout", "A megálló felvéve, de a szenzor még nem jelent meg. Frissítsd az oldalt.")
