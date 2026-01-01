"""
Helper functions for loading LLM provider configuration from .env file
and generating codex command options.
"""

import os
from pathlib import Path


def _load_llm_config():
    """
    Load LLM provider configuration from .env file in project root.
    
    Supports two modes:
    1. API-based: Requires MODEL, BASE_URL, ENV_KEY, PROVIDER. This is when using user's own API key, including OpenAI API.
    2. ChatGPT-based: Requires only MODEL and PROVIDER=chatgpt. This is to support using Codex through a ChatGPT account.
    
    Returns:
        dict: Configuration dictionary with keys:
            - model: The model name
            - base_url: The API base URL (None for ChatGPT mode)
            - env_key: The environment variable name for the API key (None for ChatGPT mode)
            - provider: The provider name
            
    Raises:
        SystemExit: If .env file is missing or required variables are not set
    """
    env_file = Path(".env")
    
    if not env_file.exists():
        raise SystemExit(
            "Error: .env file not found in project root.\n"
            "Please create a .env file with one of the following configurations:\n\n"
            "For API-based access:\n"
            "  MODEL=<model_name>\n"
            "  BASE_URL=<api_base_url>\n"
            "  ENV_KEY=<api_key_env_var_name>\n"
            "  PROVIDER=<provider_name>\n\n"
            "For ChatGPT-based access:\n"
            "  MODEL=<model_name>\n"
            "  PROVIDER=chatgpt"
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
    
    # Validate MODEL and PROVIDER are always required
    required_vars = ['MODEL', 'PROVIDER']
    missing_vars = [var for var in required_vars if var not in config]
    
    if missing_vars:
        raise SystemExit(
            f"Error: Missing required variables in .env file: {', '.join(missing_vars)}\n"
            "Please ensure your .env file contains:\n"
            "  MODEL=<model_name>\n"
            "  PROVIDER=<provider_name>"
        )
    
    provider = config['PROVIDER']
    
    # For ChatGPT mode, only MODEL and PROVIDER are required
    if provider == 'chatgpt':
        return {
            'model': config['MODEL'],
            'base_url': None,
            'env_key': None,
            'provider': provider
        }
    
    # For API-based mode, BASE_URL and ENV_KEY are also required
    api_required_vars = ['BASE_URL', 'ENV_KEY']
    missing_api_vars = [var for var in api_required_vars if var not in config]
    
    if missing_api_vars:
        raise SystemExit(
            f"Error: Missing required variables for API-based mode in .env file: {', '.join(missing_api_vars)}\n"
            "For API-based access, please ensure your .env file contains:\n"
            "  MODEL=<model_name>\n"
            "  BASE_URL=<api_base_url>\n"
            "  ENV_KEY=<api_key_env_var_name>\n"
            "  PROVIDER=<provider_name>\n\n"
            "Or use ChatGPT mode with:\n"
            "  MODEL=<model_name>\n"
            "  PROVIDER=chatgpt"
        )
    
    return {
        'model': config['MODEL'],
        'base_url': config['BASE_URL'],
        'env_key': config['ENV_KEY'],
        'provider': provider
    }


def _build_codex_config_options(config):
    """
    Generate codex -c config options from the provided configuration.
    
    For ChatGPT mode (provider=chatgpt), returns an empty list since no
    custom config options are needed.
    
    For API-based mode, returns config options for custom provider setup.
    
    Args:
        config: Configuration dictionary from _load_llm_config()
    
    Returns:
        list: List of strings to pass as --config/-c options to codex
              Empty list for ChatGPT mode
            
    Raises:
        SystemExit: If API key is not in environment (for API-based mode)
    """
    provider = config['provider']
    
    # For ChatGPT mode, no config options needed
    if provider == 'chatgpt':
        return []
    
    # For API-based mode, build config options
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
    
    return config_options


def get_llm_configs():
    """
    Load LLM configuration and build codex config options in one call.
    
    This is the main entry point for getting all LLM-related configuration.
    It loads the .env file once and returns both the config dict and the
    codex command-line options.
    
    Returns:
        tuple: (llm_config, config_options)
            - llm_config: dict with keys 'model', 'base_url', 'env_key', 'provider'
            - config_options: list of strings for codex --config options
            
    Raises:
        SystemExit: If .env file is missing, required variables are not set,
                    or API key is not in environment
    """
    config = _load_llm_config()
    options = _build_codex_config_options(config)
    return config, options
