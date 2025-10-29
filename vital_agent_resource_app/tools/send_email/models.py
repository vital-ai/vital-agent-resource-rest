from pydantic import BaseModel, Field, EmailStr, validator
from typing import List, Optional, Dict, Any, Literal, Union
import re


class EmailInput(BaseModel):
    """Input model for Email tool"""
    to: Union[str, List[str]] = Field(..., description="Recipient email address(es)")
    subject: str = Field(..., description="Email subject line", max_length=998)
    text: Optional[str] = Field(None, description="Plain text email content")
    html: Optional[str] = Field(None, description="HTML email content")
    from_email: Optional[str] = Field(None, description="Sender email address (if different from default)")
    from_name: Optional[str] = Field(None, description="Sender name")
    cc: Optional[Union[str, List[str]]] = Field(None, description="CC recipient email address(es)")
    bcc: Optional[Union[str, List[str]]] = Field(None, description="BCC recipient email address(es)")
    reply_to: Optional[str] = Field(None, description="Reply-to email address")
    attachments: Optional[List[str]] = Field(None, description="List of attachment URLs (HTTPS only)", max_items=10)
    tags: Optional[List[str]] = Field(None, description="Email tags for tracking", max_items=3)
    custom_variables: Optional[Dict[str, str]] = Field(None, description="Custom variables for email personalization")
    template: Optional[str] = Field(None, description="Mailgun template name")
    template_variables: Optional[Dict[str, Any]] = Field(None, description="Template variables")
    
    @validator('to', 'cc', 'bcc', pre=True)
    def validate_email_addresses(cls, v):
        """Validate email addresses"""
        if v is None:
            return v
        
        email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
        
        if isinstance(v, str):
            emails = [email.strip() for email in v.split(',')]
        else:
            emails = v if isinstance(v, list) else [v]
        
        for email in emails:
            if not email_pattern.match(email.strip()):
                raise ValueError(f"Invalid email address: {email}")
        
        return emails if len(emails) > 1 else emails[0] if emails else None
    
    @validator('attachments')
    def validate_attachments(cls, v):
        """Validate attachment URLs are HTTPS"""
        if v is None:
            return v
        
        for url in v:
            if not url.startswith('https://'):
                raise ValueError(f"Attachment URLs must be HTTPS: {url}")
            if len(url) > 512:
                raise ValueError(f"Attachment URL too long (max 512 chars): {url}")
        
        return v
    
    @validator('text', 'html')
    def validate_content(cls, v, values):
        """Ensure at least one content type is provided"""
        if v is None and values.get('template') is None:
            # Check if we have text or html content
            has_text = values.get('text') is not None
            has_html = values.get('html') is not None
            if not has_text and not has_html:
                raise ValueError("Either 'text', 'html', or 'template' must be provided")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "to": "recipient@example.com",
                "subject": "Hello from Mailgun!",
                "text": "This is a test email sent via Mailgun API.",
                "html": "<h1>Hello!</h1><p>This is a test email sent via Mailgun API.</p>",
                "from_name": "MyApp",
                "tags": ["test", "api"]
            }
        }
    }


class EmailResult(BaseModel):
    """Email sending result"""
    id: str = Field(..., description="Mailgun message ID")
    message: str = Field(..., description="Success message from Mailgun")


class EmailError(BaseModel):
    """Email error details"""
    error: str = Field(..., description="Error message")
    code: Optional[int] = Field(None, description="HTTP error code")


class EmailOutput(BaseModel):
    """Output model for Email tool"""
    tool: Literal["send_email_tool"] = Field(..., description="Tool identifier")
    success: bool = Field(..., description="Whether the email was sent successfully")
    result: Optional[EmailResult] = Field(None, description="Email sending result if successful")
    error: Optional[EmailError] = Field(None, description="Error details if unsuccessful")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "tool": "send_email_tool",
                "success": True,
                "result": {
                    "id": "<20231201120000.1.ABCD1234@example.com>",
                    "message": "Queued. Thank you."
                }
            }
        }
    }
