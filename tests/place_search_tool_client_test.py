from vital_agent_resource_app.tools.place_search.place_search_tool import PlaceSearchTool
import requests


def main():
    print("Place Search Tool Test")

    url = "http://localhost:8008/tool"

    payload = {
        "tool": "place_search_tool",
        "tool_parameters": {
            "place_search_string": "Philly"
        }
    }

    response = requests.post(url, json=payload)

    print(f"Status Code: {response.status_code}")
    print("Response JSON:")
    print(response.json())


if __name__ == "__main__":
    main()
