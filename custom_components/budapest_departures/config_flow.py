"""Config flow.

Setup:   API key -> search -> tick stops in a list (-> search again or finish)
Later:   "Megálló hozzáadása" (subentry flow): search -> pick a stop
Options: update interval, time window, departures kept
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryData,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import FutarApi, FutarAuthError, FutarConnectionError, FutarError
from .const import (
    API_KEY_URL,
    CONF_DIRECTION,
    CONF_MAX_DEPARTURES,
    CONF_MINUTES_AFTER,
    CONF_QUERY,
    CONF_SCAN_INTERVAL,
    CONF_STOP_ID,
    CONF_STOP_NAME,
    CONF_STOPS,
    DEFAULT_MAX_DEPARTURES,
    DEFAULT_MINUTES_AFTER,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    SUBENTRY_STOP,
)

MAX_RESULTS = 40
PLACEHOLDERS = {"url": API_KEY_URL}


def stop_label(stop: dict[str, Any]) -> str:
    """Human readable line for the stop list."""
    parts = [stop["name"]]
    if stop["direction"]:
        parts.append(f"→ {stop['direction']}")
    routes = stop["routes"]
    if routes:
        parts.append("· " + ", ".join(routes[:8]) + (" …" if len(routes) > 8 else ""))
    if stop["locality"]:
        parts.append(f"({stop['locality']})")
    return " ".join(parts)


def stop_title(stop: dict[str, Any]) -> str:
    return f"{stop['name']} → {stop['direction']}" if stop["direction"] else stop["name"]


def stop_subentry(stop: dict[str, Any]) -> ConfigSubentryData:
    return ConfigSubentryData(
        data={CONF_STOP_ID: stop["id"], CONF_STOP_NAME: stop["name"], CONF_DIRECTION: stop["direction"]},
        subentry_type=SUBENTRY_STOP,
        title=stop_title(stop),
        unique_id=stop["id"],
    )


async def validate_key(hass: HomeAssistant, api_key: str) -> str | None:
    """Return an error key, or None if the key works."""
    try:
        await FutarApi(async_get_clientsession(hass), api_key).search_stops("Deák")
    except FutarAuthError:
        return "invalid_auth"
    except FutarConnectionError:
        return "cannot_connect"
    except FutarError:
        return "unknown"
    return None


async def search(hass: HomeAssistant, api_key: str, query: str) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Search stops; returns (results, errors)."""
    query = query.strip()
    if len(query) < 3:
        return [], {CONF_QUERY: "query_too_short"}
    try:
        stops = await FutarApi(async_get_clientsession(hass), api_key).search_stops(query)
    except FutarAuthError:
        return [], {"base": "invalid_auth"}
    except FutarConnectionError:
        return [], {"base": "cannot_connect"}
    except FutarError:
        return [], {"base": "unknown"}
    if not stops:
        return [], {CONF_QUERY: "no_stops"}
    return stops[:MAX_RESULTS], {}


def search_schema(default: str = "") -> vol.Schema:
    return vol.Schema({vol.Required(CONF_QUERY, default=default or vol.UNDEFINED): TextSelector()})


def stops_schema(results: dict[str, dict[str, Any]], multiple: bool) -> vol.Schema:
    options = [SelectOptionDict(value=sid, label=stop_label(s)) for sid, s in results.items()]
    key = CONF_STOPS if multiple else CONF_STOP_ID
    return vol.Schema(
        {
            vol.Required(key): SelectSelector(
                SelectSelectorConfig(options=options, multiple=multiple, mode=SelectSelectorMode.LIST)
            )
        }
    )


class BudapestDeparturesConfigFlow(ConfigFlow, domain=DOMAIN):
    """Initial setup."""

    VERSION = 2

    def __init__(self) -> None:
        self._api_key: str = ""
        self._results: dict[str, dict[str, Any]] = {}
        self._selected: dict[str, dict[str, Any]] = {}

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_STOP: StopSubentryFlow}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return BudapestDeparturesOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Step 1: API key."""
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            if not (error := await validate_key(self.hass, api_key)):
                self._api_key = api_key
                return await self.async_step_search()
            errors["base"] = error

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_API_KEY): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))}
            ),
            errors=errors,
            description_placeholders=PLACEHOLDERS,
        )

    async def async_step_search(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Step 2: search stops by name."""
        errors: dict[str, str] = {}
        if user_input is not None:
            stops, errors = await search(self.hass, self._api_key, user_input[CONF_QUERY])
            if not errors:
                self._results = {s["id"]: s for s in stops}
                return await self.async_step_stops()
        return self.async_show_form(
            step_id="search",
            data_schema=search_schema(),
            errors=errors,
            description_placeholders={"selected": self._selected_text()},
        )

    async def async_step_stops(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Step 3: tick one or more stops in the list."""
        errors: dict[str, str] = {}
        if user_input is not None:
            chosen = user_input.get(CONF_STOPS) or []
            if chosen:
                for sid in chosen:
                    self._selected[sid] = self._results[sid]
                return await self.async_step_more()
            errors["base"] = "select_one"
        return self.async_show_form(
            step_id="stops", data_schema=stops_schema(self._results, multiple=True), errors=errors
        )

    async def async_step_more(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Step 4: search for more stops or finish."""
        return self.async_show_menu(
            step_id="more",
            menu_options=["search", "finish"],
            description_placeholders={"selected": self._selected_text()},
        )

    async def async_step_finish(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Create the entry with all selected stops."""
        return self.async_create_entry(
            title="BKK FUTÁR",
            data={CONF_API_KEY: self._api_key},
            subentries=[stop_subentry(s) for s in self._selected.values()],
        )

    def _selected_text(self) -> str:
        if not self._selected:
            return "–"
        return "\n".join(f"• {stop_title(s)}" for s in self._selected.values())

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """The stored key was rejected: ask for a new one."""
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            if not (error := await validate_key(self.hass, api_key)):
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(), data_updates={CONF_API_KEY: api_key}
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {vol.Required(CONF_API_KEY): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))}
            ),
            errors=errors,
            description_placeholders=PLACEHOLDERS,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change the API key from the UI."""
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            if not (error := await validate_key(self.hass, api_key)):
                return self.async_update_reload_and_abort(
                    self._get_reconfigure_entry(), data_updates={CONF_API_KEY: api_key}
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {vol.Required(CONF_API_KEY): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))}
            ),
            errors=errors,
            description_placeholders=PLACEHOLDERS,
        )


class StopSubentryFlow(ConfigSubentryFlow):
    """'Megálló hozzáadása' button on the integration page."""

    def __init__(self) -> None:
        self._results: dict[str, dict[str, Any]] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            entry = self._get_entry()
            stops, errors = await search(self.hass, entry.data[CONF_API_KEY], user_input[CONF_QUERY])
            if not errors:
                existing = {s.unique_id for s in entry.subentries.values()}
                self._results = {s["id"]: s for s in stops if s["id"] not in existing}
                if self._results:
                    return await self.async_step_pick()
                errors[CONF_QUERY] = "all_added"
        return self.async_show_form(step_id="user", data_schema=search_schema(), errors=errors)

    async def async_step_pick(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        if user_input is not None:
            stop = self._results[user_input[CONF_STOP_ID]]
            data = stop_subentry(stop)
            return self.async_create_entry(title=data["title"], data=data["data"], unique_id=data["unique_id"])
        return self.async_show_form(step_id="pick", data_schema=stops_schema(self._results, multiple=False))


class BudapestDeparturesOptionsFlow(OptionsFlow):
    """Polling interval, time window and number of departures."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={k: int(v) for k, v in user_input.items()})

        opts = self.config_entry.options

        def num(minimum: int, maximum: int, unit: str | None) -> NumberSelector:
            return NumberSelector(
                NumberSelectorConfig(
                    min=minimum, max=maximum, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement=unit
                )
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL, default=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                    ): num(MIN_SCAN_INTERVAL, MAX_SCAN_INTERVAL, "mp"),
                    vol.Required(
                        CONF_MINUTES_AFTER, default=opts.get(CONF_MINUTES_AFTER, DEFAULT_MINUTES_AFTER)
                    ): num(10, 180, "perc"),
                    vol.Required(
                        CONF_MAX_DEPARTURES, default=opts.get(CONF_MAX_DEPARTURES, DEFAULT_MAX_DEPARTURES)
                    ): num(1, 30, None),
                }
            ),
        )
