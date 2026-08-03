import logging
import time
import httpx
from typing import List, Dict, Any, Optional
from vital_agent_resource_app.tools.abstract_tool import AbstractTool
from vital_agent_resource_app.tools.tool_request import ToolRequest
from vital_agent_resource_app.tools.tool_response import ToolResponse
from vital_agent_resource_app.tools.web_search.models import WebSearchResult, WebSearchInput

logger = logging.getLogger("VitalAgentContainerLogger")

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

    async def handle_tool_request(self, tool_request: ToolRequest) -> ToolResponse:
        start_time = time.time()
        
        logger.info("Google Web Search Tool - handle_tool_request called")
        
        validated_input = tool_request.tool_input
        search_query = validated_input.search_query
        
        logger.info(f"Search query: {search_query}")
        num_results = validated_input.num_results or 10
        location = validated_input.location
        language = validated_input.language
        country = validated_input.country
        device = validated_input.device or "desktop"
        safe_search = validated_input.safe_search
        search_type = validated_input.search_type or "search"
        time_period = validated_input.time_period
        ludocid = validated_input.ludocid
        kgmid = validated_input.kgmid
        
        try:
            raw_results = await self._get_raw_search_results(
                search_query=search_query,
                num_results=num_results,
                location=location,
                language=language,
                country=country,
                device=device,
                safe_search=safe_search,
                search_type=search_type,
                time_period=time_period,
                ludocid=ludocid,
                kgmid=kgmid
            )
            
            # Reuse the same extraction logic as sync version
            results = self._extract_search_results(raw_results, search_type)
            
            api_error = None
            api_status_code = None
            
            error_value = raw_results.get('error')
            if error_value:
                if isinstance(error_value, str):
                    logger.info(f"SerpAPI message: {error_value}")
                    api_error = None
                    api_status_code = None
                else:
                    api_error = raw_results.get('error_message', 'Unknown API error')
                    api_status_code = raw_results.get('status_code')
                    logger.error(f"API Error detected: {api_error}")
                knowledge_graph = None
                related_questions = None
                search_information = {}
            else:
                knowledge_graph = self._extract_knowledge_graph(raw_results)
                related_questions = self._extract_related_questions(raw_results)
                search_information = raw_results.get('search_information', {})
                
                logger.info("="*80)
                logger.info("GOOGLE WEB SEARCH RESULTS")
                logger.info("="*80)
                logger.info(f"Query: '{search_query}'")
                logger.info(f"Total results found: {len(results)}")
                logger.info(f"Result types: {[r.result_type for r in results]}")
                logger.info("-"*80)
                
                for idx, result in enumerate(results, 1):
                    logger.info(f"Result {idx}: [{result.result_type}] {result.title}")
                    logger.info(f"  Link: {result.link}")
                    if result.snippet:
                        snippet_preview = result.snippet[:100] + '...' if len(result.snippet) > 100 else result.snippet
                        logger.info(f"  Snippet: {snippet_preview}")
                    if result.price:
                        logger.info(f"  Price: {result.price}")
                    if result.rating:
                        logger.info(f"  Rating: {result.rating}")
                
                if knowledge_graph:
                    logger.info("-"*80)
                    logger.info("KNOWLEDGE GRAPH:")
                    logger.info(f"  Title: {knowledge_graph.title}")
                    logger.info(f"  Type: {knowledge_graph.type}")
                    if knowledge_graph.description:
                        desc_preview = knowledge_graph.description[:100] + '...' if len(knowledge_graph.description) > 100 else knowledge_graph.description
                        logger.info(f"  Description: {desc_preview}")
                
                if related_questions:
                    logger.info("-"*80)
                    logger.info(f"RELATED QUESTIONS ({len(related_questions)}):")
                    for idx, rq in enumerate(related_questions, 1):
                        logger.info(f"  Q{idx}: {rq.question}")
                
                logger.info("="*80)
            
            from vital_agent_resource_app.tools.web_search.models import WebSearchOutput
            tool_output = WebSearchOutput(
                tool="google_web_search_tool",
                query=search_query,
                results=results,
                total_results=search_information.get('total_results', len(results)),
                knowledge_graph=knowledge_graph,
                related_questions=related_questions,
                search_information=search_information,
                api_error=api_error,
                api_status_code=api_status_code
            )
            
            return self._create_success_response(tool_output.model_dump(), start_time)
            
        except Exception as e:
            logger.error(f"Google Web Search error: {str(e)}")
            return self._create_error_response(str(e), start_time)

    async def _get_raw_search_results(self, search_query: str, num_results: int = 10,
                                            location: str = None, language: str = None,
                                            country: str = None, device: str = "desktop",
                                            safe_search: str = None, search_type: str = "search",
                                            time_period: str = None, ludocid: str = None,
                                            kgmid: str = None) -> dict:
        """Get raw search results from SerpAPI using async httpx."""
        api_key = self.config.get('api_key')
        logger.info(f"Config keys available: {list(self.config.keys())}")
        logger.info(f"API key loaded: ...{api_key[-4:] if api_key else 'None'}")
        
        if not api_key:
            raise Exception("SerpAPI API key not found in configuration")
        
        params = {
            "engine": "google",
            "q": search_query,
            "api_key": api_key,
            "num": num_results,
            "device": device,
            "output": "json"
        }
        
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
        if ludocid:
            params["ludocid"] = ludocid
        if kgmid:
            params["kgmid"] = kgmid
        
        if search_type == "news":
            params["tbm"] = "nws"
        elif search_type == "images":
            params["tbm"] = "isch"
        elif search_type == "shopping":
            params["tbm"] = "shop"
        elif search_type == "local":
            params["tbm"] = "lcl"
        
        logger.info(f"SerpAPI request params: engine={params['engine']}, q={params['q']}, num={params['num']}")
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.get("https://serpapi.com/search.json", params=params)
            
            logger.info(f"SerpAPI response status: {resp.status_code}")
            
            if resp.status_code == 200:
                results = resp.json()
                logger.info(f"SerpAPI returned {len(results.get('organic_results', []))} organic results")
                return results
            else:
                error_body = resp.text[:500]
                logger.error(f"Search API returned status code: {resp.status_code}")
                logger.error(f"Response body: {error_body}")
                return {
                    'error': True,
                    'status_code': resp.status_code,
                    'error_message': error_body,
                    'organic_results': []
                }
        except httpx.TimeoutException as e:
            raise Exception(f"SerpAPI request timed out: {e}")
        except httpx.RequestError as e:
            raise Exception(f"Network error occurred: {e}")

    def _extract_search_results(self, results: dict, search_type: str = "search") -> List[WebSearchResult]:
        """Extract structured search results from raw SerpAPI response dict"""
        web_search_results = []
        
        # Process different result types based on search type
        if search_type == "news":
            result_types = [("news_results", "news")]
        elif search_type == "images":
            result_types = [("images_results", "image")]
        elif search_type == "shopping":
            result_types = [("shopping_results", "shopping")]
        elif search_type == "local":
            result_types = []
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
            if idx == 0:
                logger.info(f"Sample local result keys: {list(result.keys())}")
                logger.info(f"Sample local result place_id={result.get('place_id')}, data_cid={result.get('data_cid')}, hours={result.get('hours')}, operating_hours={result.get('operating_hours')}")
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
            place_id = None
            hours = None
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
                place_id = result.get('place_id', result.get('data_cid', None))
                hours = result.get('hours', result.get('operating_hours', None))
                
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
                place_id=place_id,
                hours=hours,
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
