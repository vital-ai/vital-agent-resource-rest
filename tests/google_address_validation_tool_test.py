import requests
import sys
import os


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    print("Google Address Validation Tool Test")

    url = "http://localhost:8008/tool"

    payload = {
        "tool": "google_address_validation_tool",
        "tool_input": {
            "address": "475 st marks broklyn 7a"
        }
    }

    response = requests.post(url, json=payload)

    print(f"Status Code: {response.status_code}")
    print("Response JSON:")
    print(response.json())


if __name__ == "__main__":
    main()
