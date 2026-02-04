#!/usr/bin/env python3
"""
Google Address Validation Tool Test with JWT Authentication
"""
import requests
import sys
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_keycloak_token(username=None, password=None, client_id=None, client_secret=None):
    """Get JWT token from Keycloak"""
    realm = os.getenv('KEYCLOAK_REALM', None)
    username = username or os.getenv('KEYCLOAK_USER', None)
    password = password or os.getenv('KEYCLOAK_PASSWORD', None)
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
    print("Google Address Validation Tool Test with JWT Authentication")
    print("=" * 60)
    
    # Get JWT token
    print("\n1. Getting JWT token from Keycloak...")
    token_response = get_keycloak_token()
    
    if not token_response:
        print("❌ Failed to get JWT token")
        return
    
    access_token = token_response.get('access_token')
    print(f"✅ Successfully got JWT token")
    print(f"Token type: {token_response.get('token_type')}")
    print(f"Expires in: {token_response.get('expires_in')} seconds")
    
    # Test Google Address Validation tool
    print("\n2. Testing Google Address Validation Tool...")
    url = "http://localhost:8008/tool"
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    payload = {
        "tool": "google_address_validation_tool",
        "tool_input": {
            "address": "475 st marks broklyn 7a"
        }
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ Google Address Validation Tool test successful!")
            print("\nResponse JSON:")
            import json
            print(json.dumps(response.json(), indent=2))
        else:
            print(f"❌ Request failed with status {response.status_code}")
            print("Response:")
            print(response.text)
    
    except requests.exceptions.RequestException as e:
        print(f"❌ Error testing endpoint: {e}")


if __name__ == "__main__":
    main()
