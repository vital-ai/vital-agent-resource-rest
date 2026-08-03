#!/usr/bin/env python3

import asyncio
import json
import sys
import os
from dotenv import load_dotenv

# Add parent directory to path to import the tool
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from vital_agent_resource_app.tools.serper_web_search.serper_web_search_tool import SerperWebSearchTool
from vital_agent_resource_app.tools.serper_web_search.models import SerperWebSearchInput
from vital_agent_resource_app.tools.tool_request import ToolRequest


def test_serper_web_search_tool():
    """Test the Serper Web Search Tool directly"""

    print("Testing Serper Web Search Tool")
    print("=" * 60)

    # Initialize the tool with config
    api_key = os.getenv('DEV__TOOL__SERPER_WEB_SEARCH__API_KEY')

    print(f"\nAPI Key Debug:")
    print(f"  Environment variable exists: {api_key is not None}")
    print(f"  API key length: {len(api_key) if api_key else 0}")
    print(f"  API key (last 4): ...{api_key[-4:] if api_key else 'None'}")

    if not api_key:
        print("Error: DEV__TOOL__SERPER_WEB_SEARCH__API_KEY not found in environment")
        return

    config = {
        'tool_id': 'serper_web_search_tool',
        'api_key': api_key
    }

    tool = SerperWebSearchTool(config)

    print(f"\nTool Instance Config:")
    print(f"  tool.config = {list(tool.config.keys())}")

    # Test 1: Basic web search
    print("\n" + "=" * 60)
    print("1. Testing Basic Web Search:")
    asyncio.run(test_basic_search(tool))

    # Test 2: News search
    print("\n" + "=" * 60)
    print("2. Testing News Search:")
    asyncio.run(test_news_search(tool))

    # Test 3: Shopping search
    print("\n" + "=" * 60)
    print("3. Testing Shopping Search:")
    asyncio.run(test_shopping_search(tool))

    # Test 4: Places search
    print("\n" + "=" * 60)
    print("4. Testing Places Search:")
    asyncio.run(test_places_search(tool))

    # Test 5: Image search
    print("\n" + "=" * 60)
    print("5. Testing Image Search:")
    asyncio.run(test_image_search(tool))

    # Test 6: Knowledge graph extraction
    print("\n" + "=" * 60)
    print("6. Testing Knowledge Graph:")
    asyncio.run(test_knowledge_graph(tool))

    # Test 7: Location targeting
    print("\n" + "=" * 60)
    print("7. Testing Location Targeting:")
    asyncio.run(test_location_targeting(tool))

    # Test 8: Time filtering
    print("\n" + "=" * 60)
    print("8. Testing Time Filtering:")
    asyncio.run(test_time_filtering(tool))

    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETE")
    print("=" * 60)


async def test_basic_search(tool):
    """Test basic web search with organic results"""
    try:
        tool_input = SerperWebSearchInput(
            search_query="Python programming tutorials",
            num_results=5
        )

        tool_request = ToolRequest(
            tool="serper_web_search_tool",
            tool_input=tool_input
        )

        print(f"Searching for: '{tool_input.search_query}'")

        response = await tool.handle_tool_request(tool_request)

        print(f"Success: {response.success}")

        if response.success and response.tool_output:
            out = response.tool_output
            # Handle both dict and Pydantic model
            if isinstance(out, dict):
                query = out.get('query')
                api_error = out.get('api_error')
                results = out.get('results', [])
            else:
                query = out.query
                api_error = out.api_error
                results = out.results or []

            print(f"Query: {query}")

            if api_error:
                print(f"  API Error: {str(api_error)[:200]}")
                return

            print(f"Results returned: {len(results)}")

            result_types = {}
            for res in results:
                rt = res.get('result_type', 'unknown') if isinstance(res, dict) else getattr(res, 'result_type', 'unknown')
                result_types[rt] = result_types.get(rt, 0) + 1
            print(f"Result Types: {result_types}")

            if results:
                first = results[0]
                title = first.get('title') if isinstance(first, dict) else first.title
                link = first.get('link') if isinstance(first, dict) else first.link
                rtype = first.get('result_type') if isinstance(first, dict) else first.result_type
                snippet = first.get('snippet') if isinstance(first, dict) else first.snippet
                print(f"\nFirst Result:")
                print(f"  Title: {title}")
                print(f"  Link: {link}")
                print(f"  Type: {rtype}")
                if snippet:
                    s = snippet[:100] + '...' if len(snippet) > 100 else snippet
                    print(f"  Snippet: {s}")

            # Check for knowledge graph
            kg = out.get('knowledge_graph') if isinstance(out, dict) else out.knowledge_graph
            if kg:
                kg_title = kg.get('title') if isinstance(kg, dict) else kg.title
                kg_type = kg.get('type') if isinstance(kg, dict) else kg.type
                print(f"\nKnowledge Graph: {kg_title} ({kg_type})")

            # Check for people also ask
            paa = out.get('people_also_ask') if isinstance(out, dict) else out.people_also_ask
            if paa:
                print(f"\nPeople Also Ask ({len(paa)}):")
                for q in paa[:3]:
                    qq = q.get('question') if isinstance(q, dict) else q.question
                    print(f"  Q: {qq}")

            # Check for related searches
            rs = out.get('related_searches') if isinstance(out, dict) else out.related_searches
            if rs:
                print(f"\nRelated Searches ({len(rs)}):")
                for s in rs[:3]:
                    sq = s.get('query') if isinstance(s, dict) else s.query
                    print(f"  - {sq}")

            print("\nBasic search successful!")
        else:
            print(f"Search failed: {response.error_message}")

    except Exception as e:
        print(f"Basic search error: {e}")
        import traceback
        traceback.print_exc()


async def test_news_search(tool):
    """Test news search"""
    try:
        tool_input = SerperWebSearchInput(
            search_query="artificial intelligence",
            search_type="news",
            num_results=5
        )

        tool_request = ToolRequest(
            tool="serper_web_search_tool",
            tool_input=tool_input
        )

        print(f"Searching for: '{tool_input.search_query}' (news)")

        response = await tool.handle_tool_request(tool_request)

        if response.success and response.tool_output:
            out = response.tool_output
            api_error = out.get('api_error') if isinstance(out, dict) else out.api_error
            if api_error:
                print(f"  API Error: {str(api_error)[:200]}")
                return

            results = out.get('results', []) if isinstance(out, dict) else (out.results or [])
            print(f"News Results Found: {len(results)}")

            for article in results[:3]:
                if isinstance(article, dict):
                    print(f"\n  Title: {article.get('title')}")
                    print(f"    Source: {article.get('source')}")
                    print(f"    Date: {article.get('date')}")
                    print(f"    Link: {article.get('link')}")
                else:
                    print(f"\n  Title: {article.title}")
                    print(f"    Source: {article.source}")
                    print(f"    Date: {article.date}")
                    print(f"    Link: {article.link}")

            print("\nNews search successful!")
        else:
            print(f"News search failed: {response.error_message}")

    except Exception as e:
        print(f"News search error: {e}")
        import traceback
        traceback.print_exc()


async def test_shopping_search(tool):
    """Test shopping search"""
    try:
        tool_input = SerperWebSearchInput(
            search_query="wireless headphones",
            search_type="shopping",
            num_results=5
        )

        tool_request = ToolRequest(
            tool="serper_web_search_tool",
            tool_input=tool_input
        )

        print(f"Searching for: '{tool_input.search_query}' (shopping)")

        response = await tool.handle_tool_request(tool_request)

        if response.success and response.tool_output:
            out = response.tool_output
            api_error = out.get('api_error') if isinstance(out, dict) else out.api_error
            if api_error:
                print(f"  API Error: {str(api_error)[:200]}")
                return

            results = out.get('results', []) if isinstance(out, dict) else (out.results or [])
            print(f"Shopping Results Found: {len(results)}")

            for product in results[:3]:
                if isinstance(product, dict):
                    print(f"\n  Product: {product.get('title')}")
                    print(f"    Price: {product.get('price')}")
                    print(f"    Rating: {product.get('rating')}")
                    print(f"    Link: {product.get('link')}")
                    print(f"    Source: {product.get('source')}")
                else:
                    print(f"\n  Product: {product.title}")
                    print(f"    Price: {product.price}")
                    print(f"    Rating: {product.rating}")
                    print(f"    Link: {product.link}")
                    print(f"    Source: {product.source}")

            print("\nShopping search successful!")
        else:
            print(f"Shopping search failed: {response.error_message}")

    except Exception as e:
        print(f"Shopping search error: {e}")
        import traceback
        traceback.print_exc()


async def test_places_search(tool):
    """Test places search with structured business data"""
    try:
        tool_input = SerperWebSearchInput(
            search_query="pizza restaurants",
            search_type="places",
            location="New York,New York",
            num_results=5
        )

        tool_request = ToolRequest(
            tool="serper_web_search_tool",
            tool_input=tool_input
        )

        print(f"Searching for: '{tool_input.search_query}' (places, location={tool_input.location})")

        response = await tool.handle_tool_request(tool_request)

        if response.success and response.tool_output:
            out = response.tool_output
            api_error = out.get('api_error') if isinstance(out, dict) else out.api_error
            if api_error:
                print(f"  API Error: {str(api_error)[:200]}")
                return

            results = out.get('results', []) if isinstance(out, dict) else (out.results or [])
            print(f"Place Results Found: {len(results)}")

            def _g(obj, key):
                return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)

            for place in results[:5]:
                print(f"\n  Business: {_g(place, 'title')}")
                print(f"    Address: {_g(place, 'address')}")
                print(f"    Phone: {_g(place, 'phone_number')}")
                print(f"    Rating: {_g(place, 'rating')} ({_g(place, 'rating_count')} reviews)")
                print(f"    Category: {_g(place, 'category')}")
                print(f"    Website: {_g(place, 'website')}")
                print(f"    CID: {_g(place, 'cid')}")
                print(f"    Lat/Lng: {_g(place, 'latitude')}, {_g(place, 'longitude')}")
                print(f"    Price Level: {_g(place, 'price_level')}")

            # Summary
            with_cid = [r for r in results if _g(r, 'cid')]
            with_website = [r for r in results if _g(r, 'website')]
            with_phone = [r for r in results if _g(r, 'phone_number')]
            print(f"\n  Results with CID: {len(with_cid)}/{len(results)}")
            print(f"  Results with website: {len(with_website)}/{len(results)}")
            print(f"  Results with phone: {len(with_phone)}/{len(results)}")

            print("\nPlaces search successful!")
        else:
            print(f"Places search failed: {response.error_message}")

    except Exception as e:
        print(f"Places search error: {e}")
        import traceback
        traceback.print_exc()


async def test_image_search(tool):
    """Test image search"""
    try:
        tool_input = SerperWebSearchInput(
            search_query="golden retriever puppies",
            search_type="images",
            num_results=5
        )

        tool_request = ToolRequest(
            tool="serper_web_search_tool",
            tool_input=tool_input
        )

        print(f"Searching for: '{tool_input.search_query}' (images)")

        response = await tool.handle_tool_request(tool_request)

        if response.success and response.tool_output:
            out = response.tool_output
            api_error = out.get('api_error') if isinstance(out, dict) else out.api_error
            if api_error:
                print(f"  API Error: {str(api_error)[:200]}")
                return

            results = out.get('results', []) if isinstance(out, dict) else (out.results or [])
            print(f"Image Results Found: {len(results)}")

            def _g(obj, key, default=None):
                return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)

            for img in results[:3]:
                img_url = _g(img, 'image_url', 'N/A') or 'N/A'
                print(f"\n  Title: {_g(img, 'title')}")
                print(f"    Image URL: {img_url[:80]}...")
                print(f"    Link: {_g(img, 'link')}")
                print(f"    Source: {_g(img, 'source')}")

            print("\nImage search successful!")
        else:
            print(f"Image search failed: {response.error_message}")

    except Exception as e:
        print(f"Image search error: {e}")
        import traceback
        traceback.print_exc()


async def test_knowledge_graph(tool):
    """Test knowledge graph extraction for a well-known entity"""
    try:
        tool_input = SerperWebSearchInput(
            search_query="Albert Einstein",
            num_results=5
        )

        tool_request = ToolRequest(
            tool="serper_web_search_tool",
            tool_input=tool_input
        )

        print(f"Searching for: '{tool_input.search_query}'")

        response = await tool.handle_tool_request(tool_request)

        if response.success and response.tool_output:
            out = response.tool_output
            api_error = out.get('api_error') if isinstance(out, dict) else out.api_error
            if api_error:
                print(f"  API Error: {str(api_error)[:200]}")
                return

            def _g(obj, key, default=None):
                return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)

            kg = _g(out, 'knowledge_graph')
            if kg:
                print(f"\nKnowledge Graph Found:")
                print(f"  Title: {_g(kg, 'title')}")
                print(f"  Type: {_g(kg, 'type')}")
                desc = _g(kg, 'description')
                if desc:
                    d = desc[:150] + '...' if len(desc) > 150 else desc
                    print(f"  Description: {d}")
                if _g(kg, 'website'):
                    print(f"  Website: {_g(kg, 'website')}")
                attrs = _g(kg, 'attributes')
                if attrs:
                    print(f"  Attributes: {list(attrs.keys())[:10]}")
                print("\nKnowledge graph extraction successful!")
            else:
                print("  No knowledge graph returned (unexpected for Albert Einstein)")

            paa = _g(out, 'people_also_ask')
            if paa:
                print(f"\nPeople Also Ask ({len(paa)}):")
                for q in paa[:3]:
                    qq = q.get('question') if isinstance(q, dict) else q.question
                    print(f"  Q: {qq}")
        else:
            print(f"Search failed: {response.error_message}")

    except Exception as e:
        print(f"Knowledge graph error: {e}")
        import traceback
        traceback.print_exc()


async def test_location_targeting(tool):
    """Test location-targeted search"""
    try:
        tool_input = SerperWebSearchInput(
            search_query="best tacos near me",
            search_type="places",
            location="Austin,Texas",
            num_results=5
        )

        tool_request = ToolRequest(
            tool="serper_web_search_tool",
            tool_input=tool_input
        )

        print(f"Searching for: '{tool_input.search_query}' (places, location={tool_input.location})")

        response = await tool.handle_tool_request(tool_request)

        if response.success and response.tool_output:
            out = response.tool_output
            api_error = out.get('api_error') if isinstance(out, dict) else out.api_error
            if api_error:
                print(f"  API Error: {str(api_error)[:200]}")
                return

            def _g(obj, key, default=None):
                return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)

            results = out.get('results', []) if isinstance(out, dict) else (out.results or [])
            print(f"Results Found: {len(results)}")

            for place in results[:3]:
                print(f"\n  Business: {_g(place, 'title')}")
                print(f"    Address: {_g(place, 'address')}")
                print(f"    Rating: {_g(place, 'rating')}")

            # Check that results are in Austin area
            texas_results = [r for r in results if _g(r, 'address') and 'TX' in _g(r, 'address', '')]
            print(f"\n  Results in Texas: {len(texas_results)}/{len(results)}")

            print("\nLocation targeting successful!")
        else:
            print(f"Location search failed: {response.error_message}")

    except Exception as e:
        print(f"Location targeting error: {e}")
        import traceback
        traceback.print_exc()


async def test_time_filtering(tool):
    """Test time-filtered search"""
    try:
        tool_input = SerperWebSearchInput(
            search_query="technology news",
            search_type="news",
            time_period="day",
            num_results=5
        )

        tool_request = ToolRequest(
            tool="serper_web_search_tool",
            tool_input=tool_input
        )

        print(f"Searching for: '{tool_input.search_query}' (news, past day)")

        response = await tool.handle_tool_request(tool_request)

        if response.success and response.tool_output:
            out = response.tool_output
            api_error = out.get('api_error') if isinstance(out, dict) else out.api_error
            if api_error:
                print(f"  API Error: {str(api_error)[:200]}")
                return

            def _g(obj, key, default=None):
                return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)

            results = out.get('results', []) if isinstance(out, dict) else (out.results or [])
            print(f"Recent News Found: {len(results)}")

            for article in results[:3]:
                print(f"\n  Title: {_g(article, 'title')}")
                print(f"    Date: {_g(article, 'date')}")
                print(f"    Source: {_g(article, 'source')}")

            print("\nTime filtering successful!")
        else:
            print(f"Time filter search failed: {response.error_message}")

    except Exception as e:
        print(f"Time filtering error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_serper_web_search_tool()
