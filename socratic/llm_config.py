"""
Helper functions for loading LLM provider configuration from .env file
and generating codex command options.
"""

import os
from pathlib import Path


def load_llm_config():
    """
    Load LLM provider configuration from .env file in project root.
    
    Returns:
        dict: Configuration dictionary with keys:
            - model: The model name
            - base_url: The API base URL
            - env_key: The environment variable name for the API key
            
    Raises:
        SystemExit: If .env file is missing or required variables are not set
    """
    env_file = Path(".env")
    
    if not env_file.exists():
        raise SystemExit(
            "Error: .env file not found in project root.\n"
            "Please create a .env file with the following variables:\n"
            "  MODEL=<model_name>\n"
            "  BASE_URL=<api_base_url>\n"
            "  ENV_KEY=<api_key_env_var_name>"
        )
    
    # Read .env file
    config = {}
    with open(env_file, 'r') as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            # Parse KEY=VALUE
            if '=' in line:
                key, value = line.split('=', 1)
                config[key.strip()] = value.strip()
    
    # Validate required variables
    required_vars = ['MODEL', 'BASE_URL', 'ENV_KEY']
    missing_vars = [var for var in required_vars if var not in config]
    
    if missing_vars:
        raise SystemExit(
            f"Error: Missing required variables in .env file: {', '.join(missing_vars)}\n"
            "Please ensure your .env file contains:\n"
            "  MODEL=<model_name>\n"
            "  BASE_URL=<api_base_url>\n"
            "  ENV_KEY=<api_key_env_var_name>"
        )
    
    return {
        'model': config['MODEL'],
        'base_url': config['BASE_URL'],
        'env_key': config['ENV_KEY']
    }


def get_codex_config_options():
    """
    Generate codex -c config options from .env configuration.
    
    Returns:
        tuple: (config_options, env_key) where:
            - config_options: List of strings to pass as --config/-c options to codex
            - env_key: Environment variable name containing the API key
            
    Raises:
        SystemExit: If .env file is missing, variables are not set, or API key is not in environment
    """
    config = load_llm_config()
    
    model = config['model']
    base_url = config['base_url']
    env_key = config['env_key']
    
    # Check if the API key exists in environment
    if not os.environ.get(env_key):
        raise SystemExit(
            f"Error: {env_key} is not set in the environment.\n"
            f"Please set the API key: export {env_key}='your_api_key_here'"
        )
    
    # Determine if this is OpenAI
    is_openai = (base_url == "https://api.openai.com/v1" and env_key == "OPENAI_API_KEY")
    
    # Build config options
    config_options = [
        'model_provider="temp_provider"',
        'model_providers.temp_provider.name="temp_provider"',
        f'model_providers.temp_provider.base_url="{base_url}"',
        f'model_providers.temp_provider.env_key="{env_key}"'
    ]
    
    # Add wire_api for OpenAI models
    if is_openai:
        config_options.append('model_providers.temp_provider.wire_api="responses"')
    
    return config_options, env_key

