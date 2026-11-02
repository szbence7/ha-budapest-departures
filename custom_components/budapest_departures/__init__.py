"""Budapesti Indulások: live departures from the BKK FUTÁR API.

One config entry = one API key (connection). Each stop is a config subentry.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from . import websocket
from .api import FutarApi, _load_postcodes
from .const import CONF_STOP_ID, CONF_STOP_NAME, DOMAIN, SUBENTRY_STOP
from .coordinator import FutarConfigEntry, FutarCoordinator, RuntimeData

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the websocket commands used by the card editor (live stop search)."""
    websocket.async_register(hass)
    await hass.async_add_executor_job(_load_postcodes)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: FutarConfigEntry) -> bool:
    """Set up the API connection and one coordinator per stop."""
    api = FutarApi(async_get_clientsession(hass), entry.data[CONF_API_KEY])
    runtime = RuntimeData(api=api)

    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_STOP:
            continue
        coordinator = FutarCoordinator(hass, entry, subentry, api)
        await coordinator.async_config_entry_first_refresh()
        runtime.coordinators[subentry.subentry_id] = coordinator

    entry.runtime_data = runtime
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # options change, stop added or removed -> reload
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: FutarConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: FutarConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: FutarConfigEntry) -> bool:
    """v1 (one entry per stop) -> v2 (one entry per API key, stops as subentries)."""
    if entry.version == 1:
        stop_id = entry.data.get(CONF_STOP_ID)
        hass.config_entries.async_update_entry(
            entry,
            data={CONF_API_KEY: entry.data[CONF_API_KEY]},
            title="BKK FUTÁR",
            unique_id=None,
            version=2,
        )
        if stop_id:
            hass.config_entries.async_add_subentry(
                entry,
                ConfigSubentry(
                    data={CONF_STOP_ID: stop_id, CONF_STOP_NAME: entry.data.get(CONF_STOP_NAME, stop_id)},
                    subentry_type=SUBENTRY_STOP,
                    title=entry.data.get(CONF_STOP_NAME, stop_id),
                    unique_id=stop_id,
                ),
            )
        _LOGGER.info("Migrated %s to version 2", entry.entry_id)
    return True
