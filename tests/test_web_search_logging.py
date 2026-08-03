#!/usr/bin/env python3
"""
Test Google Web Search Tool Logging
"""
import requests
import os
from dotenv import load_dotenv

load_dotenv()

def get_keycloak_token():
    """Get JWT token from Keycloak"""
    realm = os.getenv('KEYCLOAK_REALM')
    username = os.getenv('KEYCLOAK_USER')
    password = os.getenv('KEYCLOAK_PASSWORD')
    client_id = os.getenv('KEYCLOAK_CLIENT_ID')
    
    token_url = f"http://localhost:8085/realms/{realm}/protocol/openid-connect/token"
    
    data = {
        'grant_type': 'password',
        'client_id': client_id,
        'username': username,
        'password': password,
        'scope': 'openid profile email'
    }
    
    response = requests.post(token_url, data=data)
    response.raise_for_status()
    return response.json()['access_token']


def main():
    print("Testing Google Web Search Tool with Logging")
    print("=" * 60)
    
    # Get JWT token
    print("\n1. Getting JWT token...")
    access_token = get_keycloak_token()
    print("✅ Token obtained")
    
    # Test web search
    print("\n2. Executing web search (check Docker logs for detailed output)...")
    url = "http://localhost:8008/tool"
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    payload = {
        "tool": "google_web_search_tool",
        "tool_input": {
            "search_query": "Python programming tutorials",
            "num_results": 5
        }
    }
    
    response = requests.post(url, json=payload, headers=headers)
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Search successful!")
        print(f"Results returned: {len(result.get('tool_output', {}).get('results', []))}")
        print("\n📋 Check Docker logs with: docker compose logs -f app")
    else:
        print(f"❌ Request failed: {response.text}")


if __name__ == "__main__":
    main()
