import requests
from typing import List, Dict, Any
from vital_agent_resource_app.tools.abstract_tool import AbstractTool
from vital_agent_resource_app.tools.tool_request import ToolRequest
from vital_agent_resource_app.tools.tool_response import ToolResponse
from vital_agent_resource_app.tools.google_address_validation.models import AddressValidationResult, AddressComponent


class GoogleAddressValidationTool(AbstractTool):

    def get_examples(self) -> List[Dict[str, Any]]:
        """Return list of example requests for Google Address Validation tool"""
        return [
            {
                "tool": "google_address_validation_tool",
                "tool_input": {
                    "address": "1600 Amphitheatre Parkway, Mountain View, CA"
                }
            },
            {
                "tool": "google_address_validation_tool",
                "tool_input": {
                    "address": "475 st marks broklyn 7a"
                }
            }
        ]

    def handle_tool_request(self, tool_request: ToolRequest) -> ToolResponse:
        import time
        start_time = time.time()
        
        # Extract address from validated tool input
        validated_input = tool_request.tool_input
        address = validated_input.address
        
        try:
            results = self.validate_address(address)
            
            # Create structured output using the registered model
            from vital_agent_resource_app.tools.google_address_validation.models import AddressValidationOutput
            tool_output = AddressValidationOutput(
                tool="google_address_validation_tool",
                results=results
            )
            
            return self._create_success_response(tool_output.dict(), start_time)
            
        except Exception as e:
            return self._create_error_response(str(e), start_time)

    def validate_address(self, address: str) -> List[AddressValidationResult]:
        
        print(f"Validating address: {address}")
        
        api_key = self.config.get("api_key", "")
        
        if not api_key:
            print("Error: No API key configured for Google Address Validation")
            return []
        
        # Google Address Validation API endpoint
        url = "https://addressvalidation.googleapis.com/v1:validateAddress"
        
        # Request payload for Address Validation API
        payload = {
            "address": {
                "addressLines": [address]
            },
            "enableUspsCass": True
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        params = {
            "key": api_key
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, params=params)
            response.raise_for_status()
            
            result_data = response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"Address Validation API Error: {e}")
            return []
        except Exception as e:
            print(f"Unexpected error during address validation: {e}")
            return []
        
        validated_addresses = []
        
        # Parse the Address Validation API response
        result = result_data.get('result', {})
        
        if result:
            # Extract address components
            address_components = []
            components = result.get('address', {}).get('addressComponents', [])
            
            for component in components:
                address_components.append(AddressComponent(
                    component_name=component.get('componentName', {}).get('text', ''),
                    component_type=component.get('componentType', ''),
                    confirmation_level=component.get('confirmationLevel', '')
                ))
            
            validated_address = AddressValidationResult(
                formatted_address=result.get('address', {}).get('formattedAddress', ''),
                postal_address=result.get('address', {}).get('postalAddress', {}),
                address_components=address_components,
                geocode=result.get('geocode', {}),
                metadata=result.get('metadata', {}),
                usps_data=result.get('uspsData', {})
            )
            
            validated_addresses.append(validated_address)
        
        return validated_addresses