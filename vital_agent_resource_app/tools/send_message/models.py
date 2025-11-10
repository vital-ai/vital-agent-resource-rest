from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any, Literal, Union
import re


class LoopLookupSingleInput(BaseModel):
    """Input model for single contact lookup"""
    contact: str = Field(..., description="Phone number or email address")
    region: Optional[str] = Field(None, description="ISO-2 country code (US, GB, CA, etc.)", max_length=2)
    contact_details: Optional[bool] = Field(False, description="Include additional contact information")

    @validator('contact')
    def validate_contact(cls, v):
        """Validate that contact is either a valid phone number or email"""
        if not v or not v.strip():
            raise ValueError("Contact cannot be empty")
        
        v = v.strip()
        
        # Check if it's an email (basic validation)
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if '@' in v:
            if not re.match(email_pattern, v):
                raise ValueError("Invalid email format")
            return v.lower()  # Normalize email to lowercase
        
        # Check if it's a phone number (remove formatting for validation)
        phone_clean = re.sub(r'[^\d+]', '', v)
        if not phone_clean:
            raise ValueError("Contact must be a valid phone number or email")
        
        # Basic phone number validation (must have at least 7 digits)
        digits_only = re.sub(r'[^\d]', '', phone_clean)
        if len(digits_only) < 7:
            raise ValueError("Phone number must have at least 7 digits")
        
        return v

    @validator('region')
    def validate_region(cls, v):
        """Validate region is a valid ISO-2 country code format"""
        if v is not None:
            v = v.upper().strip()
            if len(v) != 2 or not v.isalpha():
                raise ValueError("Region must be a 2-letter ISO country code")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "contact": "+1 (323) 123-4567",
                "region": "US",
                "contact_details": True
            }
        }
    }


class LoopLookupBulkInput(BaseModel):
    """Input model for bulk contact lookup"""
    contacts: List[str] = Field(..., description="Array of phone numbers or email addresses", min_items=1, max_items=3000)
    region: Optional[str] = Field(None, description="ISO-2 country code (US, GB, CA, etc.)", max_length=2)
    contact_details: Optional[bool] = Field(False, description="Include additional contact information")

    @validator('contacts')
    def validate_contacts(cls, v):
        """Validate each contact in the list"""
        if not v:
            raise ValueError("Contacts list cannot be empty")
        
        validated_contacts = []
        for i, contact in enumerate(v):
            if not contact or not contact.strip():
                raise ValueError(f"Contact at index {i} cannot be empty")
            
            contact = contact.strip()
            
            # Check if it's an email
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if '@' in contact:
                if not re.match(email_pattern, contact):
                    raise ValueError(f"Invalid email format at index {i}: {contact}")
                validated_contacts.append(contact.lower())
                continue
            
            # Check if it's a phone number
            phone_clean = re.sub(r'[^\d+]', '', contact)
            if not phone_clean:
                raise ValueError(f"Contact at index {i} must be a valid phone number or email: {contact}")
            
            digits_only = re.sub(r'[^\d]', '', phone_clean)
            if len(digits_only) < 7:
                raise ValueError(f"Phone number at index {i} must have at least 7 digits: {contact}")
            
            validated_contacts.append(contact)
        
        return validated_contacts

    @validator('region')
    def validate_region(cls, v):
        """Validate region is a valid ISO-2 country code format"""
        if v is not None:
            v = v.upper().strip()
            if len(v) != 2 or not v.isalpha():
                raise ValueError("Region must be a 2-letter ISO country code")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "contacts": ["+13231112233", "steve@mac.com", "1(787)111-22-33"],
                "region": "US",
                "contact_details": False
            }
        }
    }


class LoopLookupStatusInput(BaseModel):
    """Input model for status check"""
    request_id: str = Field(..., description="Request ID to check status for")

    @validator('request_id')
    def validate_request_id(cls, v):
        """Validate request ID is not empty"""
        if not v or not v.strip():
            raise ValueError("Request ID cannot be empty")
        return v.strip()

    model_config = {
        "json_schema_extra": {
            "example": {
                "request_id": "2BC4FD6A-CE49-439F-81DF-E895C09CA49C"
            }
        }
    }


# Union type for all input models to support dynamic input validation
LoopLookupInput = Union[LoopLookupSingleInput, LoopLookupBulkInput, LoopLookupStatusInput]


class LoopLookupRequest(BaseModel):
    """Individual lookup request result"""
    contact: str = Field(..., description="Normalized contact (phone/email)")
    request_id: str = Field(..., description="Unique request identifier")

    model_config = {
        "json_schema_extra": {
            "example": {
                "contact": "+13231112233",
                "request_id": "2BC4FD6A-CE49-439F-81DF-E895C09CA49C"
            }
        }
    }


# ========================================
# Loop Lookup Result Models (Based on Official API Documentation)
# ========================================

class AppleServiceLinks(BaseModel):
    """Apple service deep links"""
    facetime_audio: Optional[str] = Field(None, description="FaceTime audio deep link")
    facetime: Optional[str] = Field(None, description="FaceTime video deep link")
    tel: Optional[str] = Field(None, description="Phone call deep link")
    imessage: Optional[str] = Field(None, description="iMessage deep link")
    sms: Optional[str] = Field(None, description="SMS deep link")

    model_config = {
        "json_schema_extra": {
            "example": {
                "facetime_audio": "facetime-audio://+15551234567",
                "facetime": "facetime://+15551234567",
                "tel": "tel://+15551234567",
                "imessage": "imessage://+15551234567",
                "sms": "sms://+15551234567"
            }
        }
    }


class AppleServiceStatus(BaseModel):
    """Apple service availability status"""
    status: str = Field(..., description="Service status: available, unavailable, unknown")
    date: Optional[str] = Field(None, description="Last known date of data (YYYY-MM-DD)")
    links: Optional[AppleServiceLinks] = Field(None, description="Deep links for the service")

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "available",
                "date": "2025-11-10",
                "links": {
                    "imessage": "imessage://+15551234567",
                    "sms": "sms://+15551234567"
                }
            }
        }
    }


class AppleServices(BaseModel):
    """Apple services availability"""
    facetime: Optional[AppleServiceStatus] = Field(None, description="FaceTime availability")
    imessage: Optional[AppleServiceStatus] = Field(None, description="iMessage availability")

    model_config = {
        "json_schema_extra": {
            "example": {
                "facetime": {
                    "status": "available",
                    "date": "2025-11-10",
                    "links": {
                        "facetime_audio": "facetime-audio://+15551234567",
                        "facetime": "facetime://+15551234567",
                        "tel": "tel://+15551234567"
                    }
                },
                "imessage": {
                    "status": "available", 
                    "date": "2025-11-10",
                    "links": {
                        "imessage": "imessage://+15551234567",
                        "sms": "sms://+15551234567"
                    }
                }
            }
        }
    }


class CarrierInfo(BaseModel):
    """Carrier information"""
    carrier: Optional[str] = Field(None, description="Carrier name (e.g., Verizon)")
    number_type: Optional[str] = Field(None, description="Number type: mobile, fixed_line, fixed_line_or_mobile")

    model_config = {
        "json_schema_extra": {
            "example": {
                "carrier": "Verizon",
                "number_type": "fixed_line_or_mobile"
            }
        }
    }


class CountryInfo(BaseModel):
    """Country information"""
    flag: Optional[str] = Field(None, description="Country flag emoji")
    iso2: Optional[str] = Field(None, description="ISO2 country code")
    iso3: Optional[str] = Field(None, description="ISO3 country code")
    name: Optional[str] = Field(None, description="Country name")
    description: Optional[str] = Field(None, description="Region/state description")
    numeric: Optional[int] = Field(None, description="Numeric country code")

    model_config = {
        "json_schema_extra": {
            "example": {
                "flag": "🇺🇸",
                "iso2": "US",
                "iso3": "USA",
                "name": "United States",
                "description": "New York",
                "numeric": 840
            }
        }
    }


class PhoneFormat(BaseModel):
    """Phone number formatting"""
    e164: Optional[str] = Field(None, description="E164 format (+13231112233)")
    international: Optional[str] = Field(None, description="International format (+1 323-111-2233)")
    national: Optional[str] = Field(None, description="National format ((323) 111-2233)")
    out_of_usa: Optional[str] = Field(None, description="Out of USA format (1 (323) 111-2233)")
    rfc3966: Optional[str] = Field(None, description="RFC3966 format (tel:+1-323-111-2233)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "e164": "+15551234567",
                "international": "+1 555-123-4567",
                "national": "(555) 123-4567",
                "out_of_usa": "+1 555-123-4567",
                "rfc3966": "tel:+1-555-123-4567"
            }
        }
    }


class LookupResultData(BaseModel):
    """Structured lookup result data based on official API documentation"""
    apple_services: Optional[AppleServices] = Field(None, description="Apple services availability")
    carrier: Optional[CarrierInfo] = Field(None, description="Carrier information")
    country: Optional[CountryInfo] = Field(None, description="Country information")
    currencies: Optional[List[str]] = Field(None, description="Supported currencies")
    format: Optional[PhoneFormat] = Field(None, description="Phone number formats")
    time_zones: Optional[List[str]] = Field(None, description="Time zones")

    model_config = {
        "json_schema_extra": {
            "example": {
                "apple_services": {
                    "imessage": {"status": "available", "date": "2025-11-10"},
                    "facetime": {"status": "available", "date": "2025-11-10"}
                },
                "carrier": {"number_type": "fixed_line_or_mobile"},
                "country": {"description": "New York", "flag": "🇺🇸", "iso2": "US"},
                "currencies": ["USD", "USN"],
                "format": {"e164": "+15551234567", "national": "(555) 123-4567"},
                "time_zones": ["America/New_York"]
            }
        }
    }


class LoopLookupResult(BaseModel):
    """Lookup result data"""
    request_id: str = Field(..., description="Request identifier")
    status: str = Field(..., description="Request status (queued, processing, completed, canceled)")
    contact: Optional[str] = Field(None, description="Contact that was looked up")
    result_v1: Optional[LookupResultData] = Field(None, description="Structured lookup results when completed")

    model_config = {
        "json_schema_extra": {
            "example": {
                "request_id": "2BC4FD6A-CE49-439F-81DF-E895C09CA49C",
                "status": "completed",
                "contact": "+15551234567",
                "result_v1": {
                    "apple_services": {
                        "imessage": {"status": "available", "date": "2025-11-10"},
                        "facetime": {"status": "available", "date": "2025-11-10"}
                    },
                    "carrier": {"number_type": "fixed_line_or_mobile"},
                    "country": {"description": "New York", "flag": "🇺🇸", "iso2": "US"},
                    "format": {"e164": "+15551234567", "national": "(555) 123-4567"},
                    "time_zones": ["America/New_York"]
                }
            }
        }
    }


class LoopLookupSingleOutput(BaseModel):
    """Output model for single lookup"""
    tool: Literal["loop_lookup_tool"] = Field(..., description="Tool identifier")
    success: bool = Field(..., description="Request success status")
    request: LoopLookupRequest = Field(..., description="Request details")

    model_config = {
        "json_schema_extra": {
            "example": {
                "tool": "loop_lookup_tool",
                "success": True,
                "request": {
                    "contact": "+13231112233",
                    "request_id": "2BC4FD6A-CE49-439F-81DF-E895C09CA49C"
                }
            }
        }
    }


class LoopLookupBulkOutput(BaseModel):
    """Output model for bulk lookup"""
    tool: Literal["loop_lookup_tool"] = Field(..., description="Tool identifier")
    success: bool = Field(..., description="Request success status")
    requests: List[LoopLookupRequest] = Field(..., description="List of request details")

    model_config = {
        "json_schema_extra": {
            "example": {
                "tool": "loop_lookup_tool",
                "success": True,
                "requests": [
                    {
                        "contact": "+13231112233",
                        "request_id": "2BC4FD6A-CE49-439F-81DF-E895C09CA49C"
                    },
                    {
                        "contact": "steve@mac.com",
                        "request_id": "3CD5GE7B-DF5A-540G-92EG-F906D10DB50D"
                    }
                ]
            }
        }
    }


class LoopLookupStatusOutput(BaseModel):
    """Output model for status check"""
    tool: Literal["loop_lookup_tool"] = Field(..., description="Tool identifier")
    result: LoopLookupResult = Field(..., description="Status and result data")

    model_config = {
        "json_schema_extra": {
            "example": {
                "tool": "loop_lookup_tool",
                "result": {
                    "request_id": "2BC4FD6A-CE49-439F-81DF-E895C09CA49C",
                    "status": "completed",
                    "contact": "+13231112233",
                    "result_v1": {
                        "reachable": True,
                        "carrier": "Verizon",
                        "number_type": "mobile"
                    }
                }
            }
        }
    }


# Union type for all output models
LoopLookupOutput = Union[LoopLookupSingleOutput, LoopLookupBulkOutput, LoopLookupStatusOutput]


class LoopLookupError(BaseModel):
    """Error response model"""
    success: bool = Field(False, description="Always false for errors")
    code: int = Field(..., description="Error code")
    message: str = Field(..., description="Error message")

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": False,
                "code": 125,
                "message": "Authorization key is invalid or does not exist"
            }
        }
    }


# ========================================
# Loop Message Models
# ========================================

class LoopMessageSingleInput(BaseModel):
    """Input model for single message sending"""
    recipient: str = Field(..., description="Phone number or email address")
    text: str = Field(..., description="Message text", max_length=10000)
    sender_name: str = Field(..., description="Dedicated sender name")
    attachments: Optional[List[str]] = Field(None, description="Array of HTTPS URLs", max_items=3)
    timeout: Optional[int] = Field(None, description="Timeout in seconds", ge=5)
    passthrough: Optional[str] = Field(None, description="Metadata string", max_length=1000)
    status_callback: Optional[str] = Field(None, description="Webhook URL", max_length=256)
    status_callback_header: Optional[str] = Field(None, description="Custom auth header", max_length=256)
    reply_to_id: Optional[str] = Field(None, description="Message ID for replies")
    subject: Optional[str] = Field(None, description="Message subject")
    effect: Optional[str] = Field(None, description="Message effect")
    service: Optional[str] = Field("imessage", description="Service type: imessage or sms")

    @validator('recipient')
    def validate_recipient(cls, v):
        """Validate that recipient is either a valid phone number or email"""
        if not v or not v.strip():
            raise ValueError("Recipient cannot be empty")
        
        v = v.strip()
        
        # Check if it's an email (basic validation)
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if '@' in v:
            if not re.match(email_pattern, v):
                raise ValueError("Invalid email format")
            return v.lower()  # Normalize email to lowercase
        
        # Check if it's a phone number (remove formatting for validation)
        phone_clean = re.sub(r'[^\d+]', '', v)
        if not phone_clean:
            raise ValueError("Recipient must be a valid phone number or email")
        
        # Basic phone number validation (must have at least 7 digits)
        digits_only = re.sub(r'[^\d]', '', phone_clean)
        if len(digits_only) < 7:
            raise ValueError("Phone number must have at least 7 digits")
        
        return v

    @validator('attachments')
    def validate_attachments(cls, v):
        """Validate attachment URLs"""
        if v is not None:
            for i, url in enumerate(v):
                if not url.startswith('https://'):
                    raise ValueError(f"Attachment URL at index {i} must start with https://")
                if len(url) > 256:
                    raise ValueError(f"Attachment URL at index {i} exceeds 256 characters")
        return v

    @validator('effect')
    def validate_effect(cls, v):
        """Validate message effect"""
        if v is not None:
            valid_effects = [
                'slam', 'loud', 'gentle', 'invisibleInk', 'echo', 'spotlight',
                'balloons', 'confetti', 'love', 'lasers', 'fireworks', 
                'shootingStar', 'celebration'
            ]
            if v not in valid_effects:
                raise ValueError(f"Invalid effect. Must be one of: {', '.join(valid_effects)}")
        return v

    @validator('service')
    def validate_service(cls, v):
        """Validate service type"""
        if v not in ['imessage', 'sms']:
            raise ValueError("Service must be 'imessage' or 'sms'")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "recipient": "+1 (323) 123-4567",
                "text": "Hello from Loop Message!",
                "sender_name": "MyApp",
                "attachments": ["https://example.com/image.jpg"],
                "effect": "balloons",
                "service": "imessage"
            }
        }
    }


class LoopMessageGroupInput(BaseModel):
    """Input model for group message sending"""
    group: str = Field(..., description="iMessage group ID")
    text: str = Field(..., description="Message text", max_length=10000)
    sender_name: str = Field(..., description="Dedicated sender name")
    attachments: Optional[List[str]] = Field(None, description="Array of HTTPS URLs", max_items=3)
    timeout: Optional[int] = Field(None, description="Timeout in seconds", ge=5)
    passthrough: Optional[str] = Field(None, description="Metadata string", max_length=1000)
    status_callback: Optional[str] = Field(None, description="Webhook URL", max_length=256)
    status_callback_header: Optional[str] = Field(None, description="Custom auth header", max_length=256)

    @validator('group')
    def validate_group(cls, v):
        """Validate group ID is not empty"""
        if not v or not v.strip():
            raise ValueError("Group ID cannot be empty")
        return v.strip()

    @validator('attachments')
    def validate_attachments(cls, v):
        """Validate attachment URLs"""
        if v is not None:
            for i, url in enumerate(v):
                if not url.startswith('https://'):
                    raise ValueError(f"Attachment URL at index {i} must start with https://")
                if len(url) > 256:
                    raise ValueError(f"Attachment URL at index {i} exceeds 256 characters")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "group": "2BC4FD6A-CE49-439F-81DF-E895C09CA49C",
                "text": "Hello group!",
                "sender_name": "MyApp",
                "attachments": ["https://example.com/image.jpg"]
            }
        }
    }


class LoopMessageAudioInput(BaseModel):
    """Input model for audio message sending"""
    recipient: str = Field(..., description="Phone number or email address")
    text: str = Field(..., description="Message text", max_length=10000)
    media_url: str = Field(..., description="HTTPS URL to audio file", max_length=256)
    sender_name: str = Field(..., description="Dedicated sender name")
    audio_message: bool = Field(True, description="Must be true for audio messages")
    status_callback: Optional[str] = Field(None, description="Webhook URL", max_length=256)
    status_callback_header: Optional[str] = Field(None, description="Custom auth header", max_length=256)
    passthrough: Optional[str] = Field(None, description="Metadata string", max_length=1000)

    @validator('recipient')
    def validate_recipient(cls, v):
        """Validate that recipient is either a valid phone number or email"""
        if not v or not v.strip():
            raise ValueError("Recipient cannot be empty")
        
        v = v.strip()
        
        # Check if it's an email (basic validation)
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if '@' in v:
            if not re.match(email_pattern, v):
                raise ValueError("Invalid email format")
            return v.lower()  # Normalize email to lowercase
        
        # Check if it's a phone number (remove formatting for validation)
        phone_clean = re.sub(r'[^\d+]', '', v)
        if not phone_clean:
            raise ValueError("Recipient must be a valid phone number or email")
        
        # Basic phone number validation (must have at least 7 digits)
        digits_only = re.sub(r'[^\d]', '', phone_clean)
        if len(digits_only) < 7:
            raise ValueError("Phone number must have at least 7 digits")
        
        return v

    @validator('media_url')
    def validate_media_url(cls, v):
        """Validate media URL"""
        if not v.startswith('https://'):
            raise ValueError("Media URL must start with https://")
        if len(v) > 256:
            raise ValueError("Media URL exceeds 256 characters")
        
        # Check for supported audio formats
        supported_formats = ['.mp3', '.wav', '.m4a', '.caf', '.aac']
        if not any(v.lower().endswith(fmt) for fmt in supported_formats):
            raise ValueError(f"Audio file must be one of: {', '.join(supported_formats)}")
        
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "recipient": "+1 (323) 123-4567",
                "text": "Voice message",
                "media_url": "https://example.com/audio.mp3",
                "sender_name": "MyApp",
                "audio_message": True
            }
        }
    }


class LoopMessageReactionInput(BaseModel):
    """Input model for reaction sending"""
    recipient: str = Field(..., description="Phone number or email address")
    text: str = Field(..., description="Message text", max_length=10000)
    message_id: str = Field(..., description="Target message ID")
    sender_name: str = Field(..., description="Dedicated sender name")
    reaction: str = Field(..., description="Reaction type")
    status_callback: Optional[str] = Field(None, description="Webhook URL", max_length=256)
    status_callback_header: Optional[str] = Field(None, description="Custom auth header", max_length=256)
    passthrough: Optional[str] = Field(None, description="Metadata string", max_length=1000)

    @validator('recipient')
    def validate_recipient(cls, v):
        """Validate that recipient is either a valid phone number or email"""
        if not v or not v.strip():
            raise ValueError("Recipient cannot be empty")
        
        v = v.strip()
        
        # Check if it's an email (basic validation)
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if '@' in v:
            if not re.match(email_pattern, v):
                raise ValueError("Invalid email format")
            return v.lower()  # Normalize email to lowercase
        
        # Check if it's a phone number (remove formatting for validation)
        phone_clean = re.sub(r'[^\d+]', '', v)
        if not phone_clean:
            raise ValueError("Recipient must be a valid phone number or email")
        
        # Basic phone number validation (must have at least 7 digits)
        digits_only = re.sub(r'[^\d]', '', phone_clean)
        if len(digits_only) < 7:
            raise ValueError("Phone number must have at least 7 digits")
        
        return v

    @validator('message_id')
    def validate_message_id(cls, v):
        """Validate message ID is not empty"""
        if not v or not v.strip():
            raise ValueError("Message ID cannot be empty")
        return v.strip()

    @validator('reaction')
    def validate_reaction(cls, v):
        """Validate reaction type"""
        valid_reactions = [
            'love', 'like', 'dislike', 'laugh', 'exclaim', 'question',
            '-love', '-like', '-dislike', '-laugh', '-exclaim', '-question'
        ]
        if v not in valid_reactions:
            raise ValueError(f"Invalid reaction. Must be one of: {', '.join(valid_reactions)}")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "recipient": "+1 (323) 123-4567",
                "text": "Reaction",
                "message_id": "2BC4FD6A-CE49-439F-81DF-E895C09CA49C",
                "sender_name": "MyApp",
                "reaction": "love"
            }
        }
    }


class LoopMessageStatusInput(BaseModel):
    """Input model for status check"""
    message_id: str = Field(..., description="Message ID to check status for")

    @validator('message_id')
    def validate_message_id(cls, v):
        """Validate message ID is not empty"""
        if not v or not v.strip():
            raise ValueError("Message ID cannot be empty")
        return v.strip()

    model_config = {
        "json_schema_extra": {
            "example": {
                "message_id": "2BC4FD6A-CE49-439F-81DF-E895C09CA49C"
            }
        }
    }


# Union type for all Loop Message input models
LoopMessageInput = Union[
    LoopMessageSingleInput, 
    LoopMessageGroupInput, 
    LoopMessageAudioInput, 
    LoopMessageReactionInput, 
    LoopMessageStatusInput
]


class LoopMessageGroup(BaseModel):
    """Group information"""
    group_id: str = Field(..., description="Group identifier")
    name: Optional[str] = Field(None, description="Group name")
    participants: List[str] = Field(..., description="List of participant phone numbers/emails")

    model_config = {
        "json_schema_extra": {
            "example": {
                "group_id": "2BC4FD6A-CE49-439F-81DF-E895C09CA49C",
                "name": "My Group Chat",
                "participants": ["+13231112233", "+13232223344"]
            }
        }
    }


class LoopMessageSingleOutput(BaseModel):
    """Output model for single message"""
    tool: Literal["loop_message_tool"] = Field(..., description="Tool identifier")
    success: bool = Field(..., description="Request success status")
    message_id: str = Field(..., description="Message identifier")
    recipient: str = Field(..., description="Normalized recipient")
    text: str = Field(..., description="Message text")

    model_config = {
        "json_schema_extra": {
            "example": {
                "tool": "loop_message_tool",
                "success": True,
                "message_id": "2BC4FD6A-CE49-439F-81DF-E895C09CA49C",
                "recipient": "+13231112233",
                "text": "Hello from Loop Message!"
            }
        }
    }


class LoopMessageGroupOutput(BaseModel):
    """Output model for group message"""
    tool: Literal["loop_message_tool"] = Field(..., description="Tool identifier")
    success: bool = Field(..., description="Request success status")
    message_id: str = Field(..., description="Message identifier")
    group: LoopMessageGroup = Field(..., description="Group information")
    text: str = Field(..., description="Message text")

    model_config = {
        "json_schema_extra": {
            "example": {
                "tool": "loop_message_tool",
                "success": True,
                "message_id": "2BC4FD6A-CE49-439F-81DF-E895C09CA49C",
                "group": {
                    "group_id": "2BC4FD6A-CE49-439F-81DF-E895C09CA49C",
                    "name": "My Group Chat",
                    "participants": ["+13231112233", "+13232223344"]
                },
                "text": "Hello group!"
            }
        }
    }


class LoopMessageStatusResult(BaseModel):
    """Message status result"""
    message_id: str = Field(..., description="Message identifier")
    status: str = Field(..., description="Message status")
    recipient: Optional[str] = Field(None, description="Recipient")
    text: Optional[str] = Field(None, description="Message text")
    sandbox: Optional[bool] = Field(None, description="Sandbox status")
    error_code: Optional[int] = Field(None, description="Error code if failed")
    sender_name: Optional[str] = Field(None, description="Sender name")
    passthrough: Optional[str] = Field(None, description="Passthrough metadata")
    last_update: Optional[str] = Field(None, description="Last update timestamp")

    model_config = {
        "json_schema_extra": {
            "example": {
                "message_id": "2BC4FD6A-CE49-439F-81DF-E895C09CA49C",
                "status": "sent",
                "recipient": "+13231112233",
                "text": "Hello from Loop Message!",
                "sandbox": False,
                "sender_name": "MyApp",
                "last_update": "2021-12-31T23:59:59.809Z"
            }
        }
    }


class LoopMessageStatusOutput(BaseModel):
    """Output model for status check"""
    tool: Literal["loop_message_tool"] = Field(..., description="Tool identifier")
    result: LoopMessageStatusResult = Field(..., description="Status result")

    model_config = {
        "json_schema_extra": {
            "example": {
                "tool": "loop_message_tool",
                "result": {
                    "message_id": "2BC4FD6A-CE49-439F-81DF-E895C09CA49C",
                    "status": "sent",
                    "recipient": "+13231112233",
                    "text": "Hello from Loop Message!",
                    "sandbox": False,
                    "sender_name": "MyApp",
                    "last_update": "2021-12-31T23:59:59.809Z"
                }
            }
        }
    }


# Union type for all Loop Message output models
LoopMessageOutput = Union[LoopMessageSingleOutput, LoopMessageGroupOutput, LoopMessageStatusOutput]


class LoopMessageError(BaseModel):
    """Error response model for Loop Message"""
    success: bool = Field(False, description="Always false for errors")
    code: int = Field(..., description="Error code")
    message: str = Field(..., description="Error message")

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": False,
                "code": 125,
                "message": "Authorization key is invalid or does not exist"
            }
        }
    }