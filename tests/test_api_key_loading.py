#!/usr/bin/env python3

import sys
import os
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from vital_agent_resource_app.tools.web_search.google_web_search_tool import GoogleWebSearchTool

# Test 1: Check environment variable
print("=" * 60)
print("Testing API Key Loading")
print("=" * 60)

env_key = os.getenv('DEV__TOOL__GOOGLE_WEB_SEARCH__API_KEY')
print(f"\n1. Environment Variable:")
print(f"   DEV__TOOL__GOOGLE_WEB_SEARCH__API_KEY = {env_key}")
print(f"   Length: {len(env_key) if env_key else 0}")

# Test 2: Check tool config
print(f"\n2. Tool Configuration:")
config = {
    'tool_id': 'google_web_search_tool',
    'api_key': env_key
}
print(f"   Config: {config}")

# Test 3: Initialize tool and check
tool = GoogleWebSearchTool(config)
print(f"\n3. Tool Instance:")
print(f"   tool.config = {tool.config}")
print(f"   tool.config.get('api_key') = {tool.config.get('api_key')}")

# Test 4: Try to access the key the way the tool does
api_key = tool.config.get('api_key')
print(f"\n4. API Key Retrieved:")
print(f"   Value: {api_key}")
print(f"   Length: {len(api_key) if api_key else 0}")
print(f"   First 20 chars: {api_key[:20] if api_key else 'None'}")
print(f"   Last 20 chars: {api_key[-20:] if api_key else 'None'}")
