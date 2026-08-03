#!/usr/bin/env python3
"""
Google Web Search Tool Client Test with JWT Authentication
"""
import requests
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


def main():
    print("=" * 60)
    print("Google Web Search Tool Client Test")
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

    # Test web search via API endpoint
    print("\n2. Executing web search via API...")
    url = "http://localhost:8008/tool"

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }

    payload = {
        "tool": "google_web_search_tool",
        "tool_input": {
            "search_query": "Python tutorials",
            "num_results": 3
        }
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        print(f"\nStatus Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Search successful!")
            
            tool_output = result.get('tool_output', {})
            
            # Check for API errors in the response
            if tool_output.get('api_error'):
                print(f"\n⚠️  API Error in Response:")
                print(f"  Status Code: {tool_output.get('api_status_code')}")
                print(f"  Error: {tool_output.get('api_error')[:200]}")
            else:
                print(f"\nQuery: {tool_output.get('query')}")
                print(f"Total Results: {tool_output.get('total_results')}")
                results = tool_output.get('results', [])
                print(f"Results returned: {len(results)}")
                
                if results:
                    print(f"\nFirst Result:")
                    print(f"  Title: {results[0].get('title')}")
                    print(f"  Link: {results[0].get('link')}")
        else:
            print(f"❌ Request failed: {response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()



