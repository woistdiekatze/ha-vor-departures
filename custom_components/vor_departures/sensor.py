"""Sensors for VOR Abfahrten."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .api import Departure
from .const import ATTRIBUTION, DOMAIN
from .coordinator import VorConfigEntry, VorCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VorConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the overview sensor plus one sensor per departure slot."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [VorNextDepartureSensor(coordinator, entry)]
    entities.extend(
        VorDepartureSensor(coordinator, entry, index)
        for index in range(coordinator.max_departures)
    )
    async_add_entities(entities)


def _hhmm(value: datetime) -> str:
    return dt_util.as_local(value).strftime("%H:%M")


def _describe(dep: Departure) -> dict[str, Any]:
    """Attributes describing one departure."""
    attrs: dict[str, Any] = {
        "line": dep.line,
        "category": dep.category,
        "direction": dep.direction,
        "planned": dep.planned.isoformat(),
        "expected": dep.effective.isoformat(),
        "planned_time": _hhmm(dep.planned),
        "expected_time": _hhmm(dep.effective),
        "delay_min": dep.delay_min,
        "platform": dep.platform,
        "stop": dep.stop,
        "cancelled": dep.cancelled,
    }
    summary = f"{dep.line} → {dep.direction} · {attrs['expected_time']}"
    if dep.delay_min:
        summary += f" ({dep.delay_min:+d})"
    if dep.cancelled:
        summary += " · Ausfall"
    attrs["summary"] = summary
    return attrs


class _VorBaseSensor(CoordinatorEntity[VorCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator: VorCoordinator, entry: VorConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry_id = entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=coordinator.stop.name,
            manufacturer="VOR / VAO",
            entry_type=DeviceEntryType.SERVICE,
        )


class VorNextDepartureSensor(_VorBaseSensor):
    """State = next departure, attribute `departures` = the full list."""

    _attr_translation_key = "next_departure"
    _attr_icon = "mdi:bus-clock"

    def __init__(self, coordinator: VorCoordinator, entry: VorConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_next_departure"

    @property
    def native_value(self) -> datetime | None:
        data = self.coordinator.data or []
        return data[0].effective if data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        coord = self.coordinator
        return {
            "stop": coord.stop.name,
            "stop_id": coord.stop.ext_id,
            "line_filter": coord.lines,
            "direction_filter": coord.directions,
            "departures": [_describe(dep) for dep in coord.data or []],
        }


class VorDepartureSensor(_VorBaseSensor):
    """One departure slot: state = expected time, attributes = details."""

    _attr_translation_key = "departure"
    _attr_icon = "mdi:bus"

    def __init__(
        self, coordinator: VorCoordinator, entry: VorConfigEntry, index: int
    ) -> None:
        super().__init__(coordinator, entry)
        self._index = index
        self._attr_unique_id = f"{entry.entry_id}_departure_{index + 1}"
        self._attr_translation_placeholders = {"n": str(index + 1)}

    @property
    def _departure(self) -> Departure | None:
        data = self.coordinator.data or []
        return data[self._index] if self._index < len(data) else None

    @property
    def native_value(self) -> datetime | None:
        dep = self._departure
        return dep.effective if dep else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        dep = self._departure
        return _describe(dep) if dep else None
