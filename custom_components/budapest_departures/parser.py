"""Pure functions turning raw FUTÁR responses into display data.

Ported from the bkk-holabusz web app (DisplayOnly.js, loopHeadsign.js, serviceAlerts.js).
"""

from __future__ import annotations

from typing import Any

ALERT_SEPARATOR = "   -   "


def _route_short_name(route: dict[str, Any] | None, route_id: str | None, trip_id: str | None) -> str:
    if route and route.get("shortName"):
        return route["shortName"]
    if route_id:
        clean = route_id.replace("BKK_", "").lstrip("0")
        return clean or route_id.replace("BKK_", "")
    if trip_id:
        digits = "".join(ch for ch in trip_id if ch.isdigit())
        if digits:
            return digits
    return "?"


def _color(value: str | None, default: str) -> str:
    value = (value or "").strip().lstrip("#")
    return f"#{value.upper()}" if len(value) in (3, 6) else default


def parse_departures(data: dict[str, Any], minutes_after: int) -> list[dict[str, Any]]:
    """Return upcoming departures sorted by time.

    Each item: route, headsign, minutes, departure (epoch s), realtime, color,
    text_color, vehicle_type, night, trip_id, route_id, stop_sequence.
    """
    payload = data.get("data", {}) or {}
    entry = payload.get("entry", {}) or {}
    refs = payload.get("references", {}) or {}
    trips = refs.get("trips", {}) or {}
    routes = refs.get("routes", {}) or {}

    now_s = (data.get("currentTime") or 0) / 1000
    result: list[dict[str, Any]] = []

    for stop_time in entry.get("stopTimes", []) or []:
        if stop_time.get("canceled"):
            continue
        predicted = stop_time.get("predictedDepartureTime") or stop_time.get("predictedArrivalTime")
        scheduled = stop_time.get("departureTime") or stop_time.get("arrivalTime")
        departure = predicted or scheduled
        if not departure:
            continue

        minutes = round((departure - now_s) / 60) if now_s else None
        if minutes is not None and not 0 <= minutes <= minutes_after:
            continue

        trip_id = stop_time.get("tripId")
        trip = trips.get(trip_id, {}) if trip_id else {}
        route_id = trip.get("routeId")
        route = routes.get(route_id) if route_id else None
        style = (route or {}).get("style", {}) or {}

        result.append(
            {
                "route": _route_short_name(route, route_id, trip_id),
                "headsign": stop_time.get("stopHeadsign") or trip.get("tripHeadsign") or "",
                "minutes": minutes,
                "departure": int(departure),
                "realtime": bool(predicted),
                "color": _color((route or {}).get("color"), "#009EE3"),
                "text_color": _color((route or {}).get("textColor"), "#FFFFFF"),
                "vehicle_type": (route or {}).get("type") or "BUS",
                "night": (route or {}).get("color") == "000000"
                or (style.get("vehicleIcon") or {}).get("name") == "night-bus"
                or style.get("groupId") == 6,
                "trip_id": trip_id,
                "route_id": route_id,
                "stop_sequence": stop_time.get("stopSequence"),
            }
        )

    result.sort(key=lambda d: d["departure"])
    return result


def stop_name(data: dict[str, Any], stop_id: str) -> str | None:
    """Stop name from the references, if present."""
    stops = (data.get("data", {}) or {}).get("references", {}).get("stops", {}) or {}
    return (stops.get(stop_id) or {}).get("name")


def service_alert_text(data: dict[str, Any]) -> str:
    """Active service alerts for the stop, as one line of text ("" if none)."""
    payload = data.get("data", {}) or {}
    entry = payload.get("entry", {}) or {}
    refs = payload.get("references", {}) or {}
    alerts = refs.get("alerts", {}) or {}
    routes = refs.get("routes", {}) or {}
    trips = refs.get("trips", {}) or {}

    alert_ids: list[str] = list(entry.get("alertIds", []) or [])
    stop_route_ids: set[str] = set()
    for stop_time in entry.get("stopTimes", []) or []:
        for alert_id in stop_time.get("alertIds", []) or []:
            if alert_id not in alert_ids:
                alert_ids.append(alert_id)
        route_id = (trips.get(stop_time.get("tripId")) or {}).get("routeId")
        if route_id:
            stop_route_ids.add(route_id)

    now_s = (data.get("currentTime") or 0) / 1000
    texts: list[str] = []
    for alert_id in alert_ids:
        alert = alerts.get(alert_id)
        if not alert:
            continue
        start, end = alert.get("start"), alert.get("end")
        if (start and now_s and start > now_s) or (end and now_s and now_s > end):
            continue
        header_obj = alert.get("header") or {}
        header = (header_obj.get("translations") or {}).get("hu") or header_obj.get("someTranslation") or ""
        alert_routes = alert.get("routeIds") or []
        local = [r for r in alert_routes if r in stop_route_ids]
        names = [
            (routes.get(r) or {}).get("shortName")
            for r in (local or alert_routes)
            if (routes.get(r) or {}).get("shortName")
        ]
        text = f"{', '.join(names)}: {header}" if names else header
        if text.strip():
            texts.append(text)
    return ALERT_SEPARATOR.join(texts)


def _norm(name: str | None) -> str:
    return (name or "").lower().strip()


def resolve_loop_headsign(
    trip_data: dict[str, Any], stop_id: str, stop_sequence: int | None, headsign: str
) -> str:
    """For loop routes (first stop == last stop) return the real destination after the turning point.

    The API reports the turning point as headsign even after the vehicle has passed it.
    """
    payload = trip_data.get("data", {}) or {}
    stop_times = (payload.get("entry") or {}).get("stopTimes", []) or []
    stops = (payload.get("references") or {}).get("stops", {}) or {}
    if len(stop_times) < 3:
        return headsign

    names = [(stops.get(st.get("stopId")) or {}).get("name") for st in stop_times]
    first, last = names[0], names[-1]
    if not last or _norm(first) != _norm(last):
        return headsign

    current = next((i for i, st in enumerate(stop_times) if st.get("stopSequence") == stop_sequence), -1)
    if current == -1:
        current = next((i for i, st in enumerate(stop_times) if st.get("stopId") == stop_id), -1)
    if current == -1:
        return headsign

    target = _norm(headsign)
    turn = -1
    if target:
        for i in range(1, len(names) - 1):
            name = _norm(names[i])
            if name and (name.startswith(target) or target.startswith(name)):
                turn = i
                break
    if turn == -1:
        origin = stops.get(stop_times[0].get("stopId"))
        if not origin:
            return headsign
        max_dist = -1.0
        for i, st in enumerate(stop_times):
            stop = stops.get(st.get("stopId"))
            if not stop:
                continue
            dist = (stop["lat"] - origin["lat"]) ** 2 + (stop["lon"] - origin["lon"]) ** 2
            if dist > max_dist:
                max_dist, turn = dist, i

    return last if turn != -1 and current >= turn else headsign
