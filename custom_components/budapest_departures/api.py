"""Minimal async client for the BKK FUTÁR (OneBusAway based) API."""

from __future__ import annotations

import asyncio
import math
from typing import Any

import aiohttp

from .const import API_BASE, API_VERSION_PARAMS

REQUEST_TIMEOUT = 15


class FutarError(Exception):
    """Generic API error."""


class FutarAuthError(FutarError):
    """The API key was rejected."""


class FutarConnectionError(FutarError):
    """The API could not be reached."""


_COMPASS = ["É", "ÉK", "K", "DK", "D", "DNy", "Ny", "ÉNy"]


def compass(direction: str | None) -> str:
    """Convert the API's bearing (degrees, -180..180) to a Hungarian compass label."""
    try:
        deg = float(direction)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return ""
    if math.isnan(deg):
        return ""
    return _COMPASS[round((deg % 360) / 45) % 8]


class FutarApi:
    """Thin wrapper around the endpoints we need."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str) -> None:
        self._session = session
        self._api_key = api_key

    async def _get(self, endpoint: str, **params: Any) -> dict[str, Any]:
        query = {"key": self._api_key, **API_VERSION_PARAMS}
        query.update({k: str(v) for k, v in params.items() if v is not None})
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                resp = await self._session.get(f"{API_BASE}/{endpoint}.json", params=query)
                if resp.status in (401, 403):
                    raise FutarAuthError("API key rejected")
                if resp.status >= 400:
                    raise FutarError(f"HTTP {resp.status}")
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise FutarConnectionError(str(err)) from err

        if not isinstance(data, dict):
            raise FutarError("Unexpected response")
        code = data.get("code")
        if code in (401, 403) or str(data.get("status", "")).upper() in (
            "UNAUTHORIZED",
            "FORBIDDEN",
        ):
            raise FutarAuthError("API key rejected")
        if data.get("status") != "OK":
            raise FutarError(f"API status: {data.get('status')} ({data.get('text', '')})")
        return data

    async def search_stops(self, query: str) -> list[dict[str, Any]]:
        """Search stops by name. Only boarding stops (not stop areas) are returned."""
        data = await self._get("search", query=query)
        entry = data.get("data", {}).get("entry", {}) or {}
        refs = data.get("data", {}).get("references", {}) or {}
        stops = refs.get("stops", {}) or {}
        routes = refs.get("routes", {}) or {}

        result: list[dict[str, Any]] = []
        for stop_id in entry.get("stopIds", []) or []:
            stop = stops.get(stop_id)
            if not stop or stop.get("locationType", 0) != 0:
                continue
            short_names: list[str] = []
            for route_id in stop.get("routeIds", []) or []:
                name = (routes.get(route_id) or {}).get("shortName")
                if name and name not in short_names:
                    short_names.append(name)
            result.append(
                {
                    "id": stop_id,
                    "name": stop.get("name") or stop_id,
                    "locality": stop.get("localityName") or "",
                    "direction": compass(stop.get("direction")),
                    "type": stop.get("type") or "",
                    "routes": short_names,
                }
            )
        return result

    async def departures(self, stop_id: str, minutes_after: int) -> dict[str, Any]:
        """Raw arrivals-and-departures-for-stop response."""
        return await self._get(
            "arrivals-and-departures-for-stop",
            stopId=stop_id,
            minutesBefore=0,
            minutesAfter=minutes_after,
            includeReferences="routes,trips,alerts,stops",
        )

    async def trip_details(self, trip_id: str) -> dict[str, Any]:
        """Raw trip-details response (with stop references)."""
        return await self._get("trip-details", tripId=trip_id, includeReferences="stops")
