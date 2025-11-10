#!/usr/bin/env python3

"""
Test script for Loop Lookup Tool using Loop Lookup API
"""

import sys
import os
import time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vital_agent_resource_app.tools.send_message.loop_lookup_tool import LoopLookupTool
from vital_agent_resource_app.tools.send_message.models import (
    LoopLookupSingleInput, LoopLookupBulkInput, LoopLookupStatusInput,
    LoopLookupSingleOutput, LoopLookupBulkOutput, LoopLookupStatusOutput
)
from vital_agent_resource_app.tools.tool_request import ToolRequest
from vital_agent_resource_app.tools.tool_name_enum import ToolName


def test_loop_lookup_tool_initialization():
    """Test LoopLookupTool initialization with config"""
    print("Testing LoopLookupTool initialization...")
    
    # Test with empty config
    config = {}
    tool = LoopLookupTool(config)
    assert tool.api_key is None
    assert tool.base_url == "https://a.looplookup.com/api/v1"
    print("✓ Empty config initialization works")
    
    # Test with API key config
    config = {
        'api_key': 'test_api_key_123'
    }
    tool = LoopLookupTool(config)
    assert tool.api_key == 'test_api_key_123'
    assert tool.base_url == "https://a.looplookup.com/api/v1"
    print("✓ API key config initialization works")


def test_loop_lookup_single_input_validation():
    """Test LoopLookupSingleInput model validation"""
    print("\nTesting LoopLookupSingleInput validation...")
    
    # Get test phone from environment
    test_phone = os.getenv('TEST_PHONE_NUMBER')
    if not test_phone:
        print("❌ TEST_PHONE_NUMBER environment variable not set")
        return
    
    # Test valid phone number input
    valid_phone_input = {
        "contact": test_phone,
        "region": "US",
        "contact_details": True
    }
    lookup_input = LoopLookupSingleInput(**valid_phone_input)
    assert lookup_input.contact == test_phone
    assert lookup_input.region == "US"
    assert lookup_input.contact_details == True
    print("✓ Valid phone number input validation works")
    
    # Test valid email input
    valid_email_input = {
        "contact": "test@example.com",
        "region": "US"
    }
    lookup_input = LoopLookupSingleInput(**valid_email_input)
    assert lookup_input.contact == "test@example.com"
    assert lookup_input.region == "US"
    print("✓ Valid email input validation works")
    
    # Test invalid contact
    try:
        invalid_input = {
            "contact": "invalid-contact",
            "region": "US"
        }
        LoopLookupSingleInput(**invalid_input)
        assert False, "Should have raised validation error"
    except Exception as e:
        print(f"✓ Invalid contact validation works: {type(e).__name__}")
    
    # Test invalid region
    try:
        invalid_region = {
            "contact": test_phone,
            "region": "USA"  # Should be 2 letters
        }
        LoopLookupSingleInput(**invalid_region)
        assert False, "Should have raised validation error"
    except Exception as e:
        print(f"✓ Invalid region validation works: {type(e).__name__}")


def test_loop_lookup_bulk_input_validation():
    """Test LoopLookupBulkInput model validation"""
    print("\nTesting LoopLookupBulkInput validation...")
    
    # Get test phone from environment
    test_phone = os.getenv('TEST_PHONE_NUMBER')
    if not test_phone:
        print("❌ TEST_PHONE_NUMBER environment variable not set")
        return
    
    # Test valid bulk input
    valid_bulk_input = {
        "contacts": [test_phone, "test@example.com", "+1-555-123-4567"],
        "region": "US",
        "contact_details": False
    }
    bulk_input = LoopLookupBulkInput(**valid_bulk_input)
    assert len(bulk_input.contacts) == 3
    assert test_phone in bulk_input.contacts
    assert "test@example.com" in bulk_input.contacts
    print("✓ Valid bulk input validation works")
    
    # Test empty contacts list
    try:
        empty_contacts = {
            "contacts": [],
            "region": "US"
        }
        LoopLookupBulkInput(**empty_contacts)
        assert False, "Should have raised validation error"
    except Exception as e:
        print(f"✓ Empty contacts validation works: {type(e).__name__}")


def test_tool_examples():
    """Test tool examples"""
    print("\nTesting tool examples...")
    
    config = {'api_key': 'test_key'}
    tool = LoopLookupTool(config)
    examples = tool.get_examples()
    
    assert len(examples) == 3
    assert all('tool' in example for example in examples)
    assert all('tool_input' in example for example in examples)
    assert all(example['tool'] == 'loop_lookup_tool' for example in examples)
    print(f"✓ Tool provides {len(examples)} valid examples")


def check_lookup_status(tool, request_id, max_attempts=6, poll_interval=10):
    """Check the status of a lookup request with polling until results are found"""
    print(f"   Polling every {poll_interval} seconds (max {max_attempts} attempts)...")
    
    for attempt in range(1, max_attempts + 1):
        try:
            print(f"   📡 Attempt {attempt}/{max_attempts}...")
            
            # Create status input
            status_input = LoopLookupStatusInput(request_id=request_id)
            
            # Create tool request
            status_request = ToolRequest(
                tool=ToolName.loop_lookup_tool,
                tool_input=status_input
            )
            
            # Check status
            status_response = tool.handle_tool_request(status_request)
            
            if status_response.success:
                status_output = status_response.tool_output
                if isinstance(status_output, dict):
                    result = status_output.get('result', {})
                    status = result.get('status', 'N/A')
                    print(f"      Status: {status}")
                    
                    # Show classification results if available
                    result_v1 = result.get('result_v1')
                    if result_v1:
                        print(f"\n📊 Classification Results (Attempt {attempt}):")
                        
                        # Check if Apple services have been determined
                        apple_services = result_v1.get('apple_services', {}) if isinstance(result_v1, dict) else {}
                        imessage_status = apple_services.get('imessage', {}).get('status') if apple_services else None
                        facetime_status = apple_services.get('facetime', {}).get('status') if apple_services else None
                        
                        # If we have definitive results, show them and exit
                        if imessage_status and imessage_status != 'unknown':
                            print(f"   ✅ iMessage Status: {imessage_status}")
                            if facetime_status and facetime_status != 'unknown':
                                print(f"   ✅ FaceTime Status: {facetime_status}")
                            
                            # Show all results
                            print(f"\n📋 Complete Results:")
                            if isinstance(result_v1, dict):
                                for key, value in result_v1.items():
                                    print(f"   {key}: {value}")
                            return True  # Found results, exit polling
                        
                        elif facetime_status and facetime_status != 'unknown':
                            print(f"   ✅ FaceTime Status: {facetime_status}")
                            print(f"   ⏳ iMessage Status: still {imessage_status or 'unknown'}")
                        
                        else:
                            print(f"   ⏳ Apple Services: iMessage={imessage_status or 'unknown'}, FaceTime={facetime_status or 'unknown'}")
                            print(f"   📱 Carrier: {result_v1.get('carrier', {}).get('number_type', 'N/A')}")
                            print(f"   🌍 Location: {result_v1.get('country', {}).get('description', 'N/A')}")
                    
                    else:
                        print(f"      Results: Not yet available (status: {status})")
            else:
                print(f"   ❌ Status check failed: {status_response.error_message}")
                
        except Exception as e:
            print(f"   ❌ Error checking status: {str(e)}")
        
        # Wait before next attempt (except on last attempt)
        if attempt < max_attempts:
            print(f"   ⏳ Waiting {poll_interval} seconds before next check...")
            time.sleep(poll_interval)
    
    print(f"   ⏰ Polling completed after {max_attempts} attempts. Final status may still be processing.")
    return False


def test_tool_request_without_api_key():
    """Test tool request handling without API key"""
    print("\nTesting tool request without API key...")
    
    config = {}
    tool = LoopLookupTool(config)
    
    # Get test phone from environment
    test_phone = os.getenv('TEST_PHONE_NUMBER')
    if not test_phone:
        print("❌ TEST_PHONE_NUMBER environment variable not set")
        return
    
    # Create a valid lookup input
    lookup_input = LoopLookupSingleInput(
        contact=test_phone,
        region="US",
        contact_details=True
    )
    
    # Create tool request
    tool_request = ToolRequest(
        tool=ToolName.loop_lookup_tool,
        tool_input=lookup_input
    )
    
    # Handle request (should fail due to missing API key)
    response = tool.handle_tool_request(tool_request)
    
    assert not response.success
    assert "API key" in response.error_message
    print("✓ Tool correctly handles missing API key")


def test_actual_loop_lookup():
    """Test actual Loop Lookup for phone number from environment variable"""
    test_phone = os.getenv('TEST_PHONE_NUMBER')
    if not test_phone:
        print("❌ TEST_PHONE_NUMBER environment variable not set")
        return
    print(f"\nTesting actual Loop Lookup for {test_phone}...")
    
    # Load config from actual config file
    from vital_agent_resource_app.utils.config_utils import ConfigUtils
    
    def get_tool_by_id(config_dict, tool_id):
        tools = config_dict.get('vital_agent_resource_app', {}).get('tools', [])
        for tool in tools:
            if tool.get('tool_id') == tool_id:
                return tool
        return {}
    
    config = ConfigUtils.load_config()
    loop_lookup_config = get_tool_by_id(config, 'loop_lookup_tool')
    
    if not loop_lookup_config.get('api_key'):
        print("❌ Loop Lookup API key not found in app_config.yaml")
        print("Please configure api_key in your app_config.yaml file")
        return
    
    # Initialize tool with real config
    tool = LoopLookupTool(loop_lookup_config)
    
    # Create lookup input for the specified phone number (with country code)
    lookup_input = LoopLookupSingleInput(
        contact=test_phone,
        region="US",
        contact_details=True
    )
    
    # Create tool request
    tool_request = ToolRequest(
        tool=ToolName.loop_lookup_tool,
        tool_input=lookup_input
    )
    
    # Perform the lookup
    print(f"Looking up phone number: {test_phone}...")
    response = tool.handle_tool_request(tool_request)
    
    if response.success:
        print("✅ Loop Lookup completed successfully!")
        print(f"Response: {response.tool_output}")
        
        # Parse the response to show key information
        tool_output = response.tool_output
        if isinstance(tool_output, dict):
            if tool_output.get('success'):
                request_info = tool_output.get('request', {})
                request_id = request_info.get('request_id')
                print(f"\n📋 Lookup Details:")
                print(f"   Contact: {request_info.get('contact', 'N/A')}")
                print(f"   Request ID: {request_id}")
                print(f"   Tool: {tool_output.get('tool', 'N/A')}")
                
                # Check the status to see classification results
                if request_id:
                    print(f"\n🔍 Checking lookup status...")
                    check_lookup_status(tool, request_id)
            else:
                print(f"❌ Lookup failed: {tool_output}")
    else:
        print("❌ Loop Lookup failed!")
        print(f"Error: {response.error_message}")


def test_bulk_lookup():
    """Test bulk lookup with multiple contacts including phone from environment"""
    test_phone = os.getenv('TEST_PHONE_NUMBER')
    if not test_phone:
        print("❌ TEST_PHONE_NUMBER environment variable not set")
        return
    print(f"\nTesting bulk Loop Lookup with {test_phone}...")
    
    # Load config from actual config file
    from vital_agent_resource_app.utils.config_utils import ConfigUtils
    
    def get_tool_by_id(config_dict, tool_id):
        tools = config_dict.get('vital_agent_resource_app', {}).get('tools', [])
        for tool in tools:
            if tool.get('tool_id') == tool_id:
                return tool
        return {}
    
    config = ConfigUtils.load_config()
    loop_lookup_config = get_tool_by_id(config, 'loop_lookup_tool')
    
    if not loop_lookup_config.get('api_key'):
        print("❌ Loop Lookup API key not found in app_config.yaml")
        return
    
    # Initialize tool with real config
    tool = LoopLookupTool(loop_lookup_config)
    
    # Create bulk lookup input
    bulk_input = LoopLookupBulkInput(
        contacts=[test_phone, "test@example.com", "+1-555-123-4567"],
        region="US",
        contact_details=True
    )
    
    # Create tool request
    tool_request = ToolRequest(
        tool=ToolName.loop_lookup_tool,
        tool_input=bulk_input
    )
    
    # Perform the bulk lookup
    print(f"Performing bulk lookup for 3 contacts...")
    response = tool.handle_tool_request(tool_request)
    
    if response.success:
        print("✅ Bulk Loop Lookup completed successfully!")
        print(f"Response: {response.tool_output}")
    else:
        print("❌ Bulk Loop Lookup failed!")
        print(f"Error: {response.error_message}")


def main():
    """Run Loop Lookup tests"""
    print("Loop Lookup Tool - Live Test")
    print("=" * 50)
    
    try:
        # Run initialization tests
        test_loop_lookup_tool_initialization()
        
        # Run validation tests
        test_loop_lookup_single_input_validation()
        test_loop_lookup_bulk_input_validation()
        
        # Run tool tests
        test_tool_examples()
        test_tool_request_without_api_key()
        
        # Run actual API tests
        test_actual_loop_lookup()
        test_bulk_lookup()
        
        print("\n🎉 All tests completed!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
