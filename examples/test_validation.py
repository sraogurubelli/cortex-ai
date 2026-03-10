"""
Test script for validation utilities.

Demonstrates:
1. Token-efficient file path validation
2. JSON Schema validation with detailed errors
3. YAML/JSON parsing and validation
4. Example agent tools using validation

Run with:
    python examples/test_validation.py
"""

import json
import tempfile
from pathlib import Path

from cortex.orchestration.validation import (
    format_schema_path,
    get_schema_requirements,
    parse_json,
    parse_yaml,
    resolve_content_from_path,
    validate_json_schema,
    validate_json_file,
    validate_yaml_schema,
)


# =========================================================================
# Demo 1: Token-Efficient File Path Resolution
# =========================================================================


def demo_file_path_resolution():
    """Demonstrate token-efficient validation using file paths."""
    print("=" * 70)
    print("Demo 1: Token-Efficient File Path Resolution")
    print("=" * 70)

    # Create temporary file with content
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        large_content = "# This is a large config file\n" + "key: value\n" * 100
        f.write(large_content)
        temp_path = f.name

    print(f"\n1. Direct content (uses ~{len(large_content)} tokens):")
    print(f"   Content length: {len(large_content)} characters")

    content1, error1 = resolve_content_from_path(content=large_content)
    print(f"   Result: {'✓ Success' if not error1 else f'✗ Error: {error1}'}")

    print(f"\n2. File path (uses only path length ~{len(temp_path)} tokens):")
    print(f"   Path: {temp_path}")
    print(f"   Token savings: ~{len(large_content) - len(temp_path)} tokens!")

    content2, error2 = resolve_content_from_path(file_path=temp_path)
    print(f"   Result: {'✓ Success' if not error2 else f'✗ Error: {error2}'}")
    print(f"   Content matches: {content1 == content2}")

    print("\n3. Error handling:")
    content3, error3 = resolve_content_from_path(file_path="/nonexistent/file.yaml")
    print(f"   Nonexistent file: {error3}")

    content4, error4 = resolve_content_from_path()
    print(f"   No arguments: {error4}")

    # Cleanup
    Path(temp_path).unlink()

    print("\n✓ File path resolution enables token-efficient validation!")


# =========================================================================
# Demo 2: JSON Schema Validation with Detailed Errors
# =========================================================================


def demo_json_schema_validation():
    """Demonstrate JSON schema validation with helpful error messages."""
    print("\n" + "=" * 70)
    print("Demo 2: JSON Schema Validation")
    print("=" * 70)

    # Define schema
    schema = {
        "type": "object",
        "required": ["name", "age", "email"],
        "properties": {
            "name": {
                "type": "string",
                "minLength": 1,
                "maxLength": 100,
            },
            "age": {
                "type": "integer",
                "minimum": 0,
                "maximum": 150,
            },
            "email": {
                "type": "string",
                "pattern": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
            },
            "role": {
                "type": "string",
                "enum": ["admin", "user", "guest"],
            },
        },
    }

    print("\n1. Valid data:")
    valid_data = {
        "name": "Alice Johnson",
        "age": 30,
        "email": "alice@example.com",
        "role": "admin",
    }
    valid, error = validate_json_schema(valid_data, schema, "user_data")
    print(f"   Data: {json.dumps(valid_data)}")
    print(f"   Result: {'✓ Valid' if valid else f'✗ Invalid: {error}'}")

    print("\n2. Missing required field:")
    invalid_data1 = {"name": "Bob", "age": 25}
    valid, error = validate_json_schema(invalid_data1, schema, "user_data")
    print(f"   Data: {json.dumps(invalid_data1)}")
    print(f"   Result: {'✓ Valid' if valid else f'✗ Invalid'}")
    print(f"   Error: {error}")

    print("\n3. Wrong type:")
    invalid_data2 = {"name": "Charlie", "age": "thirty", "email": "charlie@example.com"}
    valid, error = validate_json_schema(invalid_data2, schema, "user_data")
    print(f"   Data: {json.dumps(invalid_data2)}")
    print(f"   Result: {'✓ Valid' if valid else f'✗ Invalid'}")
    print(f"   Error: {error}")

    print("\n4. Pattern mismatch:")
    invalid_data3 = {"name": "Diana", "age": 28, "email": "not-an-email"}
    valid, error = validate_json_schema(invalid_data3, schema, "user_data")
    print(f"   Data: {json.dumps(invalid_data3)}")
    print(f"   Result: {'✓ Valid' if valid else f'✗ Invalid'}")
    print(f"   Error: {error}")

    print("\n5. Enum violation:")
    invalid_data4 = {
        "name": "Eve",
        "age": 35,
        "email": "eve@example.com",
        "role": "superadmin",
    }
    valid, error = validate_json_schema(invalid_data4, schema, "user_data")
    print(f"   Data: {json.dumps(invalid_data4)}")
    print(f"   Result: {'✓ Valid' if valid else f'✗ Invalid'}")
    print(f"   Error: {error}")

    print("\n✓ Detailed error messages help users fix validation issues!")


# =========================================================================
# Demo 3: YAML Validation
# =========================================================================


def demo_yaml_validation():
    """Demonstrate YAML parsing and schema validation."""
    print("\n" + "=" * 70)
    print("Demo 3: YAML Validation")
    print("=" * 70)

    schema = {
        "type": "object",
        "required": ["apiVersion", "kind", "metadata"],
        "properties": {
            "apiVersion": {"type": "string"},
            "kind": {"type": "string"},
            "metadata": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string"},
                    "labels": {"type": "object"},
                },
            },
        },
    }

    print("\n1. Valid YAML:")
    valid_yaml = """
apiVersion: v1
kind: ConfigMap
metadata:
  name: my-config
  labels:
    app: demo
"""
    valid, error, data = validate_yaml_schema(yaml_content=valid_yaml, schema=schema)
    print(f"   YAML:\n{valid_yaml}")
    print(f"   Result: {'✓ Valid' if valid else f'✗ Invalid: {error}'}")
    if data:
        print(f"   Parsed data: {json.dumps(data, indent=2)}")

    print("\n2. Invalid YAML (syntax error):")
    invalid_yaml = """
apiVersion: v1
kind: ConfigMap
metadata:
  name: my-config
  labels
    app: demo  # Missing colon after 'labels'
"""
    valid, error, data = validate_yaml_schema(yaml_content=invalid_yaml)
    print(f"   Result: {'✓ Valid' if valid else f'✗ Invalid'}")
    print(f"   Error: {error}")

    print("\n3. Valid YAML but fails schema:")
    invalid_yaml2 = """
apiVersion: v1
kind: ConfigMap
# Missing required 'metadata' field
data:
  key: value
"""
    valid, error, data = validate_yaml_schema(
        yaml_content=invalid_yaml2, schema=schema
    )
    print(f"   Result: {'✓ Valid YAML syntax' if data else '✗ Parse failed'}")
    print(f"   Schema validation: {'✓ Valid' if valid else f'✗ Invalid'}")
    print(f"   Error: {error}")

    print("\n✓ YAML validation catches both syntax and schema errors!")


# =========================================================================
# Demo 4: Example Agent Tool Using Validation
# =========================================================================


def demo_agent_tool_example():
    """Demonstrate how an agent tool would use validation."""
    print("\n" + "=" * 70)
    print("Demo 4: Example Agent Tool")
    print("=" * 70)

    # Simulate an agent tool that validates user configuration
    def validate_user_config(
        config_content: str | None = None, file_path: str | None = None
    ) -> str:
        """
        Agent tool: Validate user configuration file.

        Args:
            config_content: Direct YAML content (costs tokens)
            file_path: Path to config file (token-efficient!)

        Returns:
            Validation result message
        """
        schema = {
            "type": "object",
            "required": ["database", "server"],
            "properties": {
                "database": {
                    "type": "object",
                    "required": ["host", "port"],
                    "properties": {
                        "host": {"type": "string"},
                        "port": {"type": "integer", "minimum": 1, "maximum": 65535},
                        "username": {"type": "string"},
                    },
                },
                "server": {
                    "type": "object",
                    "required": ["port"],
                    "properties": {
                        "port": {"type": "integer", "minimum": 1, "maximum": 65535},
                        "host": {"type": "string", "default": "0.0.0.0"},
                    },
                },
            },
        }

        # Validate
        valid, error, data = validate_yaml_schema(
            yaml_content=config_content, file_path=file_path, schema=schema
        )

        if not valid:
            return f"❌ Configuration validation failed:\n{error}"

        return f"✅ Configuration is valid!\nParsed config: {json.dumps(data, indent=2)}"

    # Test with valid config
    print("\n1. Valid configuration:")
    valid_config = """
database:
  host: localhost
  port: 5432
  username: admin

server:
  port: 8080
  host: 0.0.0.0
"""
    result = validate_user_config(config_content=valid_config)
    print(result)

    # Test with invalid config
    print("\n2. Invalid configuration (port out of range):")
    invalid_config = """
database:
  host: localhost
  port: 99999  # Invalid port number!
  username: admin

server:
  port: 8080
"""
    result = validate_user_config(config_content=invalid_config)
    print(result)

    # Test with file path (token-efficient!)
    print("\n3. Validation using file path:")
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        f.write(valid_config)
        temp_path = f.name

    result = validate_user_config(file_path=temp_path)
    print(f"File path: {temp_path}")
    print(result)

    # Cleanup
    Path(temp_path).unlink()

    print("\n✓ Agent tools can use validation for helpful error messages!")


# =========================================================================
# Main
# =========================================================================


def main():
    """Run all validation demos."""
    print("\n" + "=" * 70)
    print("Cortex Orchestration SDK - Validation Utilities")
    print("=" * 70)

    demo_file_path_resolution()
    demo_json_schema_validation()
    demo_yaml_validation()
    demo_agent_tool_example()

    print("\n" + "=" * 70)
    print("All Validation Demos Complete!")
    print("=" * 70)
    print("\nKey Features:")
    print("  1. Token-efficient validation using file paths")
    print("  2. Detailed error messages with schema requirements")
    print("  3. YAML and JSON parsing with syntax error reporting")
    print("  4. Easy integration into agent tools")
    print("\nOptional dependencies:")
    print("  - jsonschema: pip install jsonschema")
    print("  - pyyaml: pip install pyyaml")


if __name__ == "__main__":
    main()
