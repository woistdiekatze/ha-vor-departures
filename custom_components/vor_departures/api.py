"""Minimal async client for the VAO / VOR AnachB HAFAS interface.

This module intentionally has no Home Assistant imports so it can be tested
on its own.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any

import aiohttp

API_URL = "https://vao.demo.hafas.de/gate"
DEFAULT_AID = "nextgen"
API_VERSION = "1.73"


class VorError(Exception):
    """Base error."""


class VorConnectionError(VorError):
    """Network / HTTP problem."""


class VorApiError(VorError):
    """The API answered with an error."""


@dataclass
class Stop:
    """A stop or meta stop returned by the location search."""

    ext_id: str
    name: str
    lid: str | None = None


@dataclass
class Departure:
    """A single departure."""

    line: str
    category: str
    direction: str
    planned: datetime
    realtime: datetime | None
    platform: str | None
    stop: str | None
    cancelled: bool
    delay_min: int | None
    line_keys: frozenset[str] = field(default_factory=frozenset)

    @property
    def effective(self) -> datetime:
        """Real-time departure if known, otherwise the planned one."""
        return self.realtime or self.planned


def _norm(value: str) -> str:
    return re.sub(r"\s+", "", value or "").lower()


def split_list(value: str | None) -> list[str]:
    """Split a user supplied 'a, b; c' string into a clean list."""
    if not value:
        return []
    return [part.strip() for part in re.split(r"[,;]", value) if part.strip()]


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


def _parse_dt(date: str | None, value: str | None, tz: tzinfo) -> datetime | None:
    """Parse HAFAS date (YYYYMMDD) + time (HHMMSS or DDHHMMSS)."""
    if not date or not value:
        return None
    day_offset = 0
    if len(value) == 8:  # DDHHMMSS, DD = days after `date`
        day_offset = int(value[:2])
        value = value[2:]
    base = datetime.strptime(date, "%Y%m%d") + timedelta(days=day_offset)
    return base.replace(
        hour=int(value[0:2]),
        minute=int(value[2:4]),
        second=int(value[4:6]) if len(value) >= 6 else 0,
        tzinfo=tz,
    )


def _platform(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("txt")
    return str(value) if value not in (None, "") else None


def _stop_id_from_lid(lid: str | None) -> str | None:
    match = re.search(r"@L=(\d+)@", lid or "")
    return match.group(1) if match else None


def parse_stops(res: dict[str, Any]) -> list[Stop]:
    """Parse a LocMatch result."""
    stops: list[Stop] = []
    seen: set[str] = set()
    for loc in res.get("match", {}).get("locL", []):
        if loc.get("type") not in (None, "S"):
            continue
        lid = loc.get("lid")
        ext_id = loc.get("extId") or _stop_id_from_lid(lid)
        name = loc.get("name")
        if not ext_id or not name or ext_id in seen:
            continue
        seen.add(ext_id)
        stops.append(Stop(ext_id=str(ext_id), name=name, lid=lid))
    return stops


def parse_departures(res: dict[str, Any], tz: tzinfo) -> list[Departure]:
    """Parse a StationBoard result."""
    common = res.get("common", {})
    locs = common.get("locL", [])
    prods = common.get("prodL", [])
    departures: list[Departure] = []

    for jny in res.get("jnyL", []):
        stb = jny.get("stbStop") or {}
        date = jny.get("date")
        planned = _parse_dt(date, stb.get("dTimeS"), tz)
        if planned is None:
            continue
        realtime = _parse_dt(date, stb.get("dTimeR"), tz)

        prod: dict[str, Any] = {}
        prod_x = jny.get("prodX")
        if isinstance(prod_x, int) and 0 <= prod_x < len(prods):
            prod = prods[prod_x]
        ctx = prod.get("prodCtx") or {}

        name = (prod.get("name") or "").strip()
        line = (ctx.get("line") or name).strip()
        category = (ctx.get("catOutS") or ctx.get("catOut") or "").strip()

        keys = {_norm(line), _norm(name), _norm(prod.get("number") or "")}
        if " " in name:
            keys.add(_norm(name.split(" ", 1)[1]))
        keys.discard("")

        stop_name = None
        loc_x = stb.get("locX")
        if isinstance(loc_x, int) and 0 <= loc_x < len(locs):
            stop_name = locs[loc_x].get("name")

        delay = None
        if realtime is not None:
            delay = round(
                (realtime.astimezone(timezone.utc) - planned.astimezone(timezone.utc)).total_seconds()
                / 60
            )

        departures.append(
            Departure(
                line=line,
                category=category,
                direction=(jny.get("dirTxt") or "").strip(),
                planned=planned,
                realtime=realtime,
                platform=_platform(stb.get("dPlatfR")) or _platform(stb.get("dPlatfS")),
                stop=stop_name,
                cancelled=bool(stb.get("dCncl") or jny.get("isCncl")),
                delay_min=delay,
                line_keys=frozenset(keys),
            )
        )

    departures.sort(key=lambda d: d.effective)
    return departures


# --------------------------------------------------------------------------
# Filtering
# --------------------------------------------------------------------------


def _split_patterns(patterns: list[str]) -> tuple[list[str], list[str]]:
    include = [p for p in patterns if not p.startswith("!")]
    exclude = [p[1:].strip() for p in patterns if p.startswith("!") and p[1:].strip()]
    return include, exclude


def filter_departures(
    departures: list[Departure],
    lines: list[str] | None = None,
    directions: list[str] | None = None,
    include_cancelled: bool = False,
) -> list[Departure]:
    """Filter by line and direction.

    * ``lines``: exact match (ignoring case and spaces) against the line
      name, e.g. ``["1234", "S 40"]``.
    * ``directions``: case-insensitive substring match on the destination
      text, e.g. ``["Tulln"]``.
    * A leading ``!`` excludes instead of includes (``["!Tulln"]``).
    """
    line_inc, line_exc = _split_patterns([_norm(x) if not x.startswith("!") else "!" + _norm(x[1:]) for x in (lines or [])])
    dir_inc, dir_exc = _split_patterns([x.lower() for x in (directions or [])])

    result: list[Departure] = []
    for dep in departures:
        if dep.cancelled and not include_cancelled:
            continue
        if line_inc and not (dep.line_keys & set(line_inc)):
            continue
        if line_exc and (dep.line_keys & set(line_exc)):
            continue
        direction = dep.direction.lower()
        if dir_inc and not any(p in direction for p in dir_inc):
            continue
        if dir_exc and any(p in direction for p in dir_exc):
            continue
        result.append(dep)
    return result


# --------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------


class VorClient:
    """Talks to the VAO HAFAS gateway."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        access_id: str = DEFAULT_AID,
        url: str = API_URL,
    ) -> None:
        self._session = session
        self._aid = access_id or DEFAULT_AID
        self._url = url

    async def _call(self, meth: str, req: dict[str, Any]) -> dict[str, Any]:
        body = {
            "svcReqL": [{"req": req, "meth": meth, "id": "1|1|"}],
            "client": {"id": "VAO", "v": "1", "type": "AND", "name": "nextgen"},
            "ver": API_VERSION,
            "lang": "de",
            "auth": {"aid": self._aid, "type": "AID"},
        }
        try:
            async with self._session.post(
                self._url, json=body, timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise VorConnectionError(str(err)) from err

        if data.get("err") not in (None, "OK"):
            raise VorApiError(f"{data.get('err')}: {data.get('errTxt', '')}")
        try:
            svc = data["svcResL"][0]
        except (KeyError, IndexError, TypeError) as err:
            raise VorApiError("Unexpected response structure") from err
        if svc.get("err") not in (None, "OK"):
            raise VorApiError(f"{svc.get('err')}: {svc.get('errTxt', '')}")
        return svc.get("res", {})

    async def search_stops(self, query: str, max_results: int = 15) -> list[Stop]:
        """Search stops / meta stops by name."""
        name = query.strip()
        if not name.endswith("?"):
            name += "?"  # HAFAS wildcard
        res = await self._call(
            "LocMatch",
            {
                "input": {
                    "field": "S",
                    "loc": {"name": name, "type": "ALL"},
                    "maxLoc": max_results,
                }
            },
        )
        return parse_stops(res)

    async def get_departures(
        self,
        stop: Stop,
        tz: tzinfo,
        duration_min: int = 120,
        max_journeys: int = 60,
    ) -> list[Departure]:
        """Fetch upcoming departures (unfiltered)."""
        now = datetime.now(tz)
        if stop.lid:
            stb_loc: dict[str, Any] = {"lid": stop.lid}
        else:
            stb_loc = {"type": "S", "extId": stop.ext_id, "name": stop.name}
        res = await self._call(
            "StationBoard",
            {
                "type": "DEP",
                "date": now.strftime("%Y%m%d"),
                "time": now.strftime("%H%M%S"),
                "stbLoc": stb_loc,
                "dur": duration_min,
                "maxJny": max_journeys,
            },
        )
        return parse_departures(res, tz)
