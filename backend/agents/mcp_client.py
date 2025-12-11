import os
import googlemaps
from typing import List, Optional
from pydantic import BaseModel, Field

# This is a simplified MCP Server implementation for Google Maps
# In a full MCP architecture, this would communicate via stdio/SSE.
# For this embedded app, we'll wrap it as a "Tool" that follows MCP schema concepts.

class PlaceSearchResult(BaseModel):
    name: str
    address: str
    rating: Optional[float] = None
    place_id: str
    types: List[str] = []

class GoogleMapsMCP:
    def __init__(self):
        api_key = os.getenv("GOOGLE_MAPS_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_MAPS_API_KEY not found in environment")
        self.client = googlemaps.Client(key=api_key)

    def search_places(self, query: str) -> List[PlaceSearchResult]:
        """
        Searches for places using the Google Maps Places API.
        """
        print(f"[MCP] Searching Google Maps for: {query}")
        # Using the Places API 'text_search'
        result = self.client.places(query=query)
        
        places = []
        if result.get('status') == 'OK':
            for result_item in result.get('results', [])[:3]: # Limit to top 3
                places.append(PlaceSearchResult(
                    name=result_item.get('name'),
                    address=result_item.get('formatted_address'),
                    rating=result_item.get('rating'),
                    place_id=result_item.get('place_id'),
                    types=result_item.get('types', [])
                ))
        return places

    def get_place_details(self, place_id: str):
        """
        Gets detailed info (reviews, etc) for a specific place.
        """
        return self.client.place(place_id=place_id)

# Schema exposure for the Agent
def get_mcp_tool_definition():
    return {
        "name": "google_maps_search",
        "description": "Search for real-world places, landmarks, and businesses to get their address, rating, and ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query (e.g., 'Eiffel Tower', 'Best coffee in Seattle')"
                }
            },
            "required": ["query"]
        }
    }
