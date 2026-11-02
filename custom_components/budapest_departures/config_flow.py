"""Config flow: API key -> stop search -> pick a stop."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_API_KEY
from homeassistant.core import callback
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
    CONF_MAX_DEPARTURES,
    CONF_MINUTES_AFTER,
    CONF_QUERY,
    CONF_SCAN_INTERVAL,
    CONF_STOP_ID,
    CONF_STOP_NAME,
    DEFAULT_MAX_DEPARTURES,
    DEFAULT_MINUTES_AFTER,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

MAX_RESULTS = 40


def _stop_label(stop: dict[str, Any]) -> str:
    parts = [stop["name"]]
    if stop["direction"]:
        parts.append(f"→ {stop['direction']}")
    routes = stop["routes"]
    if routes:
        shown = ", ".join(routes[:8]) + (" …" if len(routes) > 8 else "")
        parts.append(f"· {shown}")
    if stop["locality"]:
        parts.append(f"({stop['locality']})")
    parts.append(f"[{stop['id'].replace('BKK_', '')}]")
    return " ".join(parts)


class BudapestDeparturesConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._api_key: str | None = None
        self._results: dict[str, dict[str, Any]] = {}

    def _api(self, api_key: str) -> FutarApi:
        return FutarApi(async_get_clientsession(self.hass), api_key)

    def _known_api_key(self) -> str | None:
        for entry in self._async_current_entries(include_ignore=False):
            if key := entry.data.get(CONF_API_KEY):
                return key
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Step 1: API key."""
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            try:
                await self._api(api_key).search_stops("Deák")
            except FutarAuthError:
                errors["base"] = "invalid_auth"
            except FutarConnectionError:
                errors["base"] = "cannot_connect"
            except FutarError:
                errors["base"] = "unknown"
            else:
                self._api_key = api_key
                return await self.async_step_search()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY, default=self._known_api_key() or vol.UNDEFINED): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_search(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Step 2: search for a stop by name."""
        errors: dict[str, str] = {}
        if user_input is not None:
            query = user_input[CONF_QUERY].strip()
            if len(query) < 3:
                errors[CONF_QUERY] = "query_too_short"
            else:
                try:
                    assert self._api_key
                    stops = await self._api(self._api_key).search_stops(query)
                except FutarConnectionError:
                    errors["base"] = "cannot_connect"
                except FutarError:
                    errors["base"] = "unknown"
                else:
                    if not stops:
                        errors[CONF_QUERY] = "no_stops"
                    else:
                        self._results = {s["id"]: s for s in stops[:MAX_RESULTS]}
                        return await self.async_step_stop()

        return self.async_show_form(
            step_id="search",
            data_schema=vol.Schema({vol.Required(CONF_QUERY): TextSelector()}),
            errors=errors,
        )

    async def async_step_stop(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Step 3: pick the stop (each direction is a separate stop)."""
        if user_input is not None:
            stop = self._results[user_input[CONF_STOP_ID]]
            await self.async_set_unique_id(stop["id"])
            self._abort_if_unique_id_configured()
            title = f"{stop['name']} → {stop['direction']}" if stop["direction"] else stop["name"]
            return self.async_create_entry(
                title=title,
                data={
                    CONF_API_KEY: self._api_key,
                    CONF_STOP_ID: stop["id"],
                    CONF_STOP_NAME: stop["name"],
                },
            )

        options = [SelectOptionDict(value=sid, label=_stop_label(s)) for sid, s in self._results.items()]
        return self.async_show_form(
            step_id="stop",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_STOP_ID): SelectSelector(
                        SelectSelectorConfig(options=options, mode=SelectSelectorMode.LIST)
                    )
                }
            ),
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """The stored key was rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for a new API key."""
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            try:
                await self._api(api_key).search_stops("Deák")
            except FutarAuthError:
                errors["base"] = "invalid_auth"
            except FutarConnectionError:
                errors["base"] = "cannot_connect"
            except FutarError:
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(), data_updates={CONF_API_KEY: api_key}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {vol.Required(CONF_API_KEY): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))}
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        """Options."""
        return BudapestDeparturesOptionsFlow()


class BudapestDeparturesOptionsFlow(OptionsFlow):
    """Polling interval, time window and number of departures."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={k: int(v) for k, v in user_input.items()})

        opts = self.config_entry.options

        def num(minimum: int, maximum: int, unit: str) -> NumberSelector:
            return NumberSelector(
                NumberSelectorConfig(min=minimum, max=maximum, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement=unit)
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL, default=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                    ): num(MIN_SCAN_INTERVAL, MAX_SCAN_INTERVAL, "s"),
                    vol.Required(
                        CONF_MINUTES_AFTER, default=opts.get(CONF_MINUTES_AFTER, DEFAULT_MINUTES_AFTER)
                    ): num(10, 180, "min"),
                    vol.Required(
                        CONF_MAX_DEPARTURES, default=opts.get(CONF_MAX_DEPARTURES, DEFAULT_MAX_DEPARTURES)
                    ): num(1, 30, ""),
                }
            ),
        )
