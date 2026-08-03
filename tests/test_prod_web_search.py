#!/usr/bin/env python3
"""
Production Web Search Tool Test

Tests the google_web_search_tool against the production tool server
using Keycloak JWT authentication.

Usage:
    python tests/test_prod_web_search.py                # default web search test
    python tests/test_prod_web_search.py --local        # test against local server
    python tests/test_prod_web_search.py --all          # run all search types
"""
import argparse
import base64
import json
import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()


def get_env(key, required=True):
    val = os.getenv(key)
    if required and not val:
        print(f"ERROR: {key} not set in .env")
        sys.exit(1)
    return val


def get_keycloak_token(base_url, realm, client_id, client_secret, username, password):
    """Get JWT access token from Keycloak via password grant."""
    token_url = f"{base_url}/realms/{realm}/protocol/openid-connect/token"

    data = {
        "grant_type": "password",
        "client_id": client_id,
        "client_secret": client_secret,
        "username": username,
        "password": password,
        "scope": "openid",
    }

    resp = requests.post(token_url, data=data, timeout=15)
    resp.raise_for_status()
    token_data = resp.json()

    access_token = token_data.get("access_token")
    if not access_token:
        raise RuntimeError(f"No access_token in response: {token_data}")

    return access_token, token_data.get("expires_in", 0)


def decode_jwt_claims(token):
    """Decode JWT payload without verification (for inspection only)."""
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    payload = parts[1] + "=" * (4 - len(parts[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def call_tool(server_url, token, tool_name, tool_input):
    """Call a tool on the tool server and return the parsed response."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "tool": tool_name,
        "tool_input": tool_input,
    }

    start = time.time()
    resp = requests.post(f"{server_url}/tool", json=payload, headers=headers, timeout=30)
    elapsed_ms = int((time.time() - start) * 1000)

    return resp.status_code, resp.json(), elapsed_ms


def print_search_results(data, max_results=5):
    """Pretty-print search results."""
    tool_output = data.get("tool_output", {})

    if tool_output.get("api_error"):
        print(f"  API Error: {tool_output.get('api_error')[:200]}")
        return

    query = tool_output.get("query", "")
    results = tool_output.get("results", [])
    total = tool_output.get("total_results", 0)
    kg = tool_output.get("knowledge_graph")

    print(f"  Query: {query}")
    print(f"  Total results: {total} | Returned: {len(results)}")

    if kg:
        print(f"  Knowledge Graph: {kg.get('title', 'N/A')} ({kg.get('type', 'N/A')})")

    for i, r in enumerate(results[:max_results]):
        rtype = r.get("result_type", "organic")
        title = r.get("title", "N/A")[:80]
        link = r.get("link", "N/A")[:80]
        snippet = (r.get("snippet") or "")[:120]
        extras = []
        if r.get("rating"):
            extras.append(f"rating={r['rating']}")
        if r.get("price"):
            extras.append(f"price={r['price']}")
        if r.get("address"):
            extras.append(f"addr={r['address'][:40]}")
        extra_str = f" [{', '.join(extras)}]" if extras else ""
        print(f"  [{i+1}] ({rtype}) {title}{extra_str}")
        print(f"      {link}")
        if snippet:
            print(f"      {snippet}")


def run_test(server_url, token, label, tool_input):
    """Run a single search test."""
    print(f"\n{'='*60}")
    print(f"TEST: {label}")
    print(f"{'='*60}")
    print(f"  Input: {json.dumps(tool_input, indent=None)}")

    status, data, elapsed = call_tool(server_url, token, "google_web_search_tool", tool_input)

    if status == 200 and data.get("success"):
        print(f"  Status: {status} OK ({elapsed}ms)")
        print_search_results(data)
        return True
    else:
        print(f"  Status: {status} FAILED ({elapsed}ms)")
        print(f"  Response: {json.dumps(data, indent=2)[:500]}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test prod web search tool")
    parser.add_argument("--local", action="store_true", help="Test against local server")
    parser.add_argument("--all", action="store_true", help="Run all search type tests")
    parser.add_argument("--query", type=str, default=None, help="Custom search query")
    args = parser.parse_args()

    # Load credentials based on target
    if args.local:
        base_url = os.getenv("KEYCLOAK_BASE_URL", "http://localhost:8085")
        realm = get_env("KEYCLOAK_REALM")
        client_id = get_env("KEYCLOAK_CLIENT_ID")
        client_secret = get_env("KEYCLOAK_CLIENT_SECRET")
        username = get_env("KEYCLOAK_USER")
        password = get_env("KEYCLOAK_PASSWORD")
        server_url = os.getenv("TOOL_SERVER_URL", "http://localhost:8008")
        env_label = "LOCAL"
    else:
        base_url = get_env("PROD_KEYCLOAK_BASE_URL")
        realm = get_env("PROD_KEYCLOAK_REALM")
        client_id = get_env("PROD_KEYCLOAK_CLIENT_ID")
        client_secret = get_env("PROD_KEYCLOAK_CLIENT_SECRET")
        username = get_env("PROD_KEYCLOAK_USER")
        password = get_env("PROD_KEYCLOAK_PASSWORD")
        server_url = get_env("PROD_TOOL_SERVER_URL")
        env_label = "PRODUCTION"

    print(f"Target: {env_label}")
    print(f"Server: {server_url}")
    print(f"Keycloak: {base_url}/realms/{realm}")

    # Step 1: Health check
    print(f"\n--- Health Check ---")
    try:
        resp = requests.get(f"{server_url}/health", timeout=5)
        print(f"  {resp.status_code}: {resp.json()}")
    except Exception as e:
        print(f"  FAILED: {e}")
        sys.exit(1)

    # Step 2: Get JWT
    print(f"\n--- Keycloak Authentication ---")
    try:
        token, expires_in = get_keycloak_token(
            base_url, realm, client_id, client_secret, username, password
        )
        claims = decode_jwt_claims(token)
        print(f"  Token obtained (expires in {expires_in}s)")
        print(f"  Subject: {claims.get('sub')}")
        print(f"  Username: {claims.get('preferred_username')}")
        print(f"  Issuer: {claims.get('iss')}")
        print(f"  Audience: {claims.get('aud')}")
    except Exception as e:
        print(f"  FAILED: {e}")
        sys.exit(1)

    # Step 3: Run search tests
    passed = 0
    failed = 0

    # Basic web search
    query = args.query or "best pizza in Manhattan NYC"
    if run_test(server_url, token, f"Web Search: {query}", {
        "search_query": query,
        "search_type": "search",
        "num_results": 5,
    }):
        passed += 1
    else:
        failed += 1

    if args.all:
        # Local search
        if run_test(server_url, token, "Local Search: pizza near Wall Street NYC", {
            "search_query": "pizza near Wall Street NYC",
            "search_type": "local",
            "num_results": 5,
        }):
            passed += 1
        else:
            failed += 1

        # News search
        if run_test(server_url, token, "News Search: artificial intelligence 2026", {
            "search_query": "artificial intelligence 2026",
            "search_type": "news",
            "num_results": 5,
        }):
            passed += 1
        else:
            failed += 1

        # Shopping search
        if run_test(server_url, token, "Shopping Search: wireless headphones", {
            "search_query": "wireless headphones",
            "search_type": "shopping",
            "num_results": 5,
        }):
            passed += 1
        else:
            failed += 1

        # Knowledge graph entity
        if run_test(server_url, token, "Knowledge Graph: Albert Einstein", {
            "search_query": "Albert Einstein",
            "search_type": "search",
            "num_results": 3,
        }):
            passed += 1
        else:
            failed += 1

    # Summary
    total = passed + failed
    print(f"\n{'='*60}")
    print(f"RESULTS: {passed}/{total} passed", end="")
    if failed:
        print(f" ({failed} failed)")
    else:
        print(" - ALL PASSED")
    print(f"{'='*60}")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
