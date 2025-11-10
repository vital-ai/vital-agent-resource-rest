#!/usr/bin/env python3

"""
Test script for Loop Message Tool using Loop Message API
"""

import sys
import os
import time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vital_agent_resource_app.tools.send_message.send_loop_message_tool import LoopMessageTool
from vital_agent_resource_app.tools.send_message.models import (
    LoopMessageSingleInput, LoopMessageGroupInput, LoopMessageAudioInput,
    LoopMessageReactionInput, LoopMessageStatusInput,
    LoopMessageSingleOutput, LoopMessageGroupOutput, LoopMessageStatusOutput
)
from vital_agent_resource_app.tools.tool_request import ToolRequest
from vital_agent_resource_app.tools.tool_name_enum import ToolName


def test_loop_message_tool_initialization():
    """Test LoopMessageTool initialization with config"""
    print("Testing LoopMessageTool initialization...")
    
    # Test with empty config
    config = {}
    tool = LoopMessageTool(config)
    assert tool.authorization_key is None
    assert tool.secret_key is None
    assert tool.base_url == "https://server.loopmessage.com/api/v1"
    print("✓ Empty config initialization works")
    
    # Test with API keys config
    config = {
        'authorization_key': 'test_auth_key_123',
        'secret_key': 'test_secret_key_456'
    }
    tool = LoopMessageTool(config)
    assert tool.authorization_key == 'test_auth_key_123'
    assert tool.secret_key == 'test_secret_key_456'
    assert tool.base_url == "https://server.loopmessage.com/api/v1"
    print("✓ API keys config initialization works")


def test_loop_message_single_input_validation():
    """Test LoopMessageSingleInput model validation"""
    print("\nTesting LoopMessageSingleInput validation...")
    
    # Get test phone from environment
    test_phone = os.getenv('TEST_PHONE_NUMBER')
    if not test_phone:
        print("❌ TEST_PHONE_NUMBER environment variable not set")
        return
    
    # Test valid message input
    valid_input = {
        "recipient": test_phone,
        "text": "Hello from Loop Message test!",
        "sender_name": "TestApp"
    }
    message_input = LoopMessageSingleInput(**valid_input)
    assert message_input.recipient == test_phone
    assert message_input.text == "Hello from Loop Message test!"
    assert message_input.sender_name == "TestApp"
    assert message_input.service == "imessage"  # default
    print("✓ Valid message input validation works")
    
    # Test with attachments and effects
    enhanced_input = {
        "recipient": test_phone,
        "text": "Hello with effects!",
        "sender_name": "TestApp",
        "attachments": ["https://example.com/image.jpg"],
        "effect": "balloons",
        "service": "imessage"
    }
    message_input = LoopMessageSingleInput(**enhanced_input)
    assert message_input.effect == "balloons"
    assert len(message_input.attachments) == 1
    print("✓ Enhanced message input validation works")
    
    # Test invalid effect
    try:
        invalid_effect = {
            "recipient": test_phone,
            "text": "Test message",
            "sender_name": "TestApp",
            "effect": "invalid_effect"
        }
        LoopMessageSingleInput(**invalid_effect)
        assert False, "Should have raised validation error"
    except Exception as e:
        print(f"✓ Invalid effect validation works: {type(e).__name__}")
    
    # Test invalid service
    try:
        invalid_service = {
            "recipient": test_phone,
            "text": "Test message",
            "sender_name": "TestApp",
            "service": "invalid_service"
        }
        LoopMessageSingleInput(**invalid_service)
        assert False, "Should have raised validation error"
    except Exception as e:
        print(f"✓ Invalid service validation works: {type(e).__name__}")


def test_loop_message_group_input_validation():
    """Test LoopMessageGroupInput model validation"""
    print("\nTesting LoopMessageGroupInput validation...")
    
    # Test valid group input
    valid_group_input = {
        "group": "2BC4FD6A-CE49-439F-81DF-E895C09CA49C",
        "text": "Hello group from test!",
        "sender_name": "TestApp"
    }
    group_input = LoopMessageGroupInput(**valid_group_input)
    assert group_input.group == "2BC4FD6A-CE49-439F-81DF-E895C09CA49C"
    assert group_input.text == "Hello group from test!"
    print("✓ Valid group input validation works")
    
    # Test empty group ID
    try:
        empty_group = {
            "group": "",
            "text": "Test message",
            "sender_name": "TestApp"
        }
        LoopMessageGroupInput(**empty_group)
        assert False, "Should have raised validation error"
    except Exception as e:
        print(f"✓ Empty group validation works: {type(e).__name__}")


def test_tool_examples():
    """Test tool examples"""
    print("\nTesting tool examples...")
    
    config = {
        'authorization_key': 'test_auth_key',
        'secret_key': 'test_secret_key'
    }
    tool = LoopMessageTool(config)
    examples = tool.get_examples()
    
    assert len(examples) == 5
    assert all('tool' in example for example in examples)
    assert all('tool_input' in example for example in examples)
    assert all(example['tool'] == 'loop_message_tool' for example in examples)
    print(f"✓ Tool provides {len(examples)} valid examples")


def test_tool_request_without_api_keys():
    """Test tool request handling without API keys"""
    print("\nTesting tool request without API keys...")
    
    # Get test phone from environment
    test_phone = os.getenv('TEST_PHONE_NUMBER')
    if not test_phone:
        print("❌ TEST_PHONE_NUMBER environment variable not set")
        return
    
    config = {}
    tool = LoopMessageTool(config)
    
    # Create a valid message input
    message_input = LoopMessageSingleInput(
        recipient=test_phone,
        text="Test message",
        sender_name="TestApp"
    )
    
    # Create tool request
    tool_request = ToolRequest(
        tool=ToolName.loop_message_tool,
        tool_input=message_input
    )
    
    # Handle request (should fail due to missing API keys)
    response = tool.handle_tool_request(tool_request)
    
    assert not response.success
    assert "API keys" in response.error_message
    print("✓ Tool correctly handles missing API keys")


def check_message_status(tool, message_id, max_attempts=3, poll_interval=5):
    """Check the status of a message with polling"""
    print(f"   Polling message status every {poll_interval} seconds (max {max_attempts} attempts)...")
    
    for attempt in range(1, max_attempts + 1):
        try:
            print(f"   📡 Attempt {attempt}/{max_attempts}...")
            
            # Create status input
            status_input = LoopMessageStatusInput(message_id=message_id)
            
            # Create tool request
            status_request = ToolRequest(
                tool=ToolName.loop_message_tool,
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
                    
                    # Show message details
                    recipient = result.get('recipient', 'N/A')
                    text = result.get('text', 'N/A')
                    sender_name = result.get('sender_name', 'N/A')
                    
                    print(f"      📱 Recipient: {recipient}")
                    print(f"      💬 Text: {text}")
                    print(f"      👤 Sender: {sender_name}")
                    
                    # If message is sent or failed, we have final status
                    if status in ['sent', 'failed', 'timeout']:
                        print(f"   ✅ Final status: {status}")
                        return True
                    else:
                        print(f"   ⏳ Message status: {status}")
            else:
                print(f"   ❌ Status check failed: {status_response.error_message}")
                
        except Exception as e:
            print(f"   ❌ Error checking status: {str(e)}")
        
        # Wait before next attempt (except on last attempt)
        if attempt < max_attempts:
            print(f"   ⏳ Waiting {poll_interval} seconds before next check...")
            time.sleep(poll_interval)
    
    print(f"   ⏰ Polling completed after {max_attempts} attempts.")
    return False


def test_send_actual_imessage():
    """Test sending actual iMessage to the test phone number"""
    print("\nTesting actual iMessage sending...")
    
    # Get test phone number from environment
    test_phone = os.getenv('TEST_PHONE_NUMBER')
    if not test_phone:
        print("❌ TEST_PHONE_NUMBER environment variable not set")
        return
    print(f"Sending iMessage to: {test_phone}")
    
    # Load config from actual config file
    from vital_agent_resource_app.utils.config_utils import ConfigUtils
    
    def get_tool_by_id(config_dict, tool_id):
        tools = config_dict.get('vital_agent_resource_app', {}).get('tools', [])
        for tool in tools:
            if tool.get('tool_id') == tool_id:
                return tool
        return {}
    
    config = ConfigUtils.load_config()
    loop_message_config = get_tool_by_id(config, 'loop_message_tool')
    
    if not loop_message_config.get('authorization_key') or not loop_message_config.get('secret_key'):
        print("❌ Loop Message API keys not found in app_config.yaml")
        print("Please configure authorization_key and secret_key in your app_config.yaml file")
        return
    
    # Initialize tool with real config
    tool = LoopMessageTool(loop_message_config)
    
    # Get sender name from config
    sender_name = loop_message_config.get('sender_name', 'Test')
    print(f"Using sender name: {sender_name}")
    
    # Create message input with configured sender name
    message_input = LoopMessageSingleInput(
        recipient=test_phone,
        text="🧪 Test iMessage from Loop Message Tool!\n\nThis is a test message sent from the Vital Agent Resource REST API using the Loop Message integration. The tool is working correctly! 🎉",
        sender_name=sender_name,
        effect="balloons",
        service="imessage"
    )
    
    # Create tool request
    tool_request = ToolRequest(
        tool=ToolName.loop_message_tool,
        tool_input=message_input
    )
    
    # Send the message
    print(f"Sending iMessage with balloons effect...")
    response = tool.handle_tool_request(tool_request)
    
    if response.success:
        print("✅ iMessage sent successfully!")
        print(f"Response: {response.tool_output}")
        
        # Parse the response to get message ID
        tool_output = response.tool_output
        if isinstance(tool_output, dict) and tool_output.get('success'):
            message_id = tool_output.get('message_id')
            recipient = tool_output.get('recipient', 'N/A')
            text = tool_output.get('text', 'N/A')
            
            print(f"\n📋 Message Details:")
            print(f"   Message ID: {message_id}")
            print(f"   Recipient: {recipient}")
            print(f"   Text: {text[:50]}..." if len(text) > 50 else f"   Text: {text}")
            
            # Check message status
            if message_id:
                print(f"\n🔍 Checking message status...")
                check_message_status(tool, message_id)
    else:
        print("❌ iMessage sending failed!")
        print(f"Error: {response.error_message}")


def test_send_sms_fallback():
    """Test sending SMS as fallback"""
    print("\nTesting SMS fallback...")
    
    # Get test phone number from environment
    test_phone = os.getenv('TEST_PHONE_NUMBER')
    if not test_phone:
        print("❌ TEST_PHONE_NUMBER environment variable not set")
        return
    print(f"Sending SMS to: {test_phone}")
    
    # Load config from actual config file
    from vital_agent_resource_app.utils.config_utils import ConfigUtils
    
    def get_tool_by_id(config_dict, tool_id):
        tools = config_dict.get('vital_agent_resource_app', {}).get('tools', [])
        for tool in tools:
            if tool.get('tool_id') == tool_id:
                return tool
        return {}
    
    config = ConfigUtils.load_config()
    loop_message_config = get_tool_by_id(config, 'loop_message_tool')
    
    if not loop_message_config.get('authorization_key') or not loop_message_config.get('secret_key'):
        print("❌ Loop Message API keys not found in app_config.yaml")
        return
    
    # Initialize tool with real config
    tool = LoopMessageTool(loop_message_config)
    
    # Get sender name from config
    sender_name = loop_message_config.get('sender_name', 'Test')
    print(f"Using sender name: {sender_name}")
    
    # Create SMS message input (no effects for SMS)
    message_input = LoopMessageSingleInput(
        recipient=test_phone,
        text="📱 Test SMS from Loop Message Tool! This is a fallback SMS message sent from the Vital Agent Resource REST API.",
        sender_name=sender_name,
        service="sms"  # Explicitly use SMS
    )
    
    # Create tool request
    tool_request = ToolRequest(
        tool=ToolName.loop_message_tool,
        tool_input=message_input
    )
    
    # Send the SMS
    print(f"Sending SMS message...")
    response = tool.handle_tool_request(tool_request)
    
    if response.success:
        print("✅ SMS sent successfully!")
        print(f"Response: {response.tool_output}")
    else:
        print("❌ SMS sending failed!")
        print(f"Error: {response.error_message}")


def main():
    """Run Loop Message tests"""
    print("Loop Message Tool - Live Test")
    print("=" * 50)
    
    try:
        # Run initialization tests
        test_loop_message_tool_initialization()
        
        # Run validation tests
        test_loop_message_single_input_validation()
        test_loop_message_group_input_validation()
        
        # Run tool tests
        test_tool_examples()
        test_tool_request_without_api_keys()
        
        # Run actual API tests
        test_send_actual_imessage()
        test_send_sms_fallback()
        
        print("\n🎉 All tests completed!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
