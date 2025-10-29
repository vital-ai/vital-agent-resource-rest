#!/usr/bin/env python3
"""
Test script for Keycloak JWT authentication
"""
import requests
import json
import base64
import sys
import os
import uuid
from dotenv import load_dotenv
from urllib.parse import urlencode

# Load environment variables
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

def test_protected_endpoint(access_token, endpoint_url="http://localhost:8008/tool"):
    """Test a protected endpoint with JWT token"""
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    # Sample tool request
    test_data = {
        "tool": "weather_tool",
        "tool_input": {
            "latitude": 40.7128,
            "longitude": -74.0060
        }
    }
    
    try:
        response = requests.post(endpoint_url, headers=headers, json=test_data)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        return response.status_code == 200
    except requests.exceptions.RequestException as e:
        print(f"Error testing endpoint: {e}")
        return False

def test_no_auth_header():
    """Test protected endpoint with no Authorization header"""
    url = "http://localhost:8008/tool"
    
    # Create test request payload
    payload = {
        "tool": "weather_tool",
        "request_id": str(uuid.uuid4()),
        "timeout": 30,
        "tool_input": {
            "latitude": 40.7128,
            "longitude": -74.0060
        }
    }
    
    # Request with no Authorization header
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        print(f"No Authorization header - Status Code: {response.status_code}")
        
        if response.status_code == 401:
            return True
        else:
            print(f"Expected 401 for missing Authorization header but got {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        return False

def test_invalid_token():
    """Test protected endpoint with invalid JWT token"""
    url = "http://localhost:8008/tool"
    
    # Create test request payload
    payload = {
        "tool": "weather_tool",
        "request_id": str(uuid.uuid4()),
        "timeout": 30,
        "tool_input": {
            "latitude": 40.7128,
            "longitude": -74.0060
        }
    }
    
    # Test 1: Empty Authorization header
    headers_empty = {
        "Content-Type": "application/json",
        "Authorization": ""
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers_empty, timeout=30)
        print(f"Empty auth header - Status Code: {response.status_code}")
        
        if response.status_code != 401:
            print(f"Expected 401 for empty token but got {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        return False
    
    # Test 2: Invalid JWT token format
    headers_invalid = {
        "Content-Type": "application/json",
        "Authorization": "Bearer invalid.jwt.token.here"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers_invalid, timeout=30)
        print(f"Invalid token - Status Code: {response.status_code}")
        
        if response.status_code not in [401, 422]:
            print(f"Expected 401 or 422 for invalid token but got {response.status_code}")
            return False
            
        return True
            
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        return False

def decode_jwt_payload(token):
    """Decode JWT payload (without verification for inspection)"""
    import base64
    import json
    
    try:
        # Split token into parts
        parts = token.split('.')
        if len(parts) != 3:
            return None
        
        # Decode payload (add padding if needed)
        payload = parts[1]
        payload += '=' * (4 - len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception as e:
        print(f"Error decoding JWT: {e}")
        return None

def main():
    # Get credentials from environment variables
    username = os.getenv('KEYCLOAK_USER')
    password = os.getenv('KEYCLOAK_PASSWORD')
    
    if not username or not password:
        print("Error: KEYCLOAK_USER and KEYCLOAK_PASSWORD environment variables must be set")
        sys.exit(1)
    
    print(f"Testing Keycloak authentication for user: {username}")
    print("=" * 50)
    
    # Get token from Keycloak
    print("1. Getting JWT token from Keycloak...")
    token_response = get_keycloak_token(username, password)
    
    if not token_response:
        print("Failed to get token from Keycloak")
        sys.exit(1)
    
    access_token = token_response.get('access_token')
    if not access_token:
        print("No access token in response")
        sys.exit(1)
    
    print("✅ Successfully got JWT token")
    print(f"Token type: {token_response.get('token_type', 'N/A')}")
    print(f"Expires in: {token_response.get('expires_in', 'N/A')} seconds")
    
    # Decode and inspect token
    print("\n2. Inspecting JWT token payload...")
    payload = decode_jwt_payload(access_token)
    if payload:
        print(f"Subject (sub): {payload.get('sub', 'N/A')}")
        print(f"Issuer (iss): {payload.get('iss', 'N/A')}")
        print(f"Audience (aud): {payload.get('aud', 'N/A')}")
        print(f"Username: {payload.get('preferred_username', 'N/A')}")
        print(f"Email: {payload.get('email', 'N/A')}")
        print(f"Expires at: {payload.get('exp', 'N/A')}")
        print(f"Full audience field: {payload.get('aud')}")
        print(f"Audience type: {type(payload.get('aud'))}")
    
    # Test protected endpoint with valid token
    print("\n3. Testing protected endpoint with valid token...")
    success = test_protected_endpoint(access_token)
    
    if success:
        print("✅ Valid JWT authentication test successful!")
    else:
        print("❌ Valid JWT authentication test failed")
        sys.exit(1)
    
    # Test protected endpoint with no Authorization header
    print("\n4. Testing protected endpoint with no Authorization header...")
    no_header_success = test_no_auth_header()
    
    if no_header_success:
        print("✅ Missing Authorization header correctly rejected!")
    else:
        print("❌ Missing Authorization header test failed - should have been rejected")
        sys.exit(1)
    
    # Test protected endpoint with invalid token
    print("\n5. Testing protected endpoint with invalid token...")
    invalid_success = test_invalid_token()
    
    if invalid_success:
        print("✅ Invalid JWT token correctly rejected!")
    else:
        print("❌ Invalid JWT token test failed - should have been rejected")
        sys.exit(1)
    
    print("\n🎉 All JWT authentication tests passed!")
    print("- Valid tokens are accepted ✅")
    print("- Missing Authorization header is rejected ✅")
    print("- Invalid tokens are rejected ✅")

if __name__ == "__main__":
    main()
