"""Fixtures (shapes taken from real BKK FUTÁR responses)."""

from __future__ import annotations

import pytest

NOW = 1793604389  # seconds

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def stop_time(trip, minutes, headsign="Hűvösvölgy", seq=9, predicted=True, canceled=False, alert_ids=None):
    t = NOW + minutes * 60
    st = {
        "stopId": "BKK_F04706",
        "stopHeadsign": headsign,
        "arrivalTime": t - 30,
        "departureTime": t - 30,
        "stopSequence": seq,
        "tripId": trip,
        "canceled": canceled,
        "alertIds": alert_ids or [],
    }
    if predicted:
        st["predictedArrivalTime"] = t
        st["predictedDepartureTime"] = t
    return st


@pytest.fixture
def departures_response():
    return {
        "version": 3,
        "status": "OK",
        "code": 200,
        "currentTime": NOW * 1000,
        "data": {
            "entry": {
                "stopId": "BKK_F04706",
                "alertIds": [],
                "stopTimes": [
                    stop_time("T2", 12, predicted=False, seq=5),
                    stop_time("T1", 2),
                    stop_time("T3", 0, headsign="Máriaremetei kegytemplom", seq=4, alert_ids=["A1"]),
                    stop_time("T4", 75),  # outside the 60 min window
                    stop_time("T5", 5, canceled=True),
                ],
            },
            "references": {
                "routes": {
                    "BKK_1642": {"id": "BKK_1642", "shortName": "164B", "type": "BUS", "color": "009EE3", "textColor": "FFFFFF"},
                    "BKK_0570": {"id": "BKK_0570", "shortName": "57", "type": "BUS", "color": "009EE3", "textColor": "FFFFFF"},
                    "BKK_9640": {"id": "BKK_9640", "shortName": "964", "type": "BUS", "color": "000000", "textColor": "FFFFFF"},
                },
                "trips": {
                    "T1": {"id": "T1", "routeId": "BKK_1642"},
                    "T2": {"id": "T2", "routeId": "BKK_9640"},
                    "T3": {"id": "T3", "routeId": "BKK_0570"},
                    "T4": {"id": "T4", "routeId": "BKK_1642"},
                    "T5": {"id": "T5", "routeId": "BKK_1642"},
                },
                "alerts": {
                    "A1": {
                        "id": "A1",
                        "start": NOW - 3600,
                        "end": NOW + 3600,
                        "routeIds": ["BKK_0570", "BKK_9999"],
                        "header": {"translations": {"hu": "Terelés"}},
                    },
                    "A2": {"id": "A2", "start": NOW + 7200, "routeIds": ["BKK_0570"], "header": {"translations": {"hu": "Jövőbeli"}}},
                },
                "stops": {"BKK_F04706": {"id": "BKK_F04706", "name": "Templom tér"}},
            },
        },
    }


def _trip(names_coords, seqs=None):
    stop_times = []
    stops = {}
    for i, (name, lat, lon) in enumerate(names_coords):
        sid = f"S{i}"
        stops[sid] = {"id": sid, "name": name, "lat": lat, "lon": lon}
        stop_times.append({"stopId": sid, "stopSequence": (seqs or list(range(len(names_coords))))[i]})
    return {"status": "OK", "data": {"entry": {"stopTimes": stop_times}, "references": {"stops": stops}}}


@pytest.fixture
def loop_trip():
    # Hűvösvölgy -> Máriaremetei kegytemplom (turn) -> Hűvösvölgy
    return _trip(
        [
            ("Hűvösvölgy", 47.54, 18.96),
            ("Nyéki út", 47.55, 18.95),
            ("Máriaremetei kegytemplom", 47.57, 18.92),
            ("Templom tér", 47.56, 18.93),
            ("Hűvösvölgy", 47.54, 18.96),
        ]
    )


@pytest.fixture
def plain_trip():
    return _trip([("Solymár, PEMÜ", 47.59, 18.93), ("Templom tér", 47.58, 18.93), ("Hűvösvölgy", 47.54, 18.96)])
