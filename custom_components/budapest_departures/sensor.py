"""Next-departure sensor; the full board is in the attributes."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, CONF_MAX_DEPARTURES, DEFAULT_MAX_DEPARTURES, DOMAIN
from .coordinator import FutarConfigEntry, FutarCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FutarConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensor."""
    async_add_entities([NextDepartureSensor(entry.runtime_data)])


class NextDepartureSensor(CoordinatorEntity[FutarCoordinator], SensorEntity):
    """Minutes until the next departure."""

    _attr_has_entity_name = True
    _attr_translation_key = "next_departure"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_attribution = ATTRIBUTION
    # The board changes every poll: keep it out of the recorder database.
    _unrecorded_attributes = frozenset({"departures", "alert"})

    def __init__(self, coordinator: FutarCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.stop_id}_next_departure"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.stop_id)},
            name=coordinator.stop_name,
            manufacturer="BKK FUTÁR",
            model=coordinator.stop_id,
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def _departures(self) -> list[dict[str, Any]]:
        return (self.coordinator.data or {}).get("departures", [])

    @property
    def native_value(self) -> int | None:
        deps = self._departures
        return deps[0]["minutes"] if deps else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        limit = self.coordinator.config_entry.options.get(CONF_MAX_DEPARTURES, DEFAULT_MAX_DEPARTURES)
        data = self.coordinator.data or {}
        return {
            "stop_id": self.coordinator.stop_id,
            "stop_name": data.get("stop_name", self.coordinator.stop_name),
            "departures": [
                {k: v for k, v in dep.items() if k not in ("trip_id", "route_id", "stop_sequence")}
                for dep in self._departures[:limit]
            ],
            "alert": data.get("alert", ""),
        }
