"""Data update coordinator for one stop."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FutarApi, FutarAuthError, FutarError
from .const import (
    CONF_MINUTES_AFTER,
    CONF_SCAN_INTERVAL,
    CONF_STOP_ID,
    CONF_STOP_NAME,
    DEFAULT_MINUTES_AFTER,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .parser import parse_departures, resolve_loop_headsign, service_alert_text, stop_name

_LOGGER = logging.getLogger(__name__)

type FutarConfigEntry = ConfigEntry["FutarCoordinator"]


class FutarCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls departures for a single stop."""

    config_entry: FutarConfigEntry

    def __init__(self, hass: HomeAssistant, entry: FutarConfigEntry) -> None:
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.data[CONF_STOP_ID]}",
            update_interval=timedelta(seconds=interval),
        )
        self.api = FutarApi(async_get_clientsession(hass), entry.data[CONF_API_KEY])
        self.stop_id: str = entry.data[CONF_STOP_ID]
        self.stop_name: str = entry.data.get(CONF_STOP_NAME) or self.stop_id
        # route|headsign|stop_sequence -> resolved headsign (route structure rarely changes)
        self._headsign_cache: dict[str, str] = {}

    async def _resolve_headsigns(self, departures: list[dict[str, Any]]) -> None:
        for dep in departures:
            if not dep["trip_id"] or not dep["headsign"]:
                continue
            key = f"{dep['route_id']}|{dep['headsign']}|{dep['stop_sequence']}"
            if key not in self._headsign_cache:
                try:
                    trip = await self.api.trip_details(dep["trip_id"])
                except FutarAuthError:
                    raise
                except FutarError as err:
                    _LOGGER.debug("Loop headsign lookup failed for %s: %s", dep["trip_id"], err)
                    continue  # not cached, retried on the next poll
                self._headsign_cache[key] = resolve_loop_headsign(
                    trip, self.stop_id, dep["stop_sequence"], dep["headsign"]
                )
            dep["headsign"] = self._headsign_cache[key]

    async def _async_update_data(self) -> dict[str, Any]:
        minutes_after = self.config_entry.options.get(CONF_MINUTES_AFTER, DEFAULT_MINUTES_AFTER)
        try:
            raw = await self.api.departures(self.stop_id, minutes_after)
            departures = parse_departures(raw, minutes_after)
            await self._resolve_headsigns(departures)
        except FutarAuthError as err:
            raise ConfigEntryAuthFailed("BKK API key rejected") from err
        except FutarError as err:
            raise UpdateFailed(f"Error fetching departures: {err}") from err

        return {
            "stop_name": stop_name(raw, self.stop_id) or self.stop_name,
            "departures": departures,
            "alert": service_alert_text(raw),
        }
