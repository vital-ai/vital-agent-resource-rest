import requests


def main():
    print("Weather Tool Test")

    url = "http://localhost:8008/tool"

    payload = {
        "tool": "weather_tool",
        "tool_parameters": {
            "latitude": 40.7128,
            "longitude": -74.0060
        }
    }

    response = requests.post(url, json=payload)

    print(f"Status Code: {response.status_code}")
    print("Response JSON:")
    print(response.json())


if __name__ == "__main__":
    main()

