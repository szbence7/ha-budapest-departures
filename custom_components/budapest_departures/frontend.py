"""Serve and register the bundled dashboard card."""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlsplit

from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace import LOVELACE_DATA
from homeassistant.components.lovelace.resources import ResourceStorageCollection
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)
CARD_PATH = "/budapest_departures/dot-matrix-departure-card.js"
CARD_URL = f"{CARD_PATH}?v=0.4.0"
LEGACY_PATHS = {
    "/hacsfiles/dot-matrix-departure-card/dot-matrix-departure-card.js",
    "/local/dot-matrix-departure-card.js",
}


async def async_setup_frontend(hass: HomeAssistant) -> None:
    """Expose only the bundled card, never the integration's Python files."""
    await hass.http.async_register_static_paths([
        StaticPathConfig(
            CARD_PATH,
            str(Path(__file__).parent / "www" / "dot-matrix-departure-card.js"),
            False,
        )
    ])
    await async_register_resource(hass)


async def async_register_resource(hass: HomeAssistant) -> None:
    """Create/update one module resource, migrating known standalone installs."""
    resources = hass.data[LOVELACE_DATA].resources
    if not isinstance(resources, ResourceStorageCollection):
        _LOGGER.warning(
            "Lovelace resources are managed in YAML. Add url: %s with type: module "
            "and remove any old dot-matrix-departure-card resource", CARD_URL
        )
        return

    # Load the collection before inspecting it, including on a fresh HA startup.
    await resources.async_get_info()
    matches = [
        item for item in resources.async_items()
        if urlsplit(item["url"]).path in {CARD_PATH, *LEGACY_PATHS}
    ]
    if not matches:
        await resources.async_create_item({"res_type": "module", "url": CARD_URL})
        return

    primary = next(
        (item for item in matches if urlsplit(item["url"]).path == CARD_PATH),
        matches[0],
    )
    if primary["url"] != CARD_URL or primary["type"] != "module":
        await resources.async_update_item(
            primary["id"], {"res_type": "module", "url": CARD_URL}
        )
    for item in matches:
        if item["id"] != primary["id"]:
            await resources.async_delete_item(item["id"])
