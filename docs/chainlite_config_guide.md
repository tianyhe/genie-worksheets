# Chainlite Configuration Management

This guide explains how to handle the global chainlite configuration (`llm_config.yaml`) in your project using the centralized configuration utility.

## Overview

The `worksheets.utils.chainlite_config` module provides a centralized way to load and manage the chainlite configuration, eliminating the need for hardcoded paths and duplicate configuration loading across your codebase.

## Key Benefits

1. **Centralized Management**: Single source of truth for config loading
2. **Auto-Discovery**: Automatically finds `llm_config.yaml` in your project
3. **Load Once**: Ensures configuration is loaded only once per application run
4. **Error Handling**: Proper error handling and logging
5. **Flexibility**: Supports custom config paths when needed

## Basic Usage

### 1. Simple Module-Level Loading (Recommended)

```python
from chainlite import llm_generation_chain
from worksheets.utils.chainlite_config import ensure_chainlite_config_loaded

# Load config at module level
ensure_chainlite_config_loaded()

# Now you can use chainlite functions anywhere in the module
async def my_function():
    result = await llm_generation_chain(
        template_file="my_prompt.prompt",
        engine="gpt-4o-mini",
        max_tokens=100,
    ).ainvoke({"input": "Hello"})
    return result
```

### 2. Explicit Config Loading

```python
from worksheets.utils.chainlite_config import load_chainlite_config

# Load from specific path
load_chainlite_config("/path/to/custom/llm_config.yaml")

# Or use auto-discovery
load_chainlite_config()
```

### 3. Check Config Status

```python
from worksheets.utils.chainlite_config import is_config_loaded, get_config_path

if is_config_loaded():
    print(f"Config loaded from: {get_config_path()}")
else:
    print("Config not loaded yet")
```

## Configuration File Discovery

The utility automatically searches for `llm_config.yaml` in the following locations:

1. **Project root** (where `pyproject.toml` is located)
2. `config/llm_config.yaml`
3. `src/llm_config.yaml`

## Migration from Old Approach

### Before (Old Approach)
```python
import os
from chainlite import load_config_from_file

CURRENT_DIR = os.path.dirname(os.path.realpath(__file__))
load_config_from_file(os.path.join(CURRENT_DIR, "..", "..", "llm_config.yaml"))
```

### After (New Approach)
```python
from worksheets.utils.chainlite_config import ensure_chainlite_config_loaded

ensure_chainlite_config_loaded()
```

## Advanced Usage

### Force Reload Configuration

```python
from worksheets.utils.chainlite_config import load_chainlite_config

# Force reload even if already loaded
load_chainlite_config(force_reload=True)
```

### Custom Error Handling

```python
from worksheets.utils.chainlite_config import load_chainlite_config
from loguru import logger

try:
    load_chainlite_config()
except FileNotFoundError:
    logger.error("llm_config.yaml not found in project")
    # Handle missing config
except Exception as e:
    logger.error(f"Failed to load config: {e}")
    # Handle other errors
```

### Auto-Loading on Import (Optional)

If you want the configuration to be loaded automatically when the module is imported, you can uncomment the auto-load line in `chainlite_config.py`:

```python
# Uncomment this line in chainlite_config.py
auto_load_config()
```

## Best Practices

1. **Load Early**: Call `ensure_chainlite_config_loaded()` at the top of modules that use chainlite
2. **Single Loading**: The utility ensures config is loaded only once, so it's safe to call multiple times
3. **Error Handling**: Always handle potential `FileNotFoundError` in production code
4. **Logging**: The utility provides informative logging about config loading status

## Configuration File Structure

Your `llm_config.yaml` should be structured like this:

```yaml
prompt_dirs:
  - "./src/kraken/prompts/"
  - "./prompts/"

litellm_set_verbose: false

prompt_logging:
  log_file: "./prompt_logs.jsonl"
  prompts_to_skip:
    - "tests/test.prompt"

llm_endpoints:
  - api_base: https://your-api-endpoint.com/
    api_version: "2024-08-01-preview"
    api_key: "YOUR_API_KEY"
    engine_map:
      gpt-4o: azure/gpt-4o
      gpt-4o-mini: azure/gpt-4o-mini
```

## Troubleshooting

### Config File Not Found
- Ensure `llm_config.yaml` exists in your project root
- Check file permissions
- Verify the file is not in `.gitignore` if you expect it to be tracked

### Import Errors
- Make sure you're importing from the correct module path
- Verify the `worksheets` package is properly installed

### Loading Errors
- Check the YAML syntax in your config file
- Ensure all required fields are present
- Verify API keys and endpoints are correct

