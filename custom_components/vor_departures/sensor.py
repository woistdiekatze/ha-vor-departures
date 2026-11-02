"""Sensor for VOR Abfahrten."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN
from .coordinator import VorConfigEntry, VorCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VorConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the departures sensor."""
    async_add_entities([VorNextDepartureSensor(entry.runtime_data, entry)])


class VorNextDepartureSensor(CoordinatorEntity[VorCoordinator], SensorEntity):
    """State = time of the next departure, attributes = the upcoming list."""

    _attr_has_entity_name = True
    _attr_translation_key = "next_departure"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:bus-clock"
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator: VorCoordinator, entry: VorConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_next_departure"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=coordinator.stop.name,
            manufacturer="VOR / VAO",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> datetime | None:
        data = self.coordinator.data or []
        return data[0].effective if data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        coord = self.coordinator
        departures = []
        for dep in coord.data or []:
            departures.append(
                {
                    "line": dep.line,
                    "category": dep.category,
                    "direction": dep.direction,
                    "planned": dep.planned.isoformat(),
                    "departure": dep.effective.isoformat(),
                    "delay_min": dep.delay_min,
                    "platform": dep.platform,
                    "stop": dep.stop,
                    "cancelled": dep.cancelled,
                }
            )
        return {
            "stop": coord.stop.name,
            "stop_id": coord.stop.ext_id,
            "line_filter": coord.lines,
            "direction_filter": coord.directions,
            "departures": departures,
        }
