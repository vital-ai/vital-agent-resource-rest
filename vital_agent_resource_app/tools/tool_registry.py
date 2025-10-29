# Tool Registry - Instance-based registry for tools
from typing import Dict, Type, List, Any
from pydantic import BaseModel


class ToolRegistry:
    """Registry for managing tool input/output models and instances"""
    
    def __init__(self):
        self._tool_input_models: Dict[str, Type[BaseModel]] = {}
        self._tool_output_models: Dict[str, Type[BaseModel]] = {}
        self._tool_instances: Dict[str, Any] = {}
        self._tool_examples: Dict[str, List[dict]] = {}
    
    def add_tool(self, tool_name: str, input_model: Type[BaseModel], output_model: Type[BaseModel], tool_instance: Any = None):
        """Add a tool with its input/output models and optional instance"""
        self._tool_input_models[tool_name] = input_model
        self._tool_output_models[tool_name] = output_model
        if tool_instance:
            self._tool_instances[tool_name] = tool_instance
            # Generate examples from tool instance if available
            if hasattr(tool_instance, 'get_examples'):
                self._tool_examples[tool_name] = tool_instance.get_examples()
    
    def get_tool_instance(self, tool_name: str) -> Any:
        """Get the tool instance for a specific tool"""
        return self._tool_instances.get(tool_name)
    
    def get_input_model(self, tool_name: str) -> Type[BaseModel]:
        """Get the input model for a specific tool"""
        return self._tool_input_models.get(tool_name)
    
    def get_output_model(self, tool_name: str) -> Type[BaseModel]:
        """Get the output model for a specific tool"""
        return self._tool_output_models.get(tool_name)
    
    def get_registered_tools(self) -> List[str]:
        """Get list of all registered tool names"""
        return list(self._tool_input_models.keys())
    
    def validate_tool_input(self, tool_name: str, data: dict) -> BaseModel:
        """Validate input data against the tool's input model"""
        input_model = self.get_input_model(tool_name)
        if not input_model:
            raise ValueError(f"Tool '{tool_name}' not registered")
        return input_model(**data)
    
    def create_tool_output(self, tool_name: str, data: dict) -> BaseModel:
        """Create output using the tool's output model"""
        output_model = self.get_output_model(tool_name)
        if not output_model:
            raise ValueError(f"Tool '{tool_name}' not registered")
        return output_model(**data)
    
    def get_examples_for_tool(self, tool_name: str) -> List[dict]:
        """Get examples for a specific tool"""
        return self._tool_examples.get(tool_name, [])
    
    def get_all_examples(self) -> List[dict]:
        """Get all examples from all registered tools"""
        examples = []
        for tool_examples in self._tool_examples.values():
            examples.extend(tool_examples)
        return examples
