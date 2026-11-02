"""Offline test for api.py using hand-built HAFAS-style responses.

Run:  python3 -I tests/test_api.py
"""

import asyncio
import importlib.util
import pathlib
from zoneinfo import ZoneInfo

path = pathlib.Path(__file__).resolve().parent.parent / "custom_components/vor_departures/api.py"
spec = importlib.util.spec_from_file_location("vor_api", path)
api = importlib.util.module_from_spec(spec)
import sys; sys.modules["vor_api"] = api
spec.loader.exec_module(api)

TZ = ZoneInfo("Europe/Vienna")

LOC_RES = {
    "match": {
        "locL": [
            {"lid": "A=1@O=Kapelln@L=490001234@", "type": "S", "name": "Kapelln", "extId": "490001234"},
            {"lid": "A=1@O=Kapelln Hauptstraße@L=490005678@", "type": "S", "name": "Kapelln Hauptstraße"},
            {"type": "A", "name": "Kapelln Adresse"},
            {"lid": "dup", "type": "S", "name": "Kapelln", "extId": "490001234"},
        ]
    }
}

BOARD_RES = {
    "common": {
        "locL": [{"name": "Kapelln Hauptstraße"}, {"name": "Kapelln Schule"}],
        "prodL": [
            {"name": "Bus 1234", "number": "1234", "prodCtx": {"catOutS": "Bus", "line": "1234"}},
            {"name": "Bus 1240", "number": "1240", "prodCtx": {"catOutS": "Bus", "line": "1240"}},
        ],
    },
    "jnyL": [
        {"date": "20261102", "prodX": 1, "dirTxt": "Böheimkirchen Bahnhof",
         "stbStop": {"locX": 1, "dTimeS": "195000", "dTimeR": "195500", "dPlatfS": "2"}},
        {"date": "20261102", "prodX": 0, "dirTxt": "Tulln Bahnhof",
         "stbStop": {"locX": 0, "dTimeS": "193000", "dPlatfR": {"txt": "1"}}},
        {"date": "20261102", "prodX": 0, "dirTxt": "Tulln Bahnhof",
         "stbStop": {"locX": 0, "dTimeS": "200000", "dCncl": True}},
        {"date": "20261102", "prodX": 0, "dirTxt": "Tulln Bahnhof",
         "stbStop": {"locX": 0, "dTimeS": "01001000", "dTimeR": "01001000"}},
    ],
}


def main() -> None:
    stops = api.parse_stops(LOC_RES)
    assert [s.ext_id for s in stops] == ["490001234", "490005678"], stops
    assert stops[1].ext_id == "490005678"  # derived from lid

    deps = api.parse_departures(BOARD_RES, TZ)
    assert len(deps) == 4
    assert [d.line for d in deps] == ["1234", "1240", "1234", "1234"], [d.line for d in deps]
    assert deps[0].platform == "1" and deps[1].platform == "2"
    assert deps[1].delay_min == 5 and deps[0].delay_min is None
    assert deps[1].stop == "Kapelln Schule"
    assert deps[2].cancelled
    assert deps[3].planned.day == 3 and deps[3].planned.hour == 0 and deps[3].planned.minute == 10  # next-day offset

    # filters
    f = api.filter_departures
    assert len(f(deps)) == 3  # cancelled dropped
    assert len(f(deps, include_cancelled=True)) == 4
    assert [d.line for d in f(deps, lines=["1240"])] == ["1240"]
    assert [d.line for d in f(deps, lines=["bus 1240"])] == ["1240"]
    assert len(f(deps, lines=["!1234"])) == 1
    assert all("Tulln" in d.direction for d in f(deps, directions=["tulln"]))
    assert [d.line for d in f(deps, directions=["!tulln"])] == ["1240"]
    assert [d.line for d in f(deps, lines=["1234"], directions=["Tulln"])] == ["1234", "1234"]
    assert api.split_list("1234, 1240;  ") == ["1234", "1240"]

    # client: request shape + error handling with a fake session
    sent = {}

    class FakeResp:
        def __init__(self, payload):
            self._p = payload
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        def raise_for_status(self): pass
        async def json(self, content_type=None): return self._p

    class FakeSession:
        def __init__(self, payload): self.payload = payload
        def post(self, url, json=None, timeout=None):
            sent["url"], sent["body"] = url, json
            return FakeResp(self.payload)

    async def run():
        ok = {"svcResL": [{"meth": "LocMatch", "err": "OK", "res": LOC_RES}]}
        c = api.VorClient(FakeSession(ok))
        res = await c.search_stops("Kapelln")
        assert len(res) == 2
        assert sent["body"]["svcReqL"][0]["req"]["input"]["loc"]["name"] == "Kapelln?"
        assert sent["body"]["auth"] == {"aid": "nextgen", "type": "AID"}

        board = {"svcResL": [{"meth": "StationBoard", "err": "OK", "res": BOARD_RES}]}
        c = api.VorClient(FakeSession(board))
        out = await c.get_departures(res[0], TZ)
        assert len(out) == 4
        r = sent["body"]["svcReqL"][0]["req"]
        assert r["type"] == "DEP" and r["stbLoc"] == {"lid": res[0].lid}

        bad = {"svcResL": [{"err": "AUTH", "errTxt": "denied"}]}
        try:
            await api.VorClient(FakeSession(bad)).search_stops("x")
        except api.VorApiError as err:
            assert "AUTH" in str(err)
        else:
            raise AssertionError("expected VorApiError")

    asyncio.run(run())
    print("OK – alle Tests bestanden")


main()
