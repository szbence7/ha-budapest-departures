"""Minimal async client for the BKK FUTÁR (OneBusAway based) API."""

from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path
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


_ROMAN = [
    "", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII",
    "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX", "XXI", "XXII", "XXIII",
]
_POSTCODES: dict[str, str] | None = None


def _load_postcodes() -> dict[str, str]:
    """Postcode -> settlement (Magyar Posta + KSH data, via github.com/ferenci-tamas/IrszHnk)."""
    global _POSTCODES  # noqa: PLW0603
    if _POSTCODES is None:
        path = Path(__file__).with_name("postcodes.json")
        try:
            _POSTCODES = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _POSTCODES = {}
    return _POSTCODES


def place_name(postcode: str | None) -> str:
    """Settlement or Budapest district for a postcode, e.g. 'Solymár', 'Budapest XIX. kerület'."""
    code = (postcode or "").strip()
    if not code:
        return ""
    if len(code) == 4 and code.startswith("1") and code.isdigit():
        district = int(code[1:3])
        if 1 <= district <= 23:
            return f"Budapest {_ROMAN[district]}. kerület"
    name = _load_postcodes().get(code, "")
    return name or code


def _hex(value: str | None, default: str) -> str:
    value = (value or "").strip().lstrip("#")
    return f"#{(value if len(value) in (3, 6) else default).upper()}"


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
            route_list: list[dict[str, str]] = []
            seen: set[str] = set()
            for route_id in stop.get("routeIds", []) or []:
                route = routes.get(route_id) or {}
                name = route.get("shortName")
                if not name or name in seen:
                    continue
                seen.add(name)
                route_list.append(
                    {
                        "name": name,
                        "color": _hex(route.get("color"), "009EE3"),
                        "text_color": _hex(route.get("textColor"), "FFFFFF"),
                        "type": route.get("type") or "",
                    }
                )
            locality = stop.get("localityName") or ""
            result.append(
                {
                    "id": stop_id,
                    "name": stop.get("name") or stop_id,
                    "locality": locality,
                    "place": place_name(locality),
                    "direction": compass(stop.get("direction")),
                    "type": stop.get("type") or "",
                    "routes": route_list,
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
