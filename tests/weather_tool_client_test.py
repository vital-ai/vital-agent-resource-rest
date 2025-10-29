import requests


def main():
    print("Weather Tool Test")

    url = "http://localhost:8008/tool"

    payload = {
        "tool": "weather_tool",
        "tool_input": {
            "latitude": 40.7128,
            "longitude": -74.0060,

            # "include_previous": True
            # "use_archive": True,
            # "archive_date": "2020-12-25"
        }
    }

    response = requests.post(url, json=payload)

    print(f"Status Code: {response.status_code}")
    print("Response JSON:")
    print(response.json())


if __name__ == "__main__":
    main()

