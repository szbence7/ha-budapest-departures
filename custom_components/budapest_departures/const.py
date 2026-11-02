"""Constants for the Budapest Departure Board integration."""

from __future__ import annotations

DOMAIN = "budapest_departures"

API_BASE = "https://futar.bkk.hu/api/query/v1/ws/otp/api/where"
API_VERSION_PARAMS = {"version": "3", "appVersion": "apiary-1.0"}

CONF_STOP_ID = "stop_id"
CONF_STOP_NAME = "stop_name"
CONF_QUERY = "query"

CONF_SCAN_INTERVAL = "scan_interval"
CONF_MINUTES_AFTER = "minutes_after"
CONF_MAX_DEPARTURES = "max_departures"

DEFAULT_SCAN_INTERVAL = 30  # seconds
MIN_SCAN_INTERVAL = 15
MAX_SCAN_INTERVAL = 300

DEFAULT_MINUTES_AFTER = 60
DEFAULT_MAX_DEPARTURES = 10

ATTRIBUTION = "Adatok: BKK FUTÁR (opendata.bkk.hu)"
