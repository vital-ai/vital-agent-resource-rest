import requests


def main():
    print("Google Web Search Tool Test")

    url = "http://localhost:8008/tool"

    payload = {
        "tool": "google_web_search_tool",
        "tool_parameters": {

        }
    }

    response = requests.post(url, json=payload)

    print(f"Status Code: {response.status_code}")
    print("Response JSON:")
    print(response.json())


if __name__ == "__main__":
    main()



