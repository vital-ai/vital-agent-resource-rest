#!/usr/bin/env python3
"""
GitHub Issue Tool Client Test with JWT Authentication

Tests the github_issue_tool via the running service at /tool endpoint.
Requires: docker compose up (service on localhost:8008), Keycloak on localhost:8085.

Exercises the full request/response round-trip so the operation-keyed input
resolution and the GitHubIssueToolOutput union member are verified over HTTP,
not just in-process. Creates one issue in the scratch repo and closes it.
"""
import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

OWNER = os.getenv('GITHUB_TEST_OWNER')
REPO = os.getenv('GITHUB_TEST_REPO')


def get_keycloak_token(username, password, client_id=None, client_secret=None):
    """Get JWT token from Keycloak"""
    realm = os.getenv('KEYCLOAK_REALM', None)
    client_id = client_id or os.getenv('KEYCLOAK_CLIENT_ID', None)
    client_secret = client_secret or os.getenv('KEYCLOAK_CLIENT_SECRET')

    token_url = f"http://localhost:8085/realms/{realm}/protocol/openid-connect/token"

    data = {
        'grant_type': 'password',
        'client_id': client_id,
        'username': username,
        'password': password,
        'scope': 'openid profile email'
    }

    if client_secret:
        data['client_secret'] = client_secret

    try:
        response = requests.post(token_url, data=data)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error getting token: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        return None


def call_github_tool(headers, tool_input, label="", expect_status=200):
    """Send a request to the /tool endpoint and print results"""
    url = "http://localhost:8008/tool"
    payload = {"tool": "github_issue_tool", "tool_input": tool_input}

    print(f"\n{'─' * 60}")
    print(f"TEST: {label}")
    print(f"{'─' * 60}")
    print(f"Payload: {json.dumps(tool_input, indent=2)}")

    try:
        response = requests.post(url, json=payload, headers=headers)
        print(f"Status Code: {response.status_code}")

        if response.status_code != expect_status:
            print(f"❌ Expected {expect_status}, got {response.status_code}: {response.text[:300]}")
            return False

        if response.status_code != 200:
            # A rejected request body is the expected outcome for some tests.
            print(f"  Response: {response.text[:200]}")
            return {'validation_error': response.text}

        result = response.json()
        tool_output = result.get('tool_output', {})

        if tool_output.get('api_error'):
            print(f"\n⚠️  API Error:")
            print(f"  Status Code: {tool_output.get('api_status_code')}")
            print(f"  Error: {tool_output.get('api_error')[:200]}")
            return {'api_error': tool_output.get('api_error')}

        print(f"Operation: {tool_output.get('operation')}")
        print(f"Repository: {tool_output.get('repository')}")
        print(f"Duration: {result.get('duration_ms')}ms")
        print(f"Rate limit remaining: {tool_output.get('rate_limit_remaining')}")

        return tool_output
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    print("=" * 60)
    print("GitHub Issue Tool — Service Client Test")
    print("=" * 60)

    if not OWNER or not REPO:
        print("❌ Error: GITHUB_TEST_OWNER and GITHUB_TEST_REPO must be set")
        return

    username = os.getenv('KEYCLOAK_USER')
    password = os.getenv('KEYCLOAK_PASSWORD')

    if not username or not password:
        print("❌ Error: KEYCLOAK_USER and KEYCLOAK_PASSWORD must be set")
        return

    print("\n1. Getting JWT token...")
    token_response = get_keycloak_token(username, password)

    if not token_response:
        print("❌ Failed to get token")
        return

    access_token = token_response.get('access_token')
    if not access_token:
        print("❌ No access token in response")
        return

    print("✅ Token obtained")

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }

    passed = 0
    failed = 0
    issue_number = None

    # ── Test 1: List issues ───────────────────────────────────
    out = call_github_tool(headers, {
        "operation": "list_issues",
        "owner": OWNER,
        "repo": REPO,
        "state": "open",
        "max_results": 5
    }, "List open issues")

    if out and not out.get('api_error'):
        issues = out.get('issues', [])
        print(f"  Issues returned: {len(issues)} (truncated={out.get('truncated')})")
        for issue in issues[:3]:
            print(f"    #{issue.get('number')} [{issue.get('state')}] {issue.get('title')}")
        print("✅ PASSED")
        passed += 1
    else:
        print("❌ FAILED")
        failed += 1

    # ── Test 2: Create an issue ───────────────────────────────
    out = call_github_tool(headers, {
        "operation": "create_issue",
        "owner": OWNER,
        "repo": REPO,
        "title": "[client test] round-trip check",
        "body": "Created by github_issue_tool_client_test.py"
    }, "Create issue")

    if out and not out.get('api_error') and (out.get('issue') or {}).get('number'):
        issue_number = out['issue']['number']
        print(f"  Created issue #{issue_number}: {out['issue'].get('html_url')}")
        print("✅ PASSED")
        passed += 1
    else:
        print("❌ FAILED")
        failed += 1

    # ── Test 3: Comment on the issue ──────────────────────────
    if issue_number:
        out = call_github_tool(headers, {
            "operation": "add_comment",
            "owner": OWNER,
            "repo": REPO,
            "issue_number": issue_number,
            "body": "Round-trip comment from the client test."
        }, "Add comment")

        if out and not out.get('api_error') and (out.get('comment') or {}).get('id'):
            print(f"  Comment id: {out['comment']['id']}")
            print("✅ PASSED")
            passed += 1
        else:
            print("❌ FAILED")
            failed += 1

    # ── Test 4: Allowlist rejection over HTTP ─────────────────
    out = call_github_tool(headers, {
        "operation": "list_issues",
        "owner": "some-other-org",
        "repo": "not-allowed"
    }, "Repo outside the allowlist is denied")

    if out and 'not in the allowed' in (out.get('api_error') or ''):
        print("✅ PASSED")
        passed += 1
    else:
        print("❌ FAILED — allowlist did not reject the request")
        failed += 1

    # ── Test 5: Unknown operation is rejected with a usable error ──
    out = call_github_tool(headers, {
        "operation": "delete_issue",
        "owner": OWNER,
        "repo": REPO,
        "issue_number": 1
    }, "Unknown operation rejected", expect_status=422)

    if out and 'valid' in str(out.get('validation_error', '')).lower():
        print("✅ PASSED")
        passed += 1
    else:
        print("❌ FAILED — expected a validation error naming the valid operations")
        failed += 1

    # ── Test 6: Missing owner is rejected ─────────────────────
    out = call_github_tool(headers, {
        "operation": "get_issue",
        "repo": REPO,
        "issue_number": 1
    }, "Missing owner rejected", expect_status=422)

    if out:
        print("✅ PASSED")
        passed += 1
    else:
        print("❌ FAILED")
        failed += 1

    # ── Cleanup: close the issue this test created ────────────
    if issue_number:
        out = call_github_tool(headers, {
            "operation": "close_issue",
            "owner": OWNER,
            "repo": REPO,
            "issue_number": issue_number,
            "state_reason": "not_planned"
        }, f"Cleanup: close issue #{issue_number}")

        if out and (out.get('issue') or {}).get('state') == 'closed':
            print("✅ PASSED")
            passed += 1
        else:
            print("❌ FAILED — test issue left open")
            failed += 1

    print("\n" + "=" * 60)
    print(f"Passed: {passed}   Failed: {failed}")
    print("=" * 60)


if __name__ == '__main__':
    main()
