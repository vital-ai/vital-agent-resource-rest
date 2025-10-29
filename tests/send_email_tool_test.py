#!/usr/bin/env python3

"""
Test script for Send Email Tool using Mailgun API
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vital_agent_resource_app.tools.send_email.send_email_tool import SendEmailTool
from vital_agent_resource_app.tools.send_email.models import EmailInput, EmailOutput
from vital_agent_resource_app.tools.tool_request import ToolRequest
from vital_agent_resource_app.tools.tool_name_enum import ToolName


def test_send_email_tool_initialization():
    """Test SendEmailTool initialization with config"""
    print("Testing SendEmailTool initialization...")
    
    # Test with empty config
    config = {}
    tool = SendEmailTool(config)
    assert tool.api_key is None
    assert tool.domain is None
    assert tool.client is None
    print("✓ Empty config initialization works")
    
    # Test with partial config
    config = {
        'api_key': 'test_key',
        'domain': 'test.mailgun.org'
    }
    tool = SendEmailTool(config)
    assert tool.api_key == 'test_key'
    assert tool.domain == 'test.mailgun.org'
    assert tool.client is not None
    print("✓ Partial config initialization works")
    
    # Test with full config
    config = {
        'api_key': 'test_key',
        'domain': 'test.mailgun.org',
        'from_email': 'test@test.mailgun.org'
    }
    tool = SendEmailTool(config)
    assert tool.api_key == 'test_key'
    assert tool.domain == 'test.mailgun.org'
    assert tool.default_from_email == 'test@test.mailgun.org'
    print("✓ Full config initialization works")


def test_email_input_validation():
    """Test EmailInput model validation"""
    print("\nTesting EmailInput validation...")
    
    # Test valid input
    valid_input = {
        "to": "test@example.com",
        "subject": "Test Subject",
        "text": "Test message content"
    }
    email_input = EmailInput(**valid_input)
    assert email_input.to == "test@example.com"
    assert email_input.subject == "Test Subject"
    assert email_input.text == "Test message content"
    print("✓ Valid input validation works")
    
    # Test multiple recipients
    multi_input = {
        "to": ["user1@example.com", "user2@example.com"],
        "subject": "Multi Recipient Test",
        "html": "<h1>Test</h1>"
    }
    email_input = EmailInput(**multi_input)
    assert isinstance(email_input.to, list)
    assert len(email_input.to) == 2
    print("✓ Multiple recipients validation works")
    
    # Test invalid email
    try:
        invalid_input = {
            "to": "invalid-email",
            "subject": "Test",
            "text": "Test"
        }
        EmailInput(**invalid_input)
        assert False, "Should have raised validation error"
    except Exception as e:
        print(f"✓ Invalid email validation works: {type(e).__name__}")
    
    # Test missing content
    try:
        missing_content = {
            "to": "test@example.com",
            "subject": "Test"
        }
        EmailInput(**missing_content)
        assert False, "Should have raised validation error"
    except Exception as e:
        print(f"✓ Missing content validation works: {type(e).__name__}")


def test_tool_examples():
    """Test tool examples"""
    print("\nTesting tool examples...")
    
    config = {
        'api_key': 'test_key',
        'domain': 'test.mailgun.org'
    }
    tool = SendEmailTool(config)
    examples = tool.get_examples()
    
    assert len(examples) == 3
    assert all('tool' in example for example in examples)
    assert all('tool_input' in example for example in examples)
    assert all(example['tool'] == 'send_email_tool' for example in examples)
    print(f"✓ Tool provides {len(examples)} valid examples")


def test_tool_request_without_api_key():
    """Test tool request handling without API key"""
    print("\nTesting tool request without API key...")
    
    config = {}
    tool = SendEmailTool(config)
    
    # Create a valid email input
    email_input = EmailInput(
        to="test@example.com",
        subject="Test Subject",
        text="Test message"
    )
    
    # Create tool request
    tool_request = ToolRequest(
        tool=ToolName.send_email_tool,
        tool_input=email_input
    )
    
    # Handle request (should fail due to missing API key)
    response = tool.handle_tool_request(tool_request)
    
    assert not response.success
    assert "API key" in response.error_message
    print("✓ Tool correctly handles missing API key")


def test_tool_request_without_domain():
    """Test tool request handling without domain"""
    print("\nTesting tool request without domain...")
    
    config = {'api_key': 'test_key'}
    tool = SendEmailTool(config)
    
    # Create a valid email input
    email_input = EmailInput(
        to="test@example.com",
        subject="Test Subject",
        text="Test message"
    )
    
    # Create tool request
    tool_request = ToolRequest(
        tool=ToolName.send_email_tool,
        tool_input=email_input
    )
    
    # Handle request (should fail due to missing domain)
    response = tool.handle_tool_request(tool_request)
    
    assert not response.success
    assert "domain" in response.error_message
    print("✓ Tool correctly handles missing domain")


def test_send_actual_email():
    """Test sending actual email to marc@hadfield.org"""
    print("Testing actual email sending to marc@hadfield.org...")
    
    # Load config from actual config file
    from vital_agent_resource_app.utils.config_utils import ConfigUtils
    
    def get_tool_by_id(config_dict, tool_id):
        tools = config_dict.get('vital_agent_resource_app', {}).get('tools', [])
        for tool in tools:
            if tool.get('tool_id') == tool_id:
                return tool
        return {}
    
    config = ConfigUtils.load_config()
    send_email_config = get_tool_by_id(config, 'send_email_tool')
    
    if not send_email_config.get('api_key') or not send_email_config.get('domain'):
        print("❌ Mailgun configuration not found in app_config.yaml")
        print("Please configure api_key and domain in your app_config.yaml file")
        return
    
    # Initialize tool with real config
    tool = SendEmailTool(send_email_config)
    
    # Create email input
    email_input = EmailInput(
        to="marc@hadfield.org",
        subject="Test Email from Vital Agent Resource REST API",
        text="This is a test email sent from the Send Email Tool using Mailgun API.\n\nThe tool is working correctly!",
        html="<h1>Test Email</h1><p>This is a test email sent from the <strong>Send Email Tool</strong> using Mailgun API.</p><p>The tool is working correctly!</p>"
    )
    
    # Create tool request
    tool_request = ToolRequest(
        tool=ToolName.send_email_tool,
        tool_input=email_input
    )
    
    # Send the email
    print(f"Sending email to marc@hadfield.org...")
    response = tool.handle_tool_request(tool_request)
    
    if response.success:
        print("✅ Email sent successfully!")
        print(f"Response: {response.tool_output}")
    else:
        print("❌ Email sending failed!")
        print(f"Error: {response.error_message}")


def main():
    """Run email sending test"""
    print("Send Email Tool - Live Test")
    print("=" * 50)
    
    try:
        test_send_actual_email()
        
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
