from vital_agent_resource_app.tools.abstract_tool import AbstractTool
from vital_agent_resource_app.tools.tool_request import ToolRequest
from vital_agent_resource_app.tools.tool_response import ToolResponse
from vital_agent_resource_app.tools.send_email.models import (
    EmailInput, EmailOutput, EmailResult, EmailError
)
from typing import List, Dict, Any, Union
from mailgun.client import Client
import time
import logging

logger = logging.getLogger(__name__)


class SendEmailTool(AbstractTool):
    """
    Send Email Tool using Mailgun API for sending emails with support for:
    - Plain text and HTML emails
    - Multiple recipients (to, cc, bcc)
    - File attachments via URLs
    - Email templates
    - Custom variables and tags
    - Reply-to addresses
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.api_key = config.get('api_key') if config else None
        self.domain = config.get('domain') if config else None
        self.default_from_email = config.get('from_email') if config else None
        
        if not self.api_key:
            logger.warning("Mailgun API key not configured")
        if not self.domain:
            logger.warning("Mailgun domain not configured")
        
        # Initialize Mailgun client
        if self.api_key:
            self.client = Client(auth=("api", self.api_key))
        else:
            self.client = None

    def get_examples(self) -> List[Dict[str, Any]]:
        """Return list of example requests for Send Email tool"""
        return [
            {
                "tool": "send_email_tool",
                "tool_input": {
                    "to": "recipient@example.com",
                    "subject": "Hello from Mailgun!",
                    "text": "This is a test email sent via Mailgun API.",
                    "from_name": "MyApp"
                }
            },
            {
                "tool": "send_email_tool",
                "tool_input": {
                    "to": ["user1@example.com", "user2@example.com"],
                    "subject": "Newsletter Update",
                    "html": "<h1>Newsletter</h1><p>Check out our latest updates!</p>",
                    "attachments": ["https://example.com/newsletter.pdf"],
                    "tags": ["newsletter", "marketing"]
                }
            },
            {
                "tool": "send_email_tool",
                "tool_input": {
                    "to": "customer@example.com",
                    "subject": "Welcome {{name}}!",
                    "template": "welcome_template",
                    "template_variables": {
                        "name": "John Doe",
                        "company": "Acme Corp"
                    }
                }
            }
        ]

    def handle_tool_request(self, tool_request: ToolRequest) -> ToolResponse:
        start_time = time.time()
        
        # Validate configuration
        if not self.client:
            return self._create_error_response(
                "Mailgun client not initialized - check API key configuration", 
                start_time
            )
        
        if not self.domain:
            return self._create_error_response(
                "Mailgun domain not configured", 
                start_time
            )
        
        # Extract parameters from validated tool input
        validated_input = tool_request.tool_input
        
        try:
            # Prepare email data
            email_data = self._prepare_email_data(validated_input)
            
            # Send email via Mailgun
            response = self.client.messages.create(data=email_data, domain=self.domain)
            
            logger.info(f"Email sent successfully: {response.status_code}")
            
            if response.status_code == 200:
                response_json = response.json()
                
                # Create structured output
                email_result = EmailResult(
                    id=response_json.get('id', ''),
                    message=response_json.get('message', 'Email sent successfully')
                )
                
                tool_output = EmailOutput(
                    tool="send_email_tool",
                    success=True,
                    result=email_result
                )
                
                return self._create_success_response(tool_output.dict(), start_time)
            else:
                error_msg = f"Mailgun API error: {response.status_code}"
                try:
                    error_details = response.json()
                    error_msg += f" - {error_details.get('message', 'Unknown error')}"
                except:
                    pass
                
                email_error = EmailError(
                    error=error_msg,
                    code=response.status_code
                )
                
                tool_output = EmailOutput(
                    tool="send_email_tool",
                    success=False,
                    error=email_error
                )
                
                return self._create_success_response(tool_output.dict(), start_time)
                
        except Exception as e:
            logger.error(f"Error sending email: {str(e)}")
            
            email_error = EmailError(
                error=f"Email sending failed: {str(e)}"
            )
            
            tool_output = EmailOutput(
                tool="send_email_tool",
                success=False,
                error=email_error
            )
            
            return self._create_success_response(tool_output.dict(), start_time)
    
    def _prepare_email_data(self, validated_input: EmailInput) -> Dict[str, Any]:
        """Prepare email data for Mailgun API"""
        email_data = {}
        
        # Recipients
        email_data['to'] = self._format_recipients(validated_input.to)
        
        if validated_input.cc:
            email_data['cc'] = self._format_recipients(validated_input.cc)
        
        if validated_input.bcc:
            email_data['bcc'] = self._format_recipients(validated_input.bcc)
        
        # Subject
        email_data['subject'] = validated_input.subject
        
        # From address
        from_email = validated_input.from_email or self.default_from_email
        if not from_email:
            raise ValueError("No from email address configured")
        
        if validated_input.from_name:
            email_data['from'] = f"{validated_input.from_name} <{from_email}>"
        else:
            email_data['from'] = from_email
        
        # Reply-to
        if validated_input.reply_to:
            email_data['h:Reply-To'] = validated_input.reply_to
        
        # Content
        if validated_input.template:
            email_data['template'] = validated_input.template
            if validated_input.template_variables:
                for key, value in validated_input.template_variables.items():
                    email_data[f'v:{key}'] = str(value)
        else:
            if validated_input.text:
                email_data['text'] = validated_input.text
            if validated_input.html:
                email_data['html'] = validated_input.html
        
        # Tags
        if validated_input.tags:
            for tag in validated_input.tags:
                email_data.setdefault('o:tag', []).append(tag)
        
        # Custom variables
        if validated_input.custom_variables:
            for key, value in validated_input.custom_variables.items():
                email_data[f'v:{key}'] = str(value)
        
        # Attachments (Mailgun handles URLs differently - this is a simplified approach)
        if validated_input.attachments:
            logger.warning("Attachment URLs provided - Mailgun requires file uploads, not URLs")
            # Note: Mailgun typically requires file uploads, not URLs
            # This would need additional implementation to download and upload files
        
        return email_data
    
    def _format_recipients(self, recipients: Union[str, List[str]]) -> str:
        """Format recipients for Mailgun API"""
        if isinstance(recipients, list):
            return ', '.join(recipients)
        return recipients