#!/usr/bin/env python3
"""Offline tests for place_search_tool.

No Google: a stub googlemaps client returning the legacy text-search and Place
Details shapes, so the Details cap and its failure handling are reachable.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vital_agent_resource_app.tools.place_search import place_search_tool as module
from vital_agent_resource_app.tools.place_search.models import PlaceSearchInput
from vital_agent_resource_app.tools.place_search.place_search_tool import (
    DETAILS_FIELDS, PlaceSearchTool,
)
from vital_agent_resource_app.tools.tool_request import ToolRequest

PASSED, FAILED = [], []


def check(name, condition, detail=''):
    if condition:
        PASSED.append(name)
        print(f"  PASS  {name}")
    else:
        FAILED.append(f"{name}: {detail}")
        print(f"  FAIL  {name} -- {detail}")


def text_result(i):
    return {
        "place_id": f"pid-{i}",
        "name": f"Roto-Rooter {i}",
        "formatted_address": f"{i} Main St, Cincinnati, OH",
        "geometry": {"location": {"lat": 39.1 + i / 100, "lng": -84.5}},
        "business_status": "OPERATIONAL",
        "icon": "https://maps.example/icon.png",
        "types": ["plumber", "point_of_interest"],
        "rating": 4.5,
        "user_ratings_total": 100 + i,
    }


class StubGmaps:
    """The two calls search_place makes: places() and place()."""

    def __init__(self, results, fail_details=(), fail_search=False):
        self.results = results
        self.fail_details = set(fail_details)
        self.fail_search = fail_search
        self.details_calls = []

    def places(self, query):
        if self.fail_search:
            raise RuntimeError("REQUEST_DENIED")
        return {"results": self.results}

    def place(self, place_id, fields):
        self.details_calls.append((place_id, list(fields)))
        if place_id in self.fail_details:
            raise RuntimeError("OVER_QUERY_LIMIT")
        return {"result": {
            "formatted_phone_number": f"(513) 555-{place_id[-1]}",
            "website": f"https://{place_id}.example",
            "url": f"https://maps.google.com/?cid={place_id}",
            "vicinity": "Cincinnati",
        }}


def run(stub, config=None):
    original = module.googlemaps.Client
    module.googlemaps.Client = lambda key=None: stub
    try:
        tool = PlaceSearchTool({"api_key": "test", **(config or {})})
        return tool.search_place("Roto Rooter Cincinnati")
    finally:
        module.googlemaps.Client = original


def test_text_search_fields():
    print("\ntext-search fields")
    stub = StubGmaps([text_result(1)])
    p = run(stub)[0]
    check('rating comes from text search', p.rating == 4.5, str(p.rating))
    check('review count comes from text search', p.user_ratings_total == 101, str(p.user_ratings_total))
    check('lat/lon come from text search', (p.latitude, p.longitude) == (39.11, -84.5),
          str((p.latitude, p.longitude)))
    check('status, icon, types come from text search',
          p.business_status == 'OPERATIONAL' and p.icon and p.types == ["plumber", "point_of_interest"],
          str(p))
    check('Details fills contact fields',
          p.formatted_phone_number and p.website and p.url and p.vicinity == 'Cincinnati', str(p))
    check('Details asks only for what it reads',
          stub.details_calls[0][1] == DETAILS_FIELDS, str(stub.details_calls))


def test_details_cap():
    print("\nDetails cap")
    stub = StubGmaps([text_result(i) for i in range(20)])
    places = run(stub)
    check('all 20 results returned', len(places) == 20, str(len(places)))
    check('default makes 3 Details calls', len(stub.details_calls) == 3, str(len(stub.details_calls)))
    check('Details go to the top results',
          [c[0] for c in stub.details_calls] == ['pid-0', 'pid-1', 'pid-2'], str(stub.details_calls))
    check('top results have contact fields',
          all(p.formatted_phone_number and p.website for p in places[:3]), str(places[:3]))
    check('later results have null contact fields',
          all(p.formatted_phone_number is None and p.website is None and p.url is None
              and p.vicinity is None for p in places[3:]), str(places[3]))
    check('later results keep rating',
          all(p.rating == 4.5 for p in places[3:]), str(places[3]))

    stub = StubGmaps([text_result(i) for i in range(5)])
    run(stub, {"details_limit": "0"})
    check('details_limit=0 makes no Details calls', not stub.details_calls, str(stub.details_calls))

    stub = StubGmaps([text_result(i) for i in range(5)])
    run(stub, {"details_limit": "1"})
    check('details_limit=1 makes one call', len(stub.details_calls) == 1, str(stub.details_calls))

    for bad in ("junk", "-2"):
        stub = StubGmaps([text_result(i) for i in range(5)])
        run(stub, {"details_limit": bad})
        check(f'details_limit={bad} falls back to 3', len(stub.details_calls) == 3,
              str(len(stub.details_calls)))

    # A result with no place_id is skipped and does not use up a Details call.
    results = [dict(text_result(0), place_id=None)] + [text_result(i) for i in range(1, 5)]
    stub = StubGmaps(results)
    places = run(stub)
    check('result without place_id is skipped', len(places) == 4, str(len(places)))
    check('skipped result uses no Details call',
          [c[0] for c in stub.details_calls] == ['pid-1', 'pid-2', 'pid-3'], str(stub.details_calls))


def test_details_failure():
    print("\nDetails failure")
    stub = StubGmaps([text_result(i) for i in range(3)], fail_details={'pid-1'})
    places = run(stub)
    check('search survives a failed Details call', len(places) == 3, str(len(places)))
    p = places[1]
    check('failed result keeps text-search fields', p.rating == 4.5 and p.latitude is not None, str(p))
    check('failed result has null contact fields', p.formatted_phone_number is None, str(p))
    check('other results still get Details',
          places[0].formatted_phone_number and places[2].formatted_phone_number, str(places))


async def test_handle_tool_request():
    print("\nhandle_tool_request")
    original = module.googlemaps.Client
    try:
        request = ToolRequest(tool='place_search_tool',
                              tool_input=PlaceSearchInput(place_search_string='Roto Rooter'))

        module.googlemaps.Client = lambda key=None: StubGmaps([text_result(1)])
        response = await PlaceSearchTool({"api_key": "test"}).handle_tool_request(request)
        out = response.to_dict()['tool_output']
        check('success carries the rating on the wire',
              response.success and out['results'][0]['rating'] == 4.5
              and out['results'][0]['user_ratings_total'] == 101, str(out))

        module.googlemaps.Client = lambda key=None: StubGmaps([], fail_search=True)
        response = await PlaceSearchTool({"api_key": "test"}).handle_tool_request(request)
        check('text search failure is success=false',
              response.success is False and 'REQUEST_DENIED' in response.error_message,
              str(response))
    finally:
        module.googlemaps.Client = original


async def main():
    test_text_search_fields()
    test_details_cap()
    test_details_failure()
    await test_handle_tool_request()

    print("\n" + "=" * 60)
    print(f"Passed: {len(PASSED)}   Failed: {len(FAILED)}")
    for f in FAILED:
        print(f"  FAILED: {f}")
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
