#!/usr/bin/env python3
"""Offline tests for how a ToolResponse goes on the wire.

A failed response must not carry a result set the tool never produced: a
synthetic {"results": []} on an error is indistinguishable from a search that
genuinely matched nothing. Upstream failures still travel as HTTP 200 -- the
body is the signal, not the status code.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from vital_agent_resource_app import app as app_module
from vital_agent_resource_app.auth.dependencies import get_current_user_dependency
from vital_agent_resource_app.data_models.auth_models import AuthenticatedUser
from vital_agent_resource_app.tools.tool_response import ToolResponse

PASSED, FAILED = [], []


def check(name, condition, detail=''):
    if condition:
        PASSED.append(name)
        print(f"  PASS  {name}")
    else:
        FAILED.append(f"{name}: {detail}")
        print(f"  FAIL  {name} -- {detail}")


def test_to_dict():
    print("\nto_dict")

    d = ToolResponse.create_error("boom", 0).to_dict()
    check('error keeps tool_output null', d['tool_output'] is None, str(d['tool_output']))
    check('error carries success=False', d['success'] is False, str(d['success']))
    check('error carries its message', d['error_message'] == 'boom', str(d['error_message']))

    d = ToolResponse.create_success(None, 0).to_dict()
    check('success with no output still defaults results',
          d['tool_output'] == {"results": []}, str(d['tool_output']))

    # The Union may coerce this dict into a tool model; only the defaulting matters.
    d = ToolResponse.create_success({"operation": "get"}, 0).to_dict()
    check('success dict without results still gets results',
          d['tool_output'].get('results') == [] and d['tool_output'].get('operation') == 'get',
          str(d['tool_output']))

    d = ToolResponse.create_success({"results": [{"title": "x"}]}, 0).to_dict()
    check('success results are untouched',
          d['tool_output']['results'] == [{"title": "x"}], str(d['tool_output']))


class StubTool:
    def __init__(self, response):
        self.response = response

    async def handle_tool_request(self, tool_request):
        return self.response


def post_with(client, response):
    stub = StubTool(response)
    original = app_module.tool_registry.get_tool_instance
    app_module.tool_registry.get_tool_instance = lambda name: stub
    try:
        return client.post('/tool', json={
            'tool': 'place_search_tool',
            'tool_input': {'place_search_string': 'Nowhere Cafe'},
        })
    finally:
        app_module.tool_registry.get_tool_instance = original


def test_endpoint():
    print("\nendpoint")

    app_module.app.dependency_overrides[get_current_user_dependency] = \
        lambda: AuthenticatedUser(user_id='test-user')
    try:
        client = TestClient(app_module.app)

        # A tool that caught its own failure: still 200, but the body says so
        # and does not pretend to be an empty search.
        resp = post_with(client, ToolResponse.create_error("upstream quota exhausted", 0))
        body = resp.json()
        check('caught failure is HTTP 200', resp.status_code == 200, str(resp.status_code))
        check('caught failure reports success=False', body.get('success') is False, str(body))
        check('caught failure has no results', body.get('tool_output') is None, str(body))
        check('caught failure carries the message',
              body.get('error_message') == 'upstream quota exhausted', str(body))

        # A genuine zero-result search must not regress.
        resp = post_with(client, ToolResponse.create_success(
            {"tool": "place_search_tool", "results": []}, 0))
        body = resp.json()
        check('zero results is HTTP 200', resp.status_code == 200, str(resp.status_code))
        check('zero results is success=True', body.get('success') is True, str(body))
        check('zero results has an empty result set',
              body.get('tool_output', {}).get('results') == [], str(body))
    finally:
        app_module.app.dependency_overrides.pop(get_current_user_dependency, None)


def main():
    test_to_dict()
    test_endpoint()

    print("\n" + "=" * 60)
    print(f"Passed: {len(PASSED)}   Failed: {len(FAILED)}")
    for f in FAILED:
        print(f"  FAILED: {f}")
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(main())
