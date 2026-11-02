"""Data update coordinator for VOR Abfahrten."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    Departure,
    Stop,
    VorClient,
    VorError,
    filter_departures,
    split_list,
)
from .const import (
    CONF_ACCESS_ID,
    CONF_DIRECTIONS,
    CONF_DURATION,
    CONF_INCLUDE_CANCELLED,
    CONF_LINES,
    CONF_MAX_DEPARTURES,
    CONF_SCAN_INTERVAL,
    CONF_STOP_ID,
    CONF_STOP_LID,
    CONF_STOP_NAME,
    DEFAULT_DURATION,
    DEFAULT_MAX_DEPARTURES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

type VorConfigEntry = ConfigEntry[VorCoordinator]


class VorCoordinator(DataUpdateCoordinator[list[Departure]]):
    """Fetches departures and applies the user's filters."""

    config_entry: VorConfigEntry

    def __init__(self, hass: HomeAssistant, entry: VorConfigEntry) -> None:
        opts = entry.options
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.data[CONF_STOP_NAME]}",
            update_interval=timedelta(
                seconds=max(30, int(opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)))
            ),
        )
        self.client = VorClient(
            async_get_clientsession(hass), entry.data.get(CONF_ACCESS_ID)
        )
        self.stop = Stop(
            ext_id=entry.data[CONF_STOP_ID],
            name=entry.data[CONF_STOP_NAME],
            lid=entry.data.get(CONF_STOP_LID),
        )
        self.lines = split_list(opts.get(CONF_LINES))
        self.directions = split_list(opts.get(CONF_DIRECTIONS))
        self.max_departures = int(opts.get(CONF_MAX_DEPARTURES, DEFAULT_MAX_DEPARTURES))
        self.duration = int(opts.get(CONF_DURATION, DEFAULT_DURATION))
        self.include_cancelled = bool(opts.get(CONF_INCLUDE_CANCELLED, False))

    async def _async_update_data(self) -> list[Departure]:
        try:
            departures = await self.client.get_departures(
                self.stop,
                dt_util.get_default_time_zone(),
                duration_min=self.duration,
            )
        except VorError as err:
            raise UpdateFailed(f"Fehler beim Abruf der VOR-Abfahrten: {err}") from err

        filtered = filter_departures(
            departures,
            lines=self.lines,
            directions=self.directions,
            include_cancelled=self.include_cancelled,
        )
        return filtered[: self.max_departures]
