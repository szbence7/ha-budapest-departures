"""Bundled card registration and standalone migration."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest
from homeassistant.components.lovelace import LOVELACE_DATA
from homeassistant.components.lovelace.resources import ResourceStorageCollection
from custom_components.budapest_departures.frontend import CARD_PATH, CARD_URL, async_register_resource, async_setup_frontend


def storage(hass, items):
    resources = MagicMock(spec=ResourceStorageCollection)
    resources.async_get_info = AsyncMock()
    resources.async_items.return_value = items
    for method in ("async_create_item", "async_update_item", "async_delete_item"):
        setattr(resources, method, AsyncMock())
    hass.data[LOVELACE_DATA] = SimpleNamespace(resources=resources)
    return resources


async def test_new_install_and_static_path(hass):
    resources = storage(hass, [])
    hass.http = SimpleNamespace(async_register_static_paths=AsyncMock())
    await async_setup_frontend(hass)
    path = hass.http.async_register_static_paths.call_args.args[0][0]
    assert path.url_path == CARD_PATH
    assert path.path.endswith("/www/dot-matrix-departure-card.js")
    resources.async_create_item.assert_awaited_once_with({"res_type": "module", "url": CARD_URL})


async def test_repeated_setup_does_not_duplicate(hass):
    resources = storage(hass, [{"id": "card", "url": CARD_URL, "type": "module"}])
    await async_register_resource(hass)
    await async_register_resource(hass)
    resources.async_create_item.assert_not_awaited()
    resources.async_update_item.assert_not_awaited()
    resources.async_delete_item.assert_not_awaited()


@pytest.mark.parametrize("old_url", [CARD_PATH + "?v=old", "/hacsfiles/dot-matrix-departure-card/dot-matrix-departure-card.js?hacstag=123", "/local/dot-matrix-departure-card.js"])
async def test_upgrade_preserves_resource_id(hass, old_url):
    resources = storage(hass, [{"id": "card", "url": old_url, "type": "module"}])
    await async_register_resource(hass)
    resources.async_update_item.assert_awaited_once_with("card", {"res_type": "module", "url": CARD_URL})
    resources.async_create_item.assert_not_awaited()


async def test_duplicate_cleanup_leaves_other_resources(hass):
    resources = storage(hass, [
        {"id": "bundled", "url": CARD_URL, "type": "module"},
        {"id": "legacy", "url": "/local/dot-matrix-departure-card.js", "type": "module"},
        {"id": "other", "url": "/local/other.js", "type": "module"},
    ])
    await async_register_resource(hass)
    resources.async_delete_item.assert_awaited_once_with("legacy")
    resources.async_update_item.assert_not_awaited()


async def test_yaml_resources_are_not_modified(hass, caplog):
    resources = SimpleNamespace(data=[])
    hass.data[LOVELACE_DATA] = SimpleNamespace(resources=resources)
    await async_register_resource(hass)
    assert resources.data == []
    assert CARD_URL in caplog.text


async def test_real_storage_and_served_javascript(hass, hass_client):
    from homeassistant.setup import async_setup_component
    assert await async_setup_component(hass, "lovelace", {"lovelace": {}})
    await async_setup_frontend(hass)
    await async_register_resource(hass)
    resources = hass.data[LOVELACE_DATA].resources
    assert sum(item["url"] == CARD_URL for item in resources.async_items()) == 1
    client = await hass_client()
    response = await client.get(CARD_URL)
    assert response.status == 200
    assert 'customElements.define("dot-matrix-departure-card"' in await response.text()
