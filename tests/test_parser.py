"""Parser unit tests."""

from custom_components.budapest_departures.api import compass
from custom_components.budapest_departures.parser import (
    parse_departures,
    resolve_loop_headsign,
    service_alert_text,
    stop_name,
)


def test_parse_departures(departures_response):
    deps = parse_departures(departures_response, 60)
    assert [d["route"] for d in deps] == ["57", "164B", "964"]  # sorted, canceled + out of window dropped
    assert [d["minutes"] for d in deps] == [0, 2, 12]
    assert deps[1]["realtime"] is True
    assert deps[2]["realtime"] is False
    assert deps[2]["night"] is True
    assert deps[1]["color"] == "#009EE3"


def test_alerts(departures_response):
    # only active alert, only the route serving this stop
    assert service_alert_text(departures_response) == "57: Terelés"


def test_stop_name(departures_response):
    assert stop_name(departures_response, "BKK_F04706") == "Templom tér"
    assert stop_name(departures_response, "nope") is None


def test_loop_after_turn(loop_trip):
    # stop index 3 is after the turning point (index 2) -> real destination
    assert resolve_loop_headsign(loop_trip, "S3", 3, "Máriaremetei kegytemplom") == "Hűvösvölgy"


def test_loop_before_turn(loop_trip):
    assert resolve_loop_headsign(loop_trip, "S1", 1, "Máriaremetei kegytemplom") == "Máriaremetei kegytemplom"


def test_not_a_loop(plain_trip):
    assert resolve_loop_headsign(plain_trip, "S1", 1, "Hűvösvölgy") == "Hűvösvölgy"


def test_compass():
    assert compass("-91") == "Ny"
    assert compass("89") == "K"
    assert compass("0") == "É"
    assert compass("") == ""
