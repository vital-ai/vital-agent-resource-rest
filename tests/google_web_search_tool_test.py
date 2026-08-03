#!/usr/bin/env python3

import json
import sys
import os
from dotenv import load_dotenv

# Add parent directory to path to import the tool
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from vital_agent_resource_app.tools.web_search.google_web_search_tool import GoogleWebSearchTool
from vital_agent_resource_app.tools.web_search.models import WebSearchInput
from vital_agent_resource_app.tools.tool_request import ToolRequest

def test_google_web_search_tool():
    """Test the Google Web Search Tool directly with enhanced features"""
    
    print("Testing Google Web Search Tool Directly (No API)")
    print("=" * 60)
    
    # Initialize the tool with config
    api_key = os.getenv('DEV__TOOL__GOOGLE_WEB_SEARCH__API_KEY')
    
    print(f"\nAPI Key Debug:")
    print(f"  Environment variable exists: {api_key is not None}")
    print(f"  API key length: {len(api_key) if api_key else 0}")
    print(f"  API key value: {api_key}")
    
    if not api_key:
        print("❌ Error: DEV__TOOL__GOOGLE_WEB_SEARCH__API_KEY not found in environment")
        return
    
    config = {
        'tool_id': 'google_web_search_tool',
        'api_key': api_key
    }
    
    print(f"\nTool Config:")
    print(f"  {config}")
    
    tool = GoogleWebSearchTool(config)
    
    print(f"\nTool Instance Config:")
    print(f"  tool.config = {tool.config}")
    print(f"  tool.config.get('api_key') = {tool.config.get('api_key')}")
    
    # Test 1: Basic web search
    print("\n1. Testing Basic Web Search:")
    test_basic_search(tool)
    
    # Test 2: Recipe search
    print("\n2. Testing Recipe Search:")
    test_recipe_search(tool)
    
    # Test 3: Shopping search
    print("\n3. Testing Shopping Search:")
    test_shopping_search(tool)
    
    # Test 4: Local search (tbm=lcl) with place_id/ludocid extraction
    print("\n4. Testing Local Search:")
    test_local_search(tool)
    
    # Test 5: ALM RV LLC local search
    print("\n5. Testing ALM RV LLC Local Search:")
    test_alm_rv_local_search(tool)
    
    # Test 6: ALM RV LLC regular search (previously 'Unknown API error')
    print("\n6. Testing ALM RV LLC Regular Search:")
    test_alm_rv_regular_search(tool)
    
    # Test 7: ALM RV LLC ludocid deep-dive
    print("\n7. Testing ALM RV LLC ludocid deep-dive:")
    test_alm_rv_ludocid(tool)

def test_basic_search(tool):
    """Test basic web search with multiple result types"""
    try:
        # Create tool input
        tool_input = WebSearchInput(
            search_query="Python programming tutorials",
            num_results=5
        )
        
        # Create tool request
        tool_request = ToolRequest(
            tool="google_web_search_tool",
            tool_input=tool_input
        )
        
        print(f"Searching for: '{tool_input.search_query}'")
        
        # Execute the tool
        response = tool.handle_tool_request(tool_request)
        
        print(f"Success: {response.success}")
        
        if response.success and response.tool_output:
            tool_output = response.tool_output
            print(f"Query: {tool_output.query}")
            
            # Check for API errors
            if tool_output.api_error:
                print(f"\n⚠️  API Error Detected:")
                print(f"  Status Code: {tool_output.api_status_code}")
                print(f"  Error Message: {tool_output.api_error[:200]}")
                print("\n❌ Search failed due to API error")
                return
            
            print(f"Total Results: {tool_output.total_results}")
            
            # Analyze result types
            results = tool_output.results
            result_types = {}
            for res in results:
                res_type = res.result_type
                result_types[res_type] = result_types.get(res_type, 0) + 1
            
            print(f"Result Types Found: {result_types}")
            print(f"Results returned: {len(results)}")
            
            # Show first result
            if results:
                first = results[0]
                print(f"\nFirst Result:")
                print(f"  Title: {first.title}")
                print(f"  Link: {first.link}")
                print(f"  Type: {first.result_type}")
            
            print("✅ Basic search successful!")
        else:
            print(f"❌ Search failed: {response.error_message}")
            
    except Exception as e:
        print(f"❌ Basic search error: {e}")
        import traceback
        traceback.print_exc()

def test_recipe_search(tool):
    """Test recipe-focused search"""
    try:
        tool_input = WebSearchInput(
            search_query="chocolate chip cookies recipe",
            num_results=5
        )
        
        tool_request = ToolRequest(
            tool="google_web_search_tool",
            tool_input=tool_input
        )
        
        print(f"Searching for: '{tool_input.search_query}'")
        
        response = tool.handle_tool_request(tool_request)
        
        if response.success and response.tool_output:
            # Check for API errors
            if response.tool_output.api_error:
                print(f"⚠️  API Error: {response.tool_output.api_error[:200]}")
                print(f"Status Code: {response.tool_output.api_status_code}")
                return
            
            results = response.tool_output.results
            recipe_results = [r for r in results if r.result_type == 'recipe']
            
            print(f"Recipe Results Found: {len(recipe_results)}")
            for recipe in recipe_results[:2]:
                print(f"  Recipe: {recipe.title}")
                if recipe.total_time:
                    print(f"    Time: {recipe.total_time}")
                if recipe.rating:
                    print(f"    Rating: {recipe.rating}")
            
            print("✅ Recipe search successful!")
        else:
            print(f"❌ Recipe search failed: {response.error_message}")
            
    except Exception as e:
        print(f"❌ Recipe search error: {e}")
        import traceback
        traceback.print_exc()

def test_shopping_search(tool):
    """Test shopping search functionality"""
    try:
        tool_input = WebSearchInput(
            search_query="wireless headphones",
            num_results=5,
            search_type="shopping"
        )
        
        tool_request = ToolRequest(
            tool="google_web_search_tool",
            tool_input=tool_input
        )
        
        print(f"Searching for: '{tool_input.search_query}' (shopping)")
        
        response = tool.handle_tool_request(tool_request)
        
        if response.success and response.tool_output:
            # Check for API errors
            if response.tool_output.api_error:
                print(f"⚠️  API Error: {response.tool_output.api_error[:200]}")
                print(f"Status Code: {response.tool_output.api_status_code}")
                return
            
            results = response.tool_output.results
            shopping_results = [r for r in results if r.result_type == 'shopping']
            
            print(f"Shopping Results Found: {len(shopping_results)}")
            for product in shopping_results[:3]:
                print(f"  Product: {product.title}")
                if product.price:
                    print(f"    Price: {product.price}")
                if product.rating:
                    print(f"    Rating: {product.rating}")
            
            print("✅ Shopping search successful!")
        else:
            print(f"❌ Shopping search failed: {response.error_message}")
            
    except Exception as e:
        print(f"❌ Shopping search error: {e}")
        import traceback
        traceback.print_exc()

def test_alm_rv_ludocid(tool):
    """Deep-dive ALM RV LLC using ludocid from previous local search"""
    try:
        tool_input = WebSearchInput(
            search_query="ALM RV LLC",
            ludocid="4103654625110011635"
        )
        
        tool_request = ToolRequest(
            tool="google_web_search_tool",
            tool_input=tool_input
        )
        
        print(f"Searching with ludocid: {tool_input.ludocid}")
        
        response = tool.handle_tool_request(tool_request)
        
        if response.success and response.tool_output:
            if response.tool_output.api_error:
                print(f"⚠️  API Error: {response.tool_output.api_error[:200]}")
                return
            
            results = response.tool_output.results
            print(f"Results Found: {len(results)}")
            
            for r in results[:5]:
                print(f"\n  [{r.result_type}] {r.title}")
                if r.link:
                    print(f"    Link: {r.link}")
                if r.snippet:
                    snippet = r.snippet[:150] + '...' if len(r.snippet) > 150 else r.snippet
                    print(f"    Snippet: {snippet}")
                if r.rating:
                    print(f"    Rating: {r.rating} ({r.reviews} reviews)")
                if r.address:
                    print(f"    Address: {r.address}")
                if r.phone:
                    print(f"    Phone: {r.phone}")
            
            # Check knowledge graph
            if response.tool_output.knowledge_graph:
                kg = response.tool_output.knowledge_graph
                print(f"\n  Knowledge Graph:")
                print(f"    Title: {kg.title}")
                print(f"    Type: {kg.type}")
                if kg.description:
                    print(f"    Description: {kg.description[:150]}")
            
            # Check related questions
            if response.tool_output.related_questions:
                print(f"\n  Related Questions ({len(response.tool_output.related_questions)}):")
                for rq in response.tool_output.related_questions[:3]:
                    print(f"    Q: {rq.question}")
            
            print("\n✅ ALM RV LLC ludocid deep-dive successful!")
        else:
            print(f"❌ ludocid search failed: {response.error_message}")
            
    except Exception as e:
        print(f"❌ ALM RV LLC ludocid error: {e}")
        import traceback
        traceback.print_exc()


def test_alm_rv_local_search(tool):
    """Test local search for ALM RV LLC - the business from the docker logs"""
    try:
        tool_input = WebSearchInput(
            search_query="ALM RV LLC",
            num_results=5,
            search_type="local",
            location="Norco,California"
        )
        
        tool_request = ToolRequest(
            tool="google_web_search_tool",
            tool_input=tool_input
        )
        
        print(f"Searching for: '{tool_input.search_query}' (local, location={tool_input.location})")
        
        response = tool.handle_tool_request(tool_request)
        
        if response.success and response.tool_output:
            if response.tool_output.api_error:
                print(f"⚠️  API Error: {response.tool_output.api_error[:200]}")
                return
            
            results = response.tool_output.results
            local_results = [r for r in results if r.result_type == 'local']
            
            print(f"Local Results Found: {len(local_results)}")
            for place in local_results[:5]:
                print(f"\n  Business: {place.title}")
                if place.address:
                    print(f"    Address: {place.address}")
                if place.phone:
                    print(f"    Phone: {place.phone}")
                if place.rating:
                    print(f"    Rating: {place.rating} ({place.reviews} reviews)")
                if place.hours:
                    print(f"    Hours: {place.hours}")
                if place.place_id:
                    print(f"    Place ID (ludocid): {place.place_id}")
                else:
                    print(f"    Place ID: NOT FOUND")
            
            if local_results:
                print("✅ ALM RV LLC local search successful!")
            else:
                print("⚠️  No local results found for ALM RV LLC")
        else:
            print(f"❌ Local search failed: {response.error_message}")
            
    except Exception as e:
        print(f"❌ ALM RV LLC local search error: {e}")
        import traceback
        traceback.print_exc()


def test_alm_rv_regular_search(tool):
    """Test the exact query from docker logs that previously returned 'Unknown API error'"""
    try:
        tool_input = WebSearchInput(
            search_query='site:maps.google.com "ALM RV LLC" Norco reviews',
            num_results=5
        )
        
        tool_request = ToolRequest(
            tool="google_web_search_tool",
            tool_input=tool_input
        )
        
        print(f"Searching for: '{tool_input.search_query}'")
        
        response = tool.handle_tool_request(tool_request)
        
        if response.success and response.tool_output:
            if response.tool_output.api_error:
                print(f"⚠️  API Error: {response.tool_output.api_error[:200]}")
                print("❌ Still getting an API error!")
                return
            
            results = response.tool_output.results
            print(f"Results Found: {len(results)}")
            if results:
                for r in results[:3]:
                    print(f"  [{r.result_type}] {r.title} - {r.link}")
            else:
                print("  (0 results - this is expected, no longer an error)")
            
            print("✅ No 'Unknown API error' - fix confirmed!")
        else:
            print(f"❌ Search failed: {response.error_message}")
            
    except Exception as e:
        print(f"❌ ALM RV regular search error: {e}")
        import traceback
        traceback.print_exc()


def test_local_search(tool):
    """Test local search (tbm=lcl) with place_id/ludocid extraction"""
    try:
        tool_input = WebSearchInput(
            search_query="plumber",
            num_results=5,
            search_type="local",
            location="Austin,Texas"
        )
        
        tool_request = ToolRequest(
            tool="google_web_search_tool",
            tool_input=tool_input
        )
        
        print(f"Searching for: '{tool_input.search_query}' (local, location={tool_input.location})")
        
        response = tool.handle_tool_request(tool_request)
        
        if response.success and response.tool_output:
            if response.tool_output.api_error:
                print(f"⚠️  API Error: {response.tool_output.api_error[:200]}")
                return
            
            results = response.tool_output.results
            local_results = [r for r in results if r.result_type == 'local']
            
            print(f"Local Results Found: {len(local_results)}")
            
            for place in local_results[:5]:
                print(f"\n  Business: {place.title}")
                if place.address:
                    print(f"    Address: {place.address}")
                if place.phone:
                    print(f"    Phone: {place.phone}")
                if place.rating:
                    print(f"    Rating: {place.rating} ({place.reviews} reviews)")
                if place.hours:
                    print(f"    Hours: {place.hours}")
                if place.place_id:
                    print(f"    Place ID (ludocid): {place.place_id}")
                else:
                    print(f"    Place ID: NOT FOUND")
            
            # Summary
            with_place_id = [r for r in local_results if r.place_id]
            print(f"\n  Results with place_id (ludocid): {len(with_place_id)}/{len(local_results)}")
            
            if with_place_id:
                print("✅ Local search successful - ludocid extracted!")
            else:
                print("⚠️  Local search returned results but no place_id/ludocid found")
        else:
            print(f"❌ Local search failed: {response.error_message}")
            
    except Exception as e:
        print(f"❌ Local search error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_google_web_search_tool()
