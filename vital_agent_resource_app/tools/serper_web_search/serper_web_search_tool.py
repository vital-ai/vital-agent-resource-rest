import logging
import time
import httpx
from typing import List, Dict, Any, Optional
from vital_agent_resource_app.tools.abstract_tool import AbstractTool
from vital_agent_resource_app.tools.tool_request import ToolRequest
from vital_agent_resource_app.tools.tool_response import ToolResponse
from vital_agent_resource_app.tools.serper_web_search.models import (
    SerperWebSearchResult, SerperWebSearchOutput,
    SerperKnowledgeGraph, SerperPeopleAlsoAsk, SerperRelatedSearch
)

logger = logging.getLogger("VitalAgentContainerLogger")

# Serper endpoints by search type
SERPER_ENDPOINTS = {
    "search": "https://google.serper.dev/search",
    "news": "https://google.serper.dev/news",
    "images": "https://google.serper.dev/images",
    "shopping": "https://google.serper.dev/shopping",
    "places": "https://google.serper.dev/places",
}


class SerperWebSearchTool(AbstractTool):

    def get_examples(self) -> List[Dict[str, Any]]:
        """Return list of example requests for Serper Web Search tool"""
        return [
            {
                "tool": "serper_web_search_tool",
                "tool_input": {
                    "search_query": "Apple Cider recipes",
                    "num_results": 10,
                    "location": "Austin,Texas",
                    "language": "en"
                }
            },
            {
                "tool": "serper_web_search_tool",
                "tool_input": {
                    "search_query": "Python programming tutorials",
                    "search_type": "search",
                    "time_period": "month"
                }
            },
            {
                "tool": "serper_web_search_tool",
                "tool_input": {
                    "search_query": "latest tech news",
                    "search_type": "news",
                    "time_period": "day",
                    "num_results": 5
                }
            },
            {
                "tool": "serper_web_search_tool",
                "tool_input": {
                    "search_query": "pizza restaurants",
                    "search_type": "places",
                    "location": "New York,New York",
                    "num_results": 10
                }
            }
        ]

    async def handle_tool_request(self, tool_request: ToolRequest) -> ToolResponse:
        start_time = time.time()

        logger.info("Serper Web Search Tool - handle_tool_request called")

        validated_input = tool_request.tool_input
        search_query = validated_input.search_query

        logger.info(f"Search query: {search_query}")
        num_results = validated_input.num_results or 10
        location = validated_input.location
        language = validated_input.language
        country = validated_input.country
        search_type = validated_input.search_type or "search"
        time_period = validated_input.time_period
        page = validated_input.page

        try:
            raw_results = await self._get_raw_search_results(
                search_query=search_query,
                num_results=num_results,
                location=location,
                language=language,
                country=country,
                search_type=search_type,
                time_period=time_period,
                page=page
            )

            # Check for API errors
            api_error = None
            api_status_code = None

            error_value = raw_results.get('error')
            if error_value:
                if isinstance(error_value, bool) and error_value:
                    api_error = raw_results.get('error_message', 'Unknown API error')
                    api_status_code = raw_results.get('status_code')
                    logger.error(f"API Error detected: {api_error}")

                    tool_output = SerperWebSearchOutput(
                        tool="serper_web_search_tool",
                        query=search_query,
                        results=[],
                        total_results=0,
                        api_error=api_error,
                        api_status_code=api_status_code
                    )
                    return self._create_success_response(tool_output.dict(), start_time)

            results = self._extract_search_results(raw_results, search_type)
            knowledge_graph = self._extract_knowledge_graph(raw_results)
            people_also_ask = self._extract_people_also_ask(raw_results)
            related_searches = self._extract_related_searches(raw_results)

            search_params = raw_results.get('searchParameters', {})

            logger.info("=" * 80)
            logger.info("SERPER WEB SEARCH RESULTS")
            logger.info("=" * 80)
            logger.info(f"Query: '{search_query}'")
            logger.info(f"Total results found: {len(results)}")
            logger.info(f"Result types: {[r.result_type for r in results]}")
            logger.info("-" * 80)

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
                if result.address:
                    logger.info(f"  Address: {result.address}")

            if knowledge_graph:
                logger.info("-" * 80)
                logger.info("KNOWLEDGE GRAPH:")
                logger.info(f"  Title: {knowledge_graph.title}")
                logger.info(f"  Type: {knowledge_graph.type}")
                if knowledge_graph.description:
                    desc_preview = knowledge_graph.description[:100] + '...' if len(knowledge_graph.description) > 100 else knowledge_graph.description
                    logger.info(f"  Description: {desc_preview}")

            if people_also_ask:
                logger.info("-" * 80)
                logger.info(f"PEOPLE ALSO ASK ({len(people_also_ask)}):")
                for idx, paa in enumerate(people_also_ask, 1):
                    logger.info(f"  Q{idx}: {paa.question}")

            if related_searches:
                logger.info("-" * 80)
                logger.info(f"RELATED SEARCHES ({len(related_searches)}):")
                for rs in related_searches:
                    logger.info(f"  - {rs.query}")

            logger.info("=" * 80)

            tool_output = SerperWebSearchOutput(
                tool="serper_web_search_tool",
                query=search_query,
                results=results,
                total_results=len(results),
                knowledge_graph=knowledge_graph,
                people_also_ask=people_also_ask,
                related_searches=related_searches,
                api_error=api_error,
                api_status_code=api_status_code
            )

            return self._create_success_response(tool_output.dict(), start_time)

        except Exception as e:
            logger.error(f"Serper Web Search error: {str(e)}")
            return self._create_error_response(str(e), start_time)

    async def _get_raw_search_results(self, search_query: str, num_results: int = 10,
                                      location: str = None, language: str = None,
                                      country: str = None, search_type: str = "search",
                                      time_period: str = None, page: int = None) -> dict:
        """Get raw search results from Serper.dev API using async httpx."""
        api_key = self.config.get('api_key')
        logger.info(f"Config keys available: {list(self.config.keys())}")
        logger.info(f"API key loaded: ...{api_key[-4:] if api_key else 'None'}")

        if not api_key:
            raise Exception("Serper API key not found in configuration")

        endpoint = SERPER_ENDPOINTS.get(search_type, SERPER_ENDPOINTS["search"])

        # Build JSON payload
        payload = {
            "q": search_query,
            "num": num_results,
        }

        if location:
            payload["location"] = location
        if language:
            payload["hl"] = language
        if country:
            payload["gl"] = country
        if time_period:
            payload["tbs"] = f"qdr:{time_period[0]}"
        if page:
            payload["page"] = page

        headers = {
            "X-API-KEY": api_key,
            "Content-Type": "application/json"
        }

        logger.info(f"Serper request: endpoint={endpoint}, q={search_query}, num={num_results}")

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(endpoint, json=payload, headers=headers)

            logger.info(f"Serper response status: {resp.status_code}")

            if resp.status_code == 200:
                results = resp.json()
                logger.info(f"Serper returned keys: {list(results.keys())}")
                return results
            else:
                error_body = resp.text[:500]
                logger.error(f"Serper API returned status code: {resp.status_code}")
                logger.error(f"Response body: {error_body}")
                return {
                    'error': True,
                    'status_code': resp.status_code,
                    'error_message': error_body,
                }
        except httpx.TimeoutException as e:
            raise Exception(f"Serper request timed out: {e}")
        except httpx.RequestError as e:
            raise Exception(f"Network error occurred: {e}")

    def _extract_search_results(self, results: dict, search_type: str = "search") -> List[SerperWebSearchResult]:
        """Extract structured search results from raw Serper response dict"""
        web_search_results = []

        if search_type == "search":
            # Organic results
            for idx, result in enumerate(results.get('organic', [])):
                web_result = self._extract_result_fields(result, "organic", idx)
                if web_result:
                    web_search_results.append(web_result)

        elif search_type == "news":
            for idx, result in enumerate(results.get('news', [])):
                web_result = self._extract_result_fields(result, "news", idx)
                if web_result:
                    web_search_results.append(web_result)

        elif search_type == "images":
            for idx, result in enumerate(results.get('images', [])):
                web_result = self._extract_result_fields(result, "image", idx)
                if web_result:
                    web_search_results.append(web_result)

        elif search_type == "shopping":
            for idx, result in enumerate(results.get('shopping', [])):
                web_result = self._extract_result_fields(result, "shopping", idx)
                if web_result:
                    web_search_results.append(web_result)

        elif search_type == "places":
            for idx, result in enumerate(results.get('places', [])):
                web_result = self._extract_result_fields(result, "place", idx)
                if web_result:
                    web_search_results.append(web_result)

        return web_search_results

    def _extract_result_fields(self, result: dict, result_type: str, idx: int) -> Optional[SerperWebSearchResult]:
        """Extract fields from a search result based on its type"""
        try:
            title = result.get('title', result.get('name', 'No Title'))
            link = result.get('link', result.get('url', result.get('website', '')))
            snippet = result.get('snippet', result.get('description', None))
            position = result.get('position', idx + 1)
            date = result.get('date', None)
            source = result.get('source', None)
            thumbnail = result.get('thumbnail', None)
            sitelinks = result.get('sitelinks', None)

            # Type-specific fields
            image_url = None
            price = None
            rating = None
            rating_count = None
            address = None
            phone_number = None
            website = None
            category = None
            cid = None
            latitude = None
            longitude = None
            price_level = None

            if result_type == "image":
                image_url = result.get('imageUrl', result.get('thumbnailUrl', None))
                link = link or image_url or ''

            elif result_type == "shopping":
                price = result.get('price', None)
                rating = result.get('rating', None)
                source = result.get('source', None)

            elif result_type == "place":
                address = result.get('address', None)
                phone_number = result.get('phoneNumber', None)
                website = result.get('website', None)
                rating = result.get('rating', None)
                rating_count = result.get('ratingCount', None)
                category = result.get('category', None)
                cid = result.get('cid', None)
                latitude = result.get('latitude', None)
                longitude = result.get('longitude', None)
                price_level = result.get('priceLevel', None)
                # For places, link may not be present — use website as fallback
                link = link or website or ''

            return SerperWebSearchResult(
                title=title,
                link=link,
                snippet=snippet,
                position=position,
                result_type=result_type,
                date=date,
                source=source,
                image_url=image_url,
                thumbnail=thumbnail,
                sitelinks=sitelinks,
                price=price,
                rating=rating,
                rating_count=rating_count,
                address=address,
                phone_number=phone_number,
                website=website,
                category=category,
                cid=cid,
                latitude=latitude,
                longitude=longitude,
                price_level=price_level
            )
        except Exception as e:
            logger.error(f"Error extracting Serper result fields: {e}")
            return None

    def _extract_knowledge_graph(self, results: dict) -> Optional[SerperKnowledgeGraph]:
        """Extract knowledge graph information from Serper results"""
        kg_data = results.get('knowledgeGraph', {})
        if not kg_data:
            return None

        return SerperKnowledgeGraph(
            title=kg_data.get('title'),
            type=kg_data.get('type'),
            description=kg_data.get('description'),
            website=kg_data.get('website'),
            image_url=kg_data.get('imageUrl'),
            attributes=kg_data.get('attributes')
        )

    def _extract_people_also_ask(self, results: dict) -> Optional[List[SerperPeopleAlsoAsk]]:
        """Extract People Also Ask from Serper results"""
        paa_data = results.get('peopleAlsoAsk', [])
        if not paa_data:
            return None

        people_also_ask = []
        for item in paa_data:
            paa = SerperPeopleAlsoAsk(
                question=item.get('question', ''),
                snippet=item.get('snippet', None),
                title=item.get('title', None),
                link=item.get('link', None)
            )
            people_also_ask.append(paa)

        return people_also_ask if people_also_ask else None

    def _extract_related_searches(self, results: dict) -> Optional[List[SerperRelatedSearch]]:
        """Extract related searches from Serper results"""
        rs_data = results.get('relatedSearches', [])
        if not rs_data:
            return None

        related_searches = []
        for item in rs_data:
            query = item.get('query', '')
            if query:
                related_searches.append(SerperRelatedSearch(query=query))

        return related_searches if related_searches else None
