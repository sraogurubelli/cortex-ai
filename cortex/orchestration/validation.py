"""
Validation utilities for agent tools.

Provides helpers for:
- Token-efficient file path validation
- JSON Schema validation with detailed error context
- YAML/JSON content validation

These utilities are designed to be used in agent tools that need to validate
user-generated content (YAML configs, JSON data, etc.) with helpful error messages.
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Optional jsonschema import (not required dependency)
try:
    import jsonschema
    from jsonschema import ValidationError

    _JSONSCHEMA_AVAILABLE = True
except ImportError:
    _JSONSCHEMA_AVAILABLE = False
    ValidationError = Exception  # type: ignore

# Optional YAML import (not required dependency)
try:
    import yaml

    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False


# =========================================================================
# File Path Resolution (Token-Efficient)
# =========================================================================


def resolve_content_from_path(
    content: Optional[str] = None,
    file_path: Optional[str | Path] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Resolve content from either direct string or file path.

    This enables token-efficient validation where agents can write to a file first,
    then validate by passing only the file path instead of duplicating the content
    in the tool call.

    Args:
        content: Direct content string
        file_path: Path to file containing content

    Returns:
        Tuple of (content_str, error_message). If error_message is not None,
        content_str will be None.

    Example:
        # Agent writes large YAML to file
        write_file("/tmp/config.yaml", large_yaml_content)

        # Then validates using just the path (saves tokens!)
        validate_yaml(file_path="/tmp/config.yaml")  # Not: validate_yaml(content=large_yaml_content)

    Raises:
        None - Returns error message as string instead of raising
    """
    if content and file_path:
        return None, "Provide either content or file_path, not both"

    if not content and not file_path:
        return None, "Must provide either content or file_path"

    if content:
        return content, None

    # Read from file
    try:
        file_path = Path(file_path)
        if not file_path.exists():
            return None, f"File not found: {file_path}"

        if not file_path.is_file():
            return None, f"Path is not a file: {file_path}"

        content_str = file_path.read_text(encoding="utf-8")

        if not content_str or not content_str.strip():
            return None, f"File is empty: {file_path}"

        return content_str, None

    except FileNotFoundError:
        return None, f"File not found: {file_path}"
    except PermissionError:
        return None, f"Permission denied reading file: {file_path}"
    except UnicodeDecodeError:
        return None, f"File is not valid UTF-8 text: {file_path}"
    except Exception as e:
        return None, f"Error reading file {file_path}: {type(e).__name__}: {e}"


# =========================================================================
# JSON Schema Validation
# =========================================================================


def format_schema_path(schema_path: list[str | int]) -> str:
    """
    Format JSON schema path into a readable string.

    Filters out noise words like 'properties' and 'items'.

    Args:
        schema_path: Path components from ValidationError

    Returns:
        Formatted path string

    Example:
        >>> format_schema_path(['properties', 'user', 'properties', 'name'])
        'user -> name'
        >>> format_schema_path(['items', '0', 'properties', 'id'])
        '0 -> id'
    """
    noise_words = {"properties", "items", "additionalProperties"}
    return " -> ".join(
        str(p) for p in schema_path if str(p) not in noise_words
    )


def get_schema_requirements(schema: dict, path: list[str]) -> str:
    """
    Extract requirements from JSON schema at the given path.

    Provides human-readable requirements to help users fix validation errors.

    Args:
        schema: JSON schema dict
        path: Path to the failing field

    Returns:
        Human-readable requirements string

    Example:
        >>> schema = {"type": "object", "properties": {"name": {"type": "string", "pattern": "^[A-Z]"}}}
        >>> get_schema_requirements(schema, ["name"])
        'type: string; must match pattern: ^[A-Z]'
    """
    current = schema
    for p in path:
        if isinstance(current, dict):
            if p in current.get("properties", {}):
                current = current["properties"][p]
            elif p in current:
                current = current[p]
        else:
            return "unknown requirements (invalid path)"

    # Extract requirements from current position
    requirements = []
    if isinstance(current, dict):
        if "type" in current:
            requirements.append(f"type: {current['type']}")
        if "required" in current:
            requirements.append(f"required fields: {', '.join(current['required'])}")
        if "pattern" in current:
            requirements.append(f"must match pattern: {current['pattern']}")
        if "enum" in current:
            requirements.append(
                f"must be one of: {', '.join(map(str, current['enum']))}"
            )
        if "minLength" in current:
            requirements.append(f"minimum length: {current['minLength']}")
        if "maxLength" in current:
            requirements.append(f"maximum length: {current['maxLength']}")
        if "minimum" in current:
            requirements.append(f"minimum value: {current['minimum']}")
        if "maximum" in current:
            requirements.append(f"maximum value: {current['maximum']}")

    return "; ".join(requirements) if requirements else "unknown requirements"


def validate_json_schema(
    data: dict | list | str,
    schema: dict,
    data_name: str = "data",
) -> Tuple[bool, Optional[str]]:
    """
    Validate data against JSON schema with detailed error messages.

    Args:
        data: Data to validate (dict, list, or JSON string)
        schema: JSON schema dict
        data_name: Name of the data for error messages (default: "data")

    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is None.

    Example:
        schema = {
            "type": "object",
            "required": ["name", "age"],
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer", "minimum": 0}
            }
        }

        valid, error = validate_json_schema({"name": "Alice", "age": 30}, schema)
        # Returns: (True, None)

        valid, error = validate_json_schema({"name": "Bob"}, schema)
        # Returns: (False, "Validation error in data: 'age' is a required property")
    """
    if not _JSONSCHEMA_AVAILABLE:
        return False, "jsonschema library not installed. Run: pip install jsonschema"

    # Parse JSON string if needed
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as e:
            return False, f"Invalid JSON in {data_name}: {e}"

    # Validate against schema
    try:
        jsonschema.validate(instance=data, schema=schema)
        return True, None
    except ValidationError as e:
        # Build detailed error message
        path = format_schema_path(list(e.absolute_path))
        path_str = f" at '{path}'" if path else ""

        # Get requirements for this field
        requirements = get_schema_requirements(schema, list(e.absolute_path))
        requirements_str = f" (Required: {requirements})" if requirements else ""

        error_msg = (
            f"Validation error in {data_name}{path_str}: "
            f"{e.message}{requirements_str}"
        )

        return False, error_msg
    except Exception as e:
        return False, f"Schema validation error: {type(e).__name__}: {e}"


# =========================================================================
# YAML Validation
# =========================================================================


def parse_yaml(
    yaml_content: Optional[str] = None,
    file_path: Optional[str | Path] = None,
) -> Tuple[Optional[dict], Optional[str]]:
    """
    Parse YAML content from string or file.

    Args:
        yaml_content: Direct YAML content string
        file_path: Path to file containing YAML

    Returns:
        Tuple of (parsed_data, error_message). If error_message is not None,
        parsed_data will be None.

    Example:
        data, error = parse_yaml(yaml_content="name: Alice\\nage: 30")
        # Returns: ({'name': 'Alice', 'age': 30}, None)

        data, error = parse_yaml(file_path="/tmp/config.yaml")
        # Reads and parses the file
    """
    if not _YAML_AVAILABLE:
        return None, "PyYAML library not installed. Run: pip install pyyaml"

    # Resolve content
    content, error = resolve_content_from_path(yaml_content, file_path)
    if error:
        return None, error

    # Parse YAML
    try:
        data = yaml.safe_load(content)
        if data is None:
            return None, "YAML content is empty or contains only comments"
        return data, None
    except yaml.YAMLError as e:
        # Extract line/column info if available
        if hasattr(e, "problem_mark"):
            mark = e.problem_mark
            error_msg = (
                f"YAML syntax error at line {mark.line + 1}, "
                f"column {mark.column + 1}: {e.problem}"
            )
        else:
            error_msg = f"YAML syntax error: {e}"
        return None, error_msg
    except Exception as e:
        return None, f"Error parsing YAML: {type(e).__name__}: {e}"


def validate_yaml_schema(
    yaml_content: Optional[str] = None,
    file_path: Optional[str | Path] = None,
    schema: Optional[dict] = None,
    data_name: str = "YAML",
) -> Tuple[bool, Optional[str], Optional[dict]]:
    """
    Parse YAML and optionally validate against JSON schema.

    Args:
        yaml_content: Direct YAML content string
        file_path: Path to file containing YAML (token-efficient!)
        schema: Optional JSON schema to validate against
        data_name: Name for error messages

    Returns:
        Tuple of (is_valid, error_message, parsed_data).
        If not valid, parsed_data will be None.

    Example:
        # Basic YAML parsing
        valid, error, data = validate_yaml_schema(
            file_path="/tmp/config.yaml"
        )

        # YAML parsing with schema validation
        schema = {
            "type": "object",
            "required": ["name"],
            "properties": {"name": {"type": "string"}}
        }
        valid, error, data = validate_yaml_schema(
            yaml_content="name: Alice",
            schema=schema
        )
    """
    # Parse YAML
    data, parse_error = parse_yaml(yaml_content, file_path)
    if parse_error:
        return False, parse_error, None

    # Validate against schema if provided
    if schema:
        valid, schema_error = validate_json_schema(data, schema, data_name)
        if not valid:
            return False, schema_error, None

    return True, None, data


# =========================================================================
# JSON Validation
# =========================================================================


def parse_json(
    json_content: Optional[str] = None,
    file_path: Optional[str | Path] = None,
) -> Tuple[Optional[dict | list], Optional[str]]:
    """
    Parse JSON content from string or file.

    Args:
        json_content: Direct JSON content string
        file_path: Path to file containing JSON

    Returns:
        Tuple of (parsed_data, error_message).
    """
    # Resolve content
    content, error = resolve_content_from_path(json_content, file_path)
    if error:
        return None, error

    # Parse JSON
    try:
        data = json.loads(content)
        return data, None
    except json.JSONDecodeError as e:
        error_msg = (
            f"JSON syntax error at line {e.lineno}, column {e.colno}: {e.msg}"
        )
        return None, error_msg
    except Exception as e:
        return None, f"Error parsing JSON: {type(e).__name__}: {e}"


def validate_json_file(
    json_content: Optional[str] = None,
    file_path: Optional[str | Path] = None,
    schema: Optional[dict] = None,
    data_name: str = "JSON",
) -> Tuple[bool, Optional[str], Optional[dict | list]]:
    """
    Parse JSON and optionally validate against schema.

    Args:
        json_content: Direct JSON content string
        file_path: Path to file containing JSON (token-efficient!)
        schema: Optional JSON schema to validate against
        data_name: Name for error messages

    Returns:
        Tuple of (is_valid, error_message, parsed_data).
    """
    # Parse JSON
    data, parse_error = parse_json(json_content, file_path)
    if parse_error:
        return False, parse_error, None

    # Validate against schema if provided
    if schema:
        valid, schema_error = validate_json_schema(data, schema, data_name)
        if not valid:
            return False, schema_error, None

    return True, None, data
