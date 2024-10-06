import googlemaps
from typing import List, Optional
from typing_extensions import TypedDict
from vital_agent_resource_app.tools.abstract_tool import AbstractTool
from vital_agent_resource_app.tools.tool_request import ToolRequest
from vital_agent_resource_app.tools.tool_response import ToolResponse


class PlaceDetails(TypedDict):
    name: str
    address: str
    place_id: str
    latitude: Optional[float]
    longitude: Optional[float]
    business_status: Optional[str]
    icon: Optional[str]
    types: Optional[List[str]]
    url: Optional[str]
    vicinity: Optional[str]
    formatted_phone_number: Optional[str]
    website: Optional[str]


class PlaceSearchTool(AbstractTool):

    def handle_tool_request(self, tool_request: ToolRequest) -> ToolResponse:

        request_data = tool_request.request_data

        place_search_string = request_data["place_search_string"]

        results = self.search_place(place_search_string)

        results_dict = {
            "place_search_results": results
        }

        tool_response = ToolResponse(data=results_dict)

        return tool_response

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

