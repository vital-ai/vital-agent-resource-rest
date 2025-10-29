import requests
from typing import List, Dict, Any, Optional
from vital_agent_resource_app.tools.abstract_tool import AbstractTool
from vital_agent_resource_app.tools.tool_request import ToolRequest
from vital_agent_resource_app.tools.tool_response import ToolResponse
from vital_agent_resource_app.tools.web_search.models import WebSearchResult, WebSearchInput

class GoogleWebSearchTool(AbstractTool):

    def get_examples(self) -> List[Dict[str, Any]]:
        """Return list of example requests for Google Web Search tool"""
        return [
            {
                "tool": "google_web_search_tool",
                "tool_input": {
                    "search_query": "Apple Cider recipes",
                    "num_results": 10,
                    "location": "Austin,Texas",
                    "language": "en"
                }
            },
            {
                "tool": "google_web_search_tool",
                "tool_input": {
                    "search_query": "Python programming tutorials",
                    "search_type": "search",
                    "time_period": "month"
                }
            },
            {
                "tool": "google_web_search_tool",
                "tool_input": {
                    "search_query": "latest tech news",
                    "search_type": "news",
                    "time_period": "day",
                    "num_results": 5
                }
            }
        ]

    def handle_tool_request(self, tool_request: ToolRequest) -> ToolResponse:
        import time
        start_time = time.time()
        
        # Extract search parameters from validated tool input
        validated_input = tool_request.tool_input
        search_query = validated_input.search_query
        num_results = validated_input.num_results or 10
        location = validated_input.location
        language = validated_input.language
        country = validated_input.country
        device = validated_input.device or "desktop"
        safe_search = validated_input.safe_search
        search_type = validated_input.search_type or "search"
        time_period = validated_input.time_period
        
        try:
            # Get the raw search results to extract additional data
            raw_results = self._get_raw_search_results(
                search_query=search_query,
                num_results=num_results,
                location=location,
                language=language,
                country=country,
                device=device,
                safe_search=safe_search,
                search_type=search_type,
                time_period=time_period
            )
            
            # Extract structured results
            results = self.google_web_search(
                search_query=search_query,
                num_results=num_results,
                location=location,
                language=language,
                country=country,
                device=device,
                safe_search=safe_search,
                search_type=search_type,
                time_period=time_period
            )
            
            # Extract additional data structures
            knowledge_graph = self._extract_knowledge_graph(raw_results)
            related_questions = self._extract_related_questions(raw_results)
            search_information = raw_results.get('search_information', {})
            
            # Create structured output using the registered model
            from vital_agent_resource_app.tools.web_search.models import WebSearchOutput
            tool_output = WebSearchOutput(
                tool="google_web_search_tool",
                query=search_query,
                results=results,
                total_results=search_information.get('total_results', len(results)),
                knowledge_graph=knowledge_graph,
                related_questions=related_questions,
                search_information=search_information
            )
            
            return self._create_success_response(tool_output.dict(), start_time)
            
        except Exception as e:
            return self._create_error_response(str(e), start_time)

    def _get_raw_search_results(self, search_query: str, num_results: int = 10, location: str = None, 
                               language: str = None, country: str = None, device: str = "desktop",
                               safe_search: str = None, search_type: str = "search", 
                               time_period: str = None) -> dict:
        """Get raw search results from SerpAPI for additional data extraction"""
        import requests
        from serpapi import GoogleSearch
        
        try:
            # Get API key from app config
            api_key = self.config.get('api_key')
            if not api_key:
                raise Exception("SerpAPI API key not found in configuration")
            
            # Build search parameters
            params = {
                "engine": "google",
                "q": search_query,
                "api_key": api_key,
                "num": num_results,
                "device": device
            }
            
            # Add optional parameters
            if location:
                params["location"] = location
            if language:
                params["hl"] = language
            if country:
                params["gl"] = country
            if safe_search:
                params["safe"] = safe_search
            if time_period:
                params["tbs"] = f"qdr:{time_period}"
            
            # Set search type specific parameters
            if search_type == "news":
                params["tbm"] = "nws"
            elif search_type == "images":
                params["tbm"] = "isch"
            elif search_type == "shopping":
                params["tbm"] = "shop"
            
            # Execute search
            search = GoogleSearch(params)
            results = search.get_dict()
            
            if search.get_response().status_code == 200:
                return results
            else:
                raise Exception(f"Search API returned status code: {search.get_response().status_code}")
                
        except requests.exceptions.RequestException as e:
            raise Exception(f"Network error occurred: {e}")
        except Exception as e:
            raise Exception(f"Search error: {e}")

    def google_web_search(self, search_query: str, num_results: int = 10, location: str = None, 
                         language: str = None, country: str = None, device: str = "desktop",
                         safe_search: str = None, search_type: str = "search", 
                         time_period: str = None) -> List[WebSearchResult]:
        """Perform Google web search and return structured results"""
        
        # Get raw results to avoid duplicate API calls
        results = self._get_raw_search_results(
            search_query, num_results, location, language, country, 
            device, safe_search, search_type, time_period
        )
        
        web_search_results = []
        
        # Process different result types based on search type
        if search_type == "news":
            result_types = [("news_results", "news")]
        elif search_type == "images":
            result_types = [("images_results", "image")]
        elif search_type == "shopping":
            result_types = [("shopping_results", "shopping")]
        else:
            # For general search, extract from all available result blocks
            result_types = [
                ("organic_results", "organic"),
                ("news_results", "news"),
                ("shopping_results", "shopping"),
                ("recipes_results", "recipe"),
                ("images_results", "image")
            ]
        
        for result_key, result_type in result_types:
            result_list = results.get(result_key, [])
            for idx, result in enumerate(result_list):
                web_result = self._extract_result_fields(result, result_type, idx)
                if web_result:
                    web_search_results.append(web_result)
        
        # Process local results if available
        local_results = results.get("local_results", {})
        if isinstance(local_results, dict):
            places = local_results.get("places", [])
        else:
            places = local_results if isinstance(local_results, list) else []
            
        for idx, result in enumerate(places):
            web_result = self._extract_result_fields(result, "local", idx)
            if web_result:
                web_search_results.append(web_result)
        
        return web_search_results
    
    def _extract_result_fields(self, result: dict, result_type: str, idx: int) -> Optional[WebSearchResult]:
        """Extract fields from a search result based on its type"""
        try:
            # Common fields with fallbacks for different result structures
            title = result.get('title', result.get('name', result.get('product_name', 'No Title')))
            link = result.get('link', result.get('url', result.get('product_link', '')))
            snippet = result.get('snippet', result.get('description', result.get('summary', None)))
            position = result.get('position', idx + 1)
            displayed_link = result.get('displayed_link', result.get('source', result.get('domain', None)))
            thumbnail = result.get('thumbnail', result.get('image', result.get('product_image', None)))
            source = result.get('source', result.get('domain', None))
            date = result.get('date', result.get('published_date', result.get('time', None)))
            
            # Type-specific fields
            price = None
            rating = None
            reviews = None
            address = None
            phone = None
            ingredients = None
            total_time = None
            
            if result_type == "shopping":
                price = result.get('price', result.get('extracted_price', None))
                rating = result.get('rating')
                reviews = result.get('reviews')
                
            elif result_type == "local":
                address = result.get('address')
                phone = result.get('phone')
                rating = result.get('rating')
                reviews = result.get('reviews')
                
            elif result_type == "recipe":
                ingredients = result.get('ingredients', [])
                total_time = result.get('total_time', result.get('prep_time', None))
                rating = result.get('rating')
                
            return WebSearchResult(
                title=title,
                link=link,
                snippet=snippet,
                position=position,
                displayed_link=displayed_link,
                thumbnail=thumbnail,
                source=source,
                date=date,
                result_type=result_type,
                price=price,
                rating=rating,
                reviews=reviews,
                address=address,
                phone=phone,
                ingredients=ingredients,
                total_time=total_time
            )
        except Exception as e:
            print(f"Error extracting result fields: {e}")
            return None
    
    def _extract_knowledge_graph(self, results: dict) -> Optional['KnowledgeGraph']:
        """Extract knowledge graph information from search results"""
        kg_data = results.get('knowledge_graph', {})
        if not kg_data:
            return None
            
        from vital_agent_resource_app.tools.web_search.models import KnowledgeGraph
        return KnowledgeGraph(
            title=kg_data.get('title'),
            type=kg_data.get('type'),
            description=kg_data.get('description'),
            source=kg_data.get('source'),
            header_images=kg_data.get('header_images', [])
        )
    
    def _extract_related_questions(self, results: dict) -> Optional[List['RelatedQuestion']]:
        """Extract related questions from search results"""
        questions_data = results.get('related_questions', [])
        if not questions_data:
            return None
            
        from vital_agent_resource_app.tools.web_search.models import RelatedQuestion
        related_questions = []
        
        for q_data in questions_data:
            question = RelatedQuestion(
                question=q_data.get('question', ''),
                snippet=q_data.get('snippet'),
                title=q_data.get('title'),
                link=q_data.get('link')
            )
            related_questions.append(question)
            
        return related_questions if related_questions else None
