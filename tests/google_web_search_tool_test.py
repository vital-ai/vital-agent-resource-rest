#!/usr/bin/env python3

import json
import requests
import sys
import os

def test_google_web_search_tool():
    """Test the Google Web Search Tool with enhanced features"""
    
    # Test URL - adjust if your server runs on a different port
    base_url = "http://localhost:8008"
    
    print("Testing Google Web Search Tool with Enhanced Features...")
    print("=" * 60)
    
    # Test 1: Basic web search with multiple result types
    print("\n1. Testing Enhanced Web Search (Multiple Result Types):")
    test_enhanced_search(base_url)
    
    # Test 2: Recipe search
    print("\n2. Testing Recipe Search:")
    test_recipe_search(base_url)
    
    # Test 3: Shopping search
    print("\n3. Testing Shopping Search:")
    test_shopping_search(base_url)
    
    # Test 4: Local search
    print("\n4. Testing Local Search:")
    test_local_search(base_url)
    
    # Test 5: Knowledge graph search
    print("\n5. Testing Knowledge Graph Search:")
    test_knowledge_graph_search(base_url)

def test_enhanced_search(base_url):
    """Test enhanced web search with multiple result types"""
    payload = {
        "tool": "google_web_search_tool",
        "tool_input": {
            "search_query": "apple pie recipe",
            "num_results": 10
        }
    }
    
    try:
        response = requests.post(f"{base_url}/tool", json=payload)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Enhanced search successful!")
            print(f"Full Response: {result}")
            
            # Handle different response structures
            if 'tool_output' in result and result['tool_output'] is not None:
                tool_output = result['tool_output']
                print(f"Query: {tool_output.get('query', 'N/A')}")
                print(f"Total Results: {tool_output.get('total_results', 'N/A')}")
                
                # Analyze result types
                results = tool_output.get('results', [])
                result_types = {}
                for res in results:
                    res_type = res.get('result_type', 'unknown')
                    result_types[res_type] = result_types.get(res_type, 0) + 1
                
                print(f"Result Types Found: {result_types}")
                
                # Check for knowledge graph
                kg = tool_output.get('knowledge_graph')
                if kg:
                    print(f"Knowledge Graph: {kg.get('title', 'N/A')} - {kg.get('type', 'N/A')}")
                
                # Check for related questions
                rq = tool_output.get('related_questions', [])
                if rq:
                    print(f"Related Questions: {len(rq)} found")
                    print(f"  First Question: {rq[0].get('question', 'N/A')}")
            else:
                print("❌ No tool_output in response or tool_output is None")
                if 'error_message' in result:
                    print(f"Error: {result['error_message']}")
                
        else:
            print(f"❌ Enhanced search failed with status {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Enhanced search error: {e}")

def test_recipe_search(base_url):
    """Test recipe-focused search"""
    payload = {
        "tool": "google_web_search_tool",
        "tool_input": {
            "search_query": "chocolate chip cookies recipe",
            "num_results": 5
        }
    }
    
    try:
        response = requests.post(f"{base_url}/tool", json=payload)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Recipe search successful!")
            
            results = result.get('tool_output', {}).get('results', [])
            recipe_results = [r for r in results if r.get('result_type') == 'recipe']
            
            print(f"Recipe Results Found: {len(recipe_results)}")
            for recipe in recipe_results[:2]:
                print(f"  Recipe: {recipe.get('title', 'N/A')}")
                if recipe.get('total_time'):
                    print(f"    Time: {recipe.get('total_time')}")
                if recipe.get('rating'):
                    print(f"    Rating: {recipe.get('rating')}")
                    
        else:
            print(f"❌ Recipe search failed with status {response.status_code}")
            
    except Exception as e:
        print(f"❌ Recipe search error: {e}")

def test_shopping_search(base_url):
    """Test shopping search functionality"""
    payload = {
        "tool": "google_web_search_tool",
        "tool_input": {
            "search_query": "wireless headphones",
            "num_results": 5,
            "search_type": "shopping"
        }
    }
    
    try:
        response = requests.post(f"{base_url}/tool", json=payload)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Shopping search successful!")
            
            results = result.get('tool_output', {}).get('results', [])
            shopping_results = [r for r in results if r.get('result_type') == 'shopping']
            
            print(f"Shopping Results Found: {len(shopping_results)}")
            for product in shopping_results[:3]:
                print(f"  Product: {product.get('title', 'N/A')}")
                if product.get('price'):
                    print(f"    Price: {product.get('price')}")
                if product.get('rating'):
                    print(f"    Rating: {product.get('rating')}")
                    
        else:
            print(f"❌ Shopping search failed with status {response.status_code}")
            
    except Exception as e:
        print(f"❌ Shopping search error: {e}")

def test_local_search(base_url):
    """Test local search functionality"""
    payload = {
        "tool": "google_web_search_tool",
        "tool_input": {
            "search_query": "coffee shops near me",
            "num_results": 5,
            "location": "Austin, Texas"
        }
    }
    
    try:
        response = requests.post(f"{base_url}/tool", json=payload)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Local search successful!")
            
            results = result.get('tool_output', {}).get('results', [])
            local_results = [r for r in results if r.get('result_type') == 'local']
            
            print(f"Local Results Found: {len(local_results)}")
            for place in local_results[:2]:
                print(f"  Place: {place.get('title', 'N/A')}")
                if place.get('address'):
                    print(f"    Address: {place.get('address')}")
                if place.get('rating'):
                    print(f"    Rating: {place.get('rating')}")
                    
        else:
            print(f"❌ Local search failed with status {response.status_code}")
            
    except Exception as e:
        print(f"❌ Local search error: {e}")

def test_knowledge_graph_search(base_url):
    """Test search that should return knowledge graph"""
    payload = {
        "tool": "google_web_search_tool",
        "tool_input": {
            "search_query": "Albert Einstein",
            "num_results": 5
        }
    }
    
    try:
        response = requests.post(f"{base_url}/tool", json=payload)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Knowledge graph search successful!")
            
            tool_output = result.get('tool_output', {})
            kg = tool_output.get('knowledge_graph')
            
            if kg:
                print("Knowledge Graph Found:")
                print(f"  Title: {kg.get('title', 'N/A')}")
                print(f"  Type: {kg.get('type', 'N/A')}")
                print(f"  Description: {kg.get('description', 'N/A')[:100]}...")
            else:
                print("No Knowledge Graph found in results")
                
            # Check related questions
            rq = tool_output.get('related_questions', [])
            if rq:
                print(f"Related Questions Found: {len(rq)}")
                for i, question in enumerate(rq[:3]):
                    print(f"  Q{i+1}: {question.get('question', 'N/A')}")
                    
        else:
            print(f"❌ Knowledge graph search failed with status {response.status_code}")
            
    except Exception as e:
        print(f"❌ Knowledge graph search error: {e}")

if __name__ == "__main__":
    test_google_web_search_tool()
