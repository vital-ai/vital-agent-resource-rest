from pydantic import BaseModel, Field
from typing import List, Optional, Literal


class SerperWebSearchResult(BaseModel):
    title: str = Field(..., description="Title of the search result")
    link: str = Field(..., description="URL of the search result")
    snippet: Optional[str] = Field(None, description="Snippet/description of the search result")
    position: Optional[int] = Field(None, description="Position in search results")
    result_type: str = Field("organic", description="Type of result (organic, news, shopping, image, place)")
    date: Optional[str] = Field(None, description="Publication date if available")
    source: Optional[str] = Field(None, description="Source domain of the result")
    image_url: Optional[str] = Field(None, description="Image URL for image results")
    thumbnail: Optional[str] = Field(None, description="Thumbnail image URL if available")
    sitelinks: Optional[List[dict]] = Field(None, description="Sitelinks if present")

    # Shopping-specific fields
    price: Optional[str] = Field(None, description="Price for shopping results")
    rating: Optional[float] = Field(None, description="Rating for place/shopping results")

    # Place-specific fields
    rating_count: Optional[int] = Field(None, description="Number of ratings/reviews for place results")
    address: Optional[str] = Field(None, description="Address for place results")
    phone_number: Optional[str] = Field(None, description="Phone number for place results")
    website: Optional[str] = Field(None, description="Business website for place results")
    category: Optional[str] = Field(None, description="Business category for place results")
    cid: Optional[str] = Field(None, description="Google CID for place results (can be used with SerpAPI ludocid)")
    latitude: Optional[float] = Field(None, description="Latitude for place results")
    longitude: Optional[float] = Field(None, description="Longitude for place results")
    price_level: Optional[str] = Field(None, description="Price level for place results (e.g. '$$')")


class SerperKnowledgeGraph(BaseModel):
    title: Optional[str] = Field(None, description="Knowledge graph title")
    type: Optional[str] = Field(None, description="Knowledge graph type")
    description: Optional[str] = Field(None, description="Knowledge graph description")
    website: Optional[str] = Field(None, description="Knowledge graph website")
    image_url: Optional[str] = Field(None, description="Knowledge graph image URL")
    attributes: Optional[dict] = Field(None, description="Knowledge graph key-value attributes")


class SerperPeopleAlsoAsk(BaseModel):
    question: str = Field(..., description="The question text")
    snippet: Optional[str] = Field(None, description="Answer snippet")
    title: Optional[str] = Field(None, description="Source title")
    link: Optional[str] = Field(None, description="Source link")


class SerperRelatedSearch(BaseModel):
    query: str = Field(..., description="Related search query")


class SerperWebSearchInput(BaseModel):
    """Input model for Serper Web Search tool"""
    search_query: str = Field(..., description="Search query string", min_length=1)
    search_type: Optional[Literal["search", "news", "images", "shopping", "places"]] = Field(
        "search", description="Type of search to perform"
    )
    num_results: Optional[int] = Field(10, description="Number of results to return", ge=1, le=100)
    location: Optional[str] = Field(None, description="Location for localized search results (e.g., 'Austin,Texas')")
    language: Optional[str] = Field(None, description="Google UI language (e.g., 'en' for English)")
    country: Optional[str] = Field(None, description="Google country code (e.g., 'us')")
    time_period: Optional[Literal["hour", "day", "week", "month", "year"]] = Field(
        None, description="Time period filter for results"
    )
    page: Optional[int] = Field(None, description="Pagination page number")

    model_config = {
        "json_schema_extra": {
            "example": {
                "search_query": "Apple Cider recipes",
                "search_type": "search",
                "num_results": 10,
                "location": "Austin,Texas",
                "language": "en"
            }
        }
    }


class SerperWebSearchOutput(BaseModel):
    """Output model for Serper Web Search tool"""
    tool: Literal["serper_web_search_tool"] = Field(..., description="Tool identifier")
    query: str = Field(..., description="The search query that was executed")
    results: List[SerperWebSearchResult] = Field(default_factory=list, description="Search results")
    total_results: Optional[int] = Field(None, description="Estimated total results")
    knowledge_graph: Optional[SerperKnowledgeGraph] = Field(None, description="Knowledge graph information")
    people_also_ask: Optional[List[SerperPeopleAlsoAsk]] = Field(None, description="People Also Ask questions")
    related_searches: Optional[List[SerperRelatedSearch]] = Field(None, description="Related searches")
    api_error: Optional[str] = Field(None, description="API error message if request failed")
    api_status_code: Optional[int] = Field(None, description="API response status code if error")

    model_config = {
        "json_schema_extra": {
            "example": {
                "tool": "serper_web_search_tool",
                "query": "Apple Cider recipes",
                "results": [
                    {
                        "title": "Best Apple Cider Recipe",
                        "link": "https://example.com/apple-cider-recipe",
                        "snippet": "Learn how to make the perfect apple cider at home...",
                        "position": 1,
                        "result_type": "organic"
                    }
                ],
                "total_results": 1000
            }
        }
    }
