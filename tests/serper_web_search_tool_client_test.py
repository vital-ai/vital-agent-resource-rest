#!/usr/bin/env python3
"""
Serper Web Search Tool Client Test with JWT Authentication

Tests the serper_web_search_tool via the running service at /tool endpoint.
Requires: docker compose up (service on localhost:8008), Keycloak on localhost:8085.
"""
import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()


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


def call_serper_tool(headers, payload, label=""):
    """Send a request to the /tool endpoint and print results"""
    url = "http://localhost:8008/tool"
    print(f"\n{'─' * 60}")
    print(f"TEST: {label}")
    print(f"{'─' * 60}")
    print(f"Payload: {json.dumps(payload['tool_input'], indent=2)}")

    try:
        response = requests.post(url, json=payload, headers=headers)
        print(f"Status Code: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            tool_output = result.get('tool_output', {})

            if tool_output.get('api_error'):
                print(f"\n⚠️  API Error:")
                print(f"  Status Code: {tool_output.get('api_status_code')}")
                print(f"  Error: {tool_output.get('api_error')[:200]}")
                return False

            print(f"Query: {tool_output.get('query')}")
            results = tool_output.get('results', [])
            print(f"Results: {len(results)}")
            print(f"Duration: {result.get('duration_ms')}ms")

            return tool_output
        else:
            print(f"❌ Request failed: {response.text[:300]}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    print("=" * 60)
    print("Serper Web Search Tool — Service Client Test")
    print("=" * 60)

    # Get credentials from environment
    username = os.getenv('KEYCLOAK_USER')
    password = os.getenv('KEYCLOAK_PASSWORD')

    if not username or not password:
        print("❌ Error: KEYCLOAK_USER and KEYCLOAK_PASSWORD must be set")
        return

    # Get JWT token
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

    # ── Test 1: Basic organic search ──────────────────────────
    out = call_serper_tool(headers, {
        "tool": "serper_web_search_tool",
        "tool_input": {
            "search_query": "Python programming tutorials",
            "num_results": 3
        }
    }, "Basic organic search")

    if out:
        results = out.get('results', [])
        if results:
            first = results[0]
            print(f"\n  First result:")
            print(f"    Title: {first.get('title')}")
            print(f"    Link: {first.get('link')}")
            print(f"    Type: {first.get('result_type')}")

        kg = out.get('knowledge_graph')
        if kg:
            print(f"  Knowledge Graph: {kg.get('title')} ({kg.get('type')})")

        rs = out.get('related_searches')
        if rs:
            print(f"  Related Searches: {len(rs)}")

        print("✅ PASSED")
        passed += 1
    else:
        print("❌ FAILED")
        failed += 1

    # ── Test 2: News search ───────────────────────────────────
    out = call_serper_tool(headers, {
        "tool": "serper_web_search_tool",
        "tool_input": {
            "search_query": "artificial intelligence",
            "search_type": "news",
            "num_results": 5
        }
    }, "News search")

    if out:
        for article in out.get('results', [])[:3]:
            print(f"  [{article.get('date')}] {article.get('title')}")
            print(f"    Source: {article.get('source')}")
        print("✅ PASSED")
        passed += 1
    else:
        print("❌ FAILED")
        failed += 1

    # ── Test 3: Shopping search ───────────────────────────────
    out = call_serper_tool(headers, {
        "tool": "serper_web_search_tool",
        "tool_input": {
            "search_query": "wireless headphones",
            "search_type": "shopping",
            "num_results": 5
        }
    }, "Shopping search")

    if out:
        for product in out.get('results', [])[:3]:
            print(f"  {product.get('title')}")
            print(f"    Price: {product.get('price')}  Rating: {product.get('rating')}")
        print("✅ PASSED")
        passed += 1
    else:
        print("❌ FAILED")
        failed += 1

    # ── Test 4: Places search with location ───────────────────
    out = call_serper_tool(headers, {
        "tool": "serper_web_search_tool",
        "tool_input": {
            "search_query": "pizza restaurants",
            "search_type": "places",
            "location": "New York,New York",
            "num_results": 5
        }
    }, "Places search (New York)")

    if out:
        for place in out.get('results', [])[:3]:
            print(f"  {place.get('title')}")
            print(f"    Address: {place.get('address')}")
            print(f"    Rating: {place.get('rating')} ({place.get('rating_count')} reviews)")
            print(f"    CID: {place.get('cid')}")
        print("✅ PASSED")
        passed += 1
    else:
        print("❌ FAILED")
        failed += 1

    # ── Test 5: Image search ─────────────────────────────────
    out = call_serper_tool(headers, {
        "tool": "serper_web_search_tool",
        "tool_input": {
            "search_query": "golden retriever puppies",
            "search_type": "images",
            "num_results": 3
        }
    }, "Image search")

    if out:
        for img in out.get('results', [])[:3]:
            img_url = (img.get('image_url') or 'N/A')[:80]
            print(f"  {img.get('title')}")
            print(f"    Image: {img_url}...")
        print("✅ PASSED")
        passed += 1
    else:
        print("❌ FAILED")
        failed += 1

    # ── Test 6: Knowledge graph ──────────────────────────────
    out = call_serper_tool(headers, {
        "tool": "serper_web_search_tool",
        "tool_input": {
            "search_query": "Albert Einstein",
            "num_results": 3
        }
    }, "Knowledge graph extraction")

    if out:
        kg = out.get('knowledge_graph')
        if kg:
            print(f"  Title: {kg.get('title')}")
            print(f"  Type: {kg.get('type')}")
            desc = kg.get('description', '')
            if desc:
                print(f"  Description: {desc[:120]}...")
            attrs = kg.get('attributes')
            if attrs:
                print(f"  Attributes: {list(attrs.keys())[:8]}")
            print("✅ PASSED")
            passed += 1
        else:
            print("⚠️  No knowledge graph returned")
            print("❌ FAILED")
            failed += 1

        paa = out.get('people_also_ask')
        if paa:
            print(f"\n  People Also Ask ({len(paa)}):")
            for q in paa[:3]:
                print(f"    Q: {q.get('question')}")
    else:
        print("❌ FAILED")
        failed += 1

    # ── Test 7: Time-filtered news ───────────────────────────
    out = call_serper_tool(headers, {
        "tool": "serper_web_search_tool",
        "tool_input": {
            "search_query": "technology news",
            "search_type": "news",
            "time_period": "day",
            "num_results": 5
        }
    }, "Time-filtered news (past day)")

    if out:
        for article in out.get('results', [])[:3]:
            print(f"  [{article.get('date')}] {article.get('title')}")
        print("✅ PASSED")
        passed += 1
    else:
        print("❌ FAILED")
        failed += 1

    # ── Summary ──────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"RESULTS: {passed} passed, {failed} failed, {passed + failed} total")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
