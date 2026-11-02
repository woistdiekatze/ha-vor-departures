"""Config flow for VOR Abfahrten."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
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
)

from .api import DEFAULT_AID, Stop, VorClient, VorConnectionError, VorError
from .const import (
    CONF_ACCESS_ID,
    CONF_DIRECTIONS,
    CONF_DURATION,
    CONF_INCLUDE_CANCELLED,
    CONF_LINES,
    CONF_MAX_DEPARTURES,
    CONF_QUERY,
    CONF_SCAN_INTERVAL,
    CONF_STOP,
    CONF_STOP_ID,
    CONF_STOP_LID,
    CONF_STOP_NAME,
    DEFAULT_DURATION,
    DEFAULT_MAX_DEPARTURES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)


def _box(minimum: int, maximum: int, unit: str | None = None) -> NumberSelector:
    config: dict[str, Any] = {
        "min": minimum,
        "max": maximum,
        "step": 1,
        "mode": NumberSelectorMode.BOX,
    }
    if unit:
        config["unit_of_measurement"] = unit
    return NumberSelector(NumberSelectorConfig(**config))


def _filters_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(CONF_LINES, default=defaults.get(CONF_LINES, "")): str,
            vol.Optional(CONF_DIRECTIONS, default=defaults.get(CONF_DIRECTIONS, "")): str,
            vol.Required(
                CONF_MAX_DEPARTURES,
                default=defaults.get(CONF_MAX_DEPARTURES, DEFAULT_MAX_DEPARTURES),
            ): _box(1, 20),
            vol.Required(
                CONF_DURATION, default=defaults.get(CONF_DURATION, DEFAULT_DURATION)
            ): _box(15, 1440, "min"),
            vol.Required(
                CONF_INCLUDE_CANCELLED,
                default=defaults.get(CONF_INCLUDE_CANCELLED, False),
            ): bool,
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): _box(30, 600, "s"),
        }
    )


def _clean_filters(user_input: dict[str, Any]) -> dict[str, Any]:
    return {
        CONF_LINES: (user_input.get(CONF_LINES) or "").strip(),
        CONF_DIRECTIONS: (user_input.get(CONF_DIRECTIONS) or "").strip(),
        CONF_MAX_DEPARTURES: int(user_input[CONF_MAX_DEPARTURES]),
        CONF_DURATION: int(user_input[CONF_DURATION]),
        CONF_INCLUDE_CANCELLED: bool(user_input[CONF_INCLUDE_CANCELLED]),
        CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
    }


class VorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Search a stop, pick it, set filters."""

    VERSION = 1

    def __init__(self) -> None:
        self._access_id = DEFAULT_AID
        self._stops: dict[str, Stop] = {}
        self._stop: Stop | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._access_id = (user_input.get(CONF_ACCESS_ID) or DEFAULT_AID).strip()
            client = VorClient(async_get_clientsession(self.hass), self._access_id)
            try:
                stops = await client.search_stops(user_input[CONF_QUERY])
            except VorConnectionError:
                errors["base"] = "cannot_connect"
            except VorError:
                errors["base"] = "unknown"
            else:
                if not stops:
                    errors["base"] = "no_stops"
                else:
                    self._stops = {s.ext_id: s for s in stops}
                    return await self.async_step_select()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_QUERY): str,
                    vol.Optional(CONF_ACCESS_ID, default=DEFAULT_AID): str,
                }
            ),
            errors=errors,
        )

    async def async_step_select(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._stop = self._stops[user_input[CONF_STOP]]
            return await self.async_step_filters()

        options = [
            SelectOptionDict(value=s.ext_id, label=f"{s.name} ({s.ext_id})")
            for s in self._stops.values()
        ]
        return self.async_show_form(
            step_id="select",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_STOP): SelectSelector(
                        SelectSelectorConfig(
                            options=options, mode=SelectSelectorMode.DROPDOWN
                        )
                    )
                }
            ),
        )

    async def async_step_filters(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._stop is not None
        if user_input is not None:
            return self.async_create_entry(
                title=self._stop.name,
                data={
                    CONF_ACCESS_ID: self._access_id,
                    CONF_STOP_ID: self._stop.ext_id,
                    CONF_STOP_NAME: self._stop.name,
                    CONF_STOP_LID: self._stop.lid,
                },
                options=_clean_filters(user_input),
            )
        return self.async_show_form(
            step_id="filters",
            data_schema=_filters_schema({}),
            description_placeholders={"stop": self._stop.name},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> VorOptionsFlow:
        return VorOptionsFlow()


class VorOptionsFlow(OptionsFlow):
    """Change filters later."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=_clean_filters(user_input))
        return self.async_show_form(
            step_id="init",
            data_schema=_filters_schema(dict(self.config_entry.options)),
        )
