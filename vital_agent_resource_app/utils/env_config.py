import os
import logging
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger("VitalAgentContainerLogger")


class EnvConfigLoader:
    """
    Load configuration from environment variables with hierarchical parsing.
    Drop-in replacement for ConfigUtils that produces identical dictionary structure.
    
    Uses __ (double underscore) as hierarchy separator to support arbitrary depth.
    Environment variables are split by __ and automatically built into nested structures.
    
    Pattern: {VITAL_ENV}__SECTION__SUBSECTION__KEY
    
    Examples:
        DEV__TOOL__LOOP_LOOKUP__API_KEY → tools[loop_lookup_tool]['api_key']
        DEV__TOOL__LOOP_MESSAGE__AUTHORIZATION_KEY → tools[loop_message_tool]['authorization_key']
        DEV__RUNPOD__API_KEY → runpod['runpod_api_key']
        DEV__MEMORYDB__URL → memorydb['url']
        DEV__JWT__ENABLED → jwt config (handled separately)
    """
    
    _config_cache: Optional[Dict[str, Any]] = None
    
    @staticmethod
    def get_env() -> str:
        """Get current environment prefix string"""
        return os.getenv('VITAL_ENV', 'DEV').upper()
    
    @staticmethod
    def _set_nested_value(config: Dict[str, Any], path: List[str], value: str):
        """
        Set a value in a nested dictionary using a path list.
        
        Args:
            config: Dictionary to update
            path: List of keys representing the path (e.g., ['tools', 'weather', 'api_key'])
            value: Value to set
        """
        current = config
        for key in path[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[path[-1]] = value
    
    @staticmethod
    def get_config_value(
        key: str,
        default: Any = None,
        required: bool = False,
        value_type: type = str
    ) -> Any:
        """
        Get configuration value with environment prefix
        
        Args:
            key: Config key (e.g., 'TOOL_WEATHER_API_KEY')
            default: Default value if not found
            required: Raise error if not found and no default
            value_type: Type to convert value to (str, int, bool, list)
        
        Returns:
            Configuration value
        
        Raises:
            ValueError: If required config key not found
        """
        env = EnvConfigLoader.get_env()
        prefixed_key = f"{env}_{key}"
        
        # Get prefixed key
        value = os.getenv(prefixed_key)
        
        # Handle required values
        if value is None:
            if required:
                raise ValueError(f"Required config key not found: {prefixed_key}")
            return default
        
        # Type conversion
        return EnvConfigLoader._convert_value(value, value_type)
    
    @staticmethod
    def _convert_value(value: str, value_type: type) -> Any:
        """Convert string value to specified type"""
        if value_type == bool:
            return value.lower() in ('true', '1', 'yes', 'on')
        elif value_type == int:
            return int(value)
        elif value_type == float:
            return float(value)
        elif value_type == list:
            # Split by comma and strip whitespace
            return [item.strip() for item in value.split(',') if item.strip()]
        else:
            return value
    
    @staticmethod
    def get_tool_config(tool_name: str) -> Dict[str, Any]:
        """
        Get all configuration for a specific tool
        
        Args:
            tool_name: Tool name (e.g., 'weather_tool', 'loop_message_tool')
        
        Returns:
            Dictionary with tool configuration including 'tool_id'
        """
        env = EnvConfigLoader.get_env()
        
        # Normalize tool name to uppercase with underscores
        # Remove '_tool' suffix if present to get base name
        tool_name_upper = tool_name.upper().replace('-', '_')
        if tool_name_upper.endswith('_TOOL'):
            tool_name_upper = tool_name_upper[:-5]  # Remove '_TOOL' suffix
        
        # Build prefix for this tool using __ separator
        prefix = f"{env}__TOOL__{tool_name_upper}__"
        
        # Scan environment for matching keys
        config = {'tool_id': tool_name}
        
        for key, value in os.environ.items():
            if key.startswith(prefix):
                # Extract config key name (everything after prefix)
                config_key = key[len(prefix):].lower()
                config[config_key] = value
        
        if len(config) > 1:
            logger.debug(f"Loaded config for {tool_name}: {list(config.keys())}")
        else:
            logger.warning(f"No config found for {tool_name} (looking for prefix: {prefix})")
        
        return config if len(config) > 1 else None
    
    @staticmethod
    def get_memorydb_config() -> Dict[str, Any]:
        """Connection config for the shared MemoryDB service.

        A global service rather than a tool: the connection is defined once and
        any tool may opt into using it. Returns {} when unconfigured.
        """
        env = EnvConfigLoader.get_env()
        prefix = f"{env}__MEMORYDB__"
        config = {}
        for key, value in os.environ.items():
            if key.startswith(prefix):
                config[key[len(prefix):].lower()] = value
        return config

    @staticmethod
    def _get_all_tool_configs() -> List[Dict[str, Any]]:
        """
        Scan environment and build list of all tool configurations
        
        Returns:
            List of tool config dictionaries
        """
        env = EnvConfigLoader.get_env()
        prefix = f"{env}__TOOL__"
        
        # Find all unique tool names by scanning environment
        tool_names = set()
        for key in os.environ.keys():
            if key.startswith(prefix):
                # Extract tool name (between TOOL__ and next __)
                remainder = key[len(prefix):]
                if '__' in remainder:
                    tool_name = remainder.split('__')[0]
                    tool_names.add(tool_name)
        
        # Build config for each tool
        tools = []
        logger.debug(f"Found tool names in environment: {sorted(tool_names)}")
        for tool_name in sorted(tool_names):
            tool_name_lower = tool_name.lower() + '_tool'
            config = EnvConfigLoader.get_tool_config(tool_name_lower)
            if config:
                tools.append(config)
        
        return tools
    
    @staticmethod
    def _get_runpod_config() -> Dict[str, str]:
        """Get RunPod configuration"""
        env = EnvConfigLoader.get_env()
        prefix = f"{env}__RUNPOD__"
        
        config = {}
        for key, value in os.environ.items():
            if key.startswith(prefix):
                config_key = key[len(prefix):].lower()
                config[config_key] = value
        
        return config
    
    @staticmethod
    def load_config() -> Dict[str, Any]:
        """
        Load all configuration and return in EXACT format as YAML config.
        Drop-in replacement for ConfigUtils.load_config()
        
        Parses environment variables hierarchically by splitting on __.
        
        Returns:
            Configuration dictionary matching YAML structure:
            {
                'vital_agent_resource_app': {
                    'tools': [
                        {'tool_id': 'weather_tool', 'api_key': 'xxx'},
                        {'tool_id': 'loop_message_tool', 'authorization_key': 'xxx', 'secret_key': 'xxx'},
                        ...
                    ],
                    'runpod': {
                        'runpod_api_key': 'xxx'
                    },
                    'memorydb': {
                        'url': 'rediss://...', 'ssl': 'true'
                    }
                }
            }
        """
        # Return cached config if available
        if EnvConfigLoader._config_cache is not None:
            return EnvConfigLoader._config_cache
        
        env = EnvConfigLoader.get_env()
        logger.info(f"Loading configuration from environment variables (VITAL_ENV={env})")
        
        # Parse all environment variables hierarchically
        env_prefix = f"{env}__"
        tool_configs = {}  # tool_name -> config dict
        runpod_config = {}
        memorydb_config = {}
        
        for key, value in os.environ.items():
            if not key.startswith(env_prefix):
                continue
            
            # Remove environment prefix and split by __
            remainder = key[len(env_prefix):]
            parts = remainder.split('__')
            
            if len(parts) < 2:
                continue
            
            section = parts[0]  # TOOL, RUNPOD, JWT, APP, etc.
            
            if section == 'TOOL':
                # Format: DEV__TOOL__TOOL_NAME__CONFIG_KEY
                if len(parts) >= 3:
                    tool_name = parts[1]  # e.g., LOOP_LOOKUP
                    config_key = '__'.join(parts[2:])  # e.g., API_KEY or could be nested
                    
                    if tool_name not in tool_configs:
                        tool_configs[tool_name] = {}
                    
                    # Convert config key to lowercase
                    tool_configs[tool_name][config_key.lower()] = value
            
            elif section == 'RUNPOD':
                # Format: DEV__RUNPOD__CONFIG_KEY
                if len(parts) >= 2:
                    config_key = '__'.join(parts[1:])
                    runpod_config[config_key.lower()] = value

            elif section == 'MEMORYDB':
                # Format: DEV__MEMORYDB__CONFIG_KEY
                # A shared service, not a tool: any tool may use it, and the
                # connection is configured once rather than per consumer.
                if len(parts) >= 2:
                    config_key = '__'.join(parts[1:])
                    memorydb_config[config_key.lower()] = value
        
        # Convert tool_configs dict to list format with tool_id
        tools = []
        for tool_name, config in sorted(tool_configs.items()):
            tool_id = tool_name.lower() + '_tool'
            tool_entry = {'tool_id': tool_id}
            tool_entry.update(config)
            tools.append(tool_entry)
        
        # Build final config structure matching YAML format
        config = {
            'vital_agent_resource_app': {
                'tools': tools,
                'runpod': runpod_config,
                'memorydb': memorydb_config
            }
        }
        
        # Cache the config
        EnvConfigLoader._config_cache = config
        
        logger.info(f"Loaded configuration for {len(tools)} tools")
        if memorydb_config.get('url'):
            logger.info("MemoryDB: shared service configured")
        if tools:
            logger.debug(f"Tools loaded: {[t['tool_id'] for t in tools]}")
        
        return config
    
    @staticmethod
    def clear_cache():
        """Clear the configuration cache (useful for testing)"""
        EnvConfigLoader._config_cache = None
