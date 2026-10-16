import asyncio
import googlemaps
import time
import logging
from typing import List, Dict, Any
from vital_agent_resource_app.tools.abstract_tool import AbstractTool
from vital_agent_resource_app.tools.tool_request import ToolRequest
from vital_agent_resource_app.tools.tool_response import ToolResponse
from vital_agent_resource_app.tools.place_search.models import PlaceDetails

logger = logging.getLogger("VitalAgentContainerLogger")

# Text search already returns everything else; these four need Place Details.
DETAILS_FIELDS = ["formatted_phone_number", "website", "url", "vicinity"]

# Details is billed per call, and a broad query returns up to 20 places, most of
# which the caller discards. 1-2 risks missing the right listing when the
# business is not ranked first.
DEFAULT_DETAILS_LIMIT = 3


class PlaceSearchTool(AbstractTool):

    def _details_limit(self) -> int:
        value = (self.config or {}).get("details_limit")
        if value is None:
            return DEFAULT_DETAILS_LIMIT
        try:
            limit = int(value)
            if limit < 0:
                raise ValueError(value)
            return limit
        except (TypeError, ValueError):
            logger.warning(f"Invalid place_search details_limit {value!r}; using {DEFAULT_DETAILS_LIMIT}")
            return DEFAULT_DETAILS_LIMIT

    def get_examples(self) -> List[Dict[str, Any]]:
        """Return list of example requests for Place Search tool"""
        return [
            {
                "tool": "place_search_tool",
                "tool_input": {
                    "place_search_string": "restaurants near me"
                }
            },
            {
                "tool": "place_search_tool",
                "tool_input": {
                    "place_search_string": "Philly"
                }
            }
        ]

    async def handle_tool_request(self, tool_request: ToolRequest) -> ToolResponse:
        start_time = time.time()
        
        # Extract search string from validated tool input
        validated_input = tool_request.tool_input
        place_search_string = validated_input.place_search_string
        
        try:
            # googlemaps client is sync — run in thread pool
            results = await asyncio.to_thread(self.search_place, place_search_string)
            
            from vital_agent_resource_app.tools.place_search.models import PlaceSearchOutput
            tool_output = PlaceSearchOutput(
                tool="place_search_tool",
                results=results
            )
            
            return self._create_success_response(tool_output.model_dump(), start_time)
            
        except Exception as e:
            return self._create_error_response(str(e), start_time)

    def search_place(self, place_string: str) -> List[PlaceDetails]:

        print(f"PlaceString: {place_string}")

        api_key = self.config.get("api_key", "")

        gmaps = googlemaps.Client(key=api_key)

        search_response = gmaps.places(place_string)

        results = search_response.get("results", [])

        details_limit = self._details_limit()
        details_calls = 0

        places = []

        for result in results:
            place_id = result.get('place_id', None)
            if not place_id:
                continue

            # Only the top results get Details. A failure there costs that
            # result its contact fields, not the whole search.
            details = {}
            if details_calls < details_limit:
                details_calls += 1
                try:
                    details = gmaps.place(place_id=place_id, fields=DETAILS_FIELDS).get("result", {})
                except Exception as e:
                    logger.warning(f"Place Details failed for {place_id}: {e}")

            location = result.get("geometry", {}).get("location", {})

            place = PlaceDetails(
                name=result.get('name', "Unknown"),
                address=result.get('formatted_address', "Unknown"),
                place_id=place_id,
                latitude=location.get("lat"),
                longitude=location.get("lng"),
                business_status=result.get("business_status"),
                icon=result.get("icon"),
                types=result.get("types", []),
                rating=result.get("rating"),
                user_ratings_total=result.get("user_ratings_total"),
                url=details.get("url"),
                vicinity=details.get("vicinity"),
                formatted_phone_number=details.get("formatted_phone_number"),
                website=details.get("website")
            )

            places.append(place)

        return places

