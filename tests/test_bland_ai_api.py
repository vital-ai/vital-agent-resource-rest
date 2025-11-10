#!/usr/bin/env python3
"""
Standalone test script for bland.ai API integration.
This script initiates a voice call using the bland.ai API.
"""

import os
import json
import requests
from dotenv import load_dotenv

def test_bland_ai_call():
    """Test initiating a call with the bland.ai API"""
    
    # Load API key and phone number from .env file
    load_dotenv()
    api_key = os.getenv("BLAND_API_KEY")
    test_phone = os.getenv("TEST_PHONE_NUMBER")
    
    if not api_key:
        print("Error: BLAND_API_KEY not found in .env file")
        return
    
    if not test_phone:
        print("Error: TEST_PHONE_NUMBER not found in .env file")
        return
    
    # API endpoint
    url = "https://api.bland.ai/v1/calls"
    
    # Headers
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # Request payload
    payload = {
        "phone_number": test_phone,  # Phone number from environment
        # The task field contains the instructions for the AI agent
        "task": """You are Sarah from Customer Support at Acme Inc. calling to collect delivery information for order #ABC123. Use a friendly, professional tone.

1. Greet the customer by name and introduce yourself.
2. Verify you're speaking with the right person.
3. Explain you're calling to collect delivery information for their recent order.
4. Collect the following information:
   - Preferred delivery date (variable: delivery_date)
   - Best time of day for delivery (variable: delivery_time_preference)
   - Special delivery instructions if any (variable: delivery_special_instructions)
   - Alternative phone number, if different from this one (variable: alternative_contact)
5. Confirm all collected information with the customer.
6. Thank them for their time and explain when they can expect delivery.
7. End the call politely.""",
        "voice": "paige",
        "model": "base",
        "record": True,
        "wait_for_greeting": False,
        "response_delay": 100,
        "from_number": "+18885144534",  # Using a bland.ai default number
        "language": "en-US",
        "metadata": {
            "order_id": "ABC123",
            "customer_name": "Test Customer",
            "reference_id": "test-call-20250629"
        },
        "reduce_latency": True,
        "wait_for_greeting": False,
        # Custom tool with schema - required for structured data in post-call webhook
        # The URL is required by the API but won't actually be called during the conversation
        # The structured data will be available in the post-call webhook based on this schema
        "tools": [
            {
                "name": "CollectDeliveryInfo",
                "description": "Extract and save delivery information provided by the customer",
                "speech": "I'm updating your delivery preferences now.",
                "url": "https://example.com/api/delivery-info", # Required by API but not actually called
                "method": "POST", # Required by API but not actually called
                "input_schema": {
                    "example": {
                        "delivery_date": "2025-07-05",
                        "delivery_time_preference": "afternoon",
                        "delivery_special_instructions": "Please leave package at the back door",
                        "alternative_contact": "+15559876543"
                    },
                    "type": "object",
                    "properties": {
                        "delivery_date": {
                            "type": "string",
                            "description": "Preferred date for delivery in YYYY-MM-DD format"
                        },
                        "delivery_time_preference": {
                            "type": "string",
                            "description": "Preferred time of day (morning, afternoon, evening)"
                        },
                        "delivery_special_instructions": {
                            "type": "string",
                            "description": "Any special instructions for the delivery"
                        },
                        "alternative_contact": {
                            "type": "string",
                            "description": "Alternative phone number for contact"
                        }
                    },
                    "required": ["delivery_date", "delivery_time_preference"]
                }
            }
        ]
    }
    
    try:
        # Make the API call
        response = requests.post(url, headers=headers, json=payload)
        
        # Print response details
        print(f"Status code: {response.status_code}")
        print(f"Response body: {json.dumps(response.json(), indent=2)}")
        
        # Check if call was successfully queued
        if response.status_code == 200 and response.json().get("status") == "success":
            call_id = response.json().get("call_id")
            print(f"\nCall successfully queued with call_id: {call_id}")
            print(f"You can check the status at: https://app.bland.ai/dashboard/call/{call_id}")
        else:
            print("\nFailed to queue call")
    
    except Exception as e:
        print(f"Error making API request: {str(e)}")

if __name__ == "__main__":
    test_bland_ai_call()
