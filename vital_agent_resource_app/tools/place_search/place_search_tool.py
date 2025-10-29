import googlemaps
from typing import List, Dict, Any
from vital_agent_resource_app.tools.abstract_tool import AbstractTool
from vital_agent_resource_app.tools.tool_request import ToolRequest
from vital_agent_resource_app.tools.tool_response import ToolResponse
from vital_agent_resource_app.tools.place_search.models import PlaceDetails


class PlaceSearchTool(AbstractTool):

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

    def handle_tool_request(self, tool_request: ToolRequest) -> ToolResponse:
        import time
        start_time = time.time()
        
        # Extract search string from validated tool input
        validated_input = tool_request.tool_input
        place_search_string = validated_input.place_search_string
        
        try:
            results = self.search_place(place_search_string)
            
            # Create structured output using the registered model
            from vital_agent_resource_app.tools.place_search.models import PlaceSearchOutput
            tool_output = PlaceSearchOutput(
                tool="place_search_tool",
                results=results
            )
            
            return self._create_success_response(tool_output.dict(), start_time)
            
        except Exception as e:
            return self._create_error_response(str(e), start_time)

    def search_place(self, place_string: str) -> List[PlaceDetails]:

        print(f"PlaceString: {place_string}")

        api_key = self.config.get("api_key", "")

        gmaps = googlemaps.Client(key=api_key)

        search_response = gmaps.places(place_string)

        results = search_response.get("results", [])

        places = []

        for result in results:
            place_id = result.get('place_id', None)
            if not place_id:
                continue

            place_details = gmaps.place(place_id=place_id, fields=[
                "address_component", "adr_address", "business_status", "formatted_address",
                "geometry", "icon", "name", "photo", "place_id", "plus_code", "type",
                "url", "utc_offset", "vicinity", "formatted_phone_number", "website"
            ])

            details = place_details.get("result", {})

            lat = details.get("geometry", {}).get("location", {}).get("lat", None)
            lon = details.get("geometry", {}).get("location", {}).get("lng", None)

            place = PlaceDetails(
                name=result.get('name', "Unknown"),
                address=result.get('formatted_address', "Unknown"),
                place_id=result.get('place_id', "Unknown"),
                latitude=lat if lat is not None else None,
                longitude=lon if lon is not None else None,
                business_status=details.get("business_status", None),
                icon=details.get("icon", None),
                types=details.get("types", []),
                url=details.get("url", None),
                vicinity=details.get("vicinity", None),
                formatted_phone_number=details.get("formatted_phone_number", None),
                website=details.get("website", None)
            )

            places.append(place)

        return places

