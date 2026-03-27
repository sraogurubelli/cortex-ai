---
description: Generate FastAPI endpoint with schemas, validation, tests, and documentation
---

You will create a new API endpoint in cortex-ai based on the provided specification.

## Input Format

```yaml
endpointName: DataAnalysis           # PascalCase name
path: /api/v1/analysis               # API path
method: POST                          # HTTP method (GET, POST, PUT, DELETE)
description: Analyze data and return insights
requiresAuth: true                    # Whether endpoint requires authentication
requestSchema:
  - name: data
    type: dict
    required: true
    description: Data to analyze
  - name: model
    type: str
    required: false
    default: "gpt-4o"
    description: Model to use
responseSchema:
  - name: analysis
    type: str
    description: Analysis results
  - name: confidence
    type: float
    description: Confidence score
```

## Files to Create/Modify

### 1. Request/Response Schemas

**Path:** `cortex/api/schemas.py`

Add to existing file:

```python
class {endpointName}Request(BaseModel):
    """Request schema for {endpointName} endpoint."""

    # For each field in requestSchema:
    {field_name}: {field_type} = Field(
        ...,  # or default={field_default} if not required
        description="{field_description}",
        example="example value",
    )

    @validator("{field_name}")
    def {field_name}_validator(cls, v):
        """Validate {field_name}."""
        # Add validation logic if needed
        return v

    class Config:
        json_schema_extra = {
            "example": {
                # Example request
            }
        }


class {endpointName}Response(BaseModel):
    """Response schema for {endpointName} endpoint."""

    # For each field in responseSchema:
    {field_name}: {field_type} = Field(
        ...,
        description="{field_description}",
        example="example value",
    )

    class Config:
        json_schema_extra = {
            "example": {
                # Example response
            }
        }
```

### 2. Route Handler

**Path:** `cortex/api/routes/{module_name}.py`

Create new file if needed, or add to existing:

```python
"""
{endpointName} API routes
"""

from fastapi import APIRouter, HTTPException, Depends, status
from cortex.api.schemas import {endpointName}Request, {endpointName}Response
from cortex.api.dependencies import get_current_user  # If requiresAuth
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1",
    tags=["{module_name}"],
)


@router.{method.lower()}(
    "{path}",
    response_model={endpointName}Response,
    status_code=status.HTTP_200_OK,
    summary="{description}",
    description="{description}",
    responses={
        200: {
            "description": "Successful response",
            "content": {
                "application/json": {
                    "example": {
                        # Response example
                    }
                }
            },
        },
        400: {"description": "Invalid request"},
        401: {"description": "Unauthorized"},  # If requiresAuth
        500: {"description": "Internal server error"},
    },
)
async def {endpoint_name}_endpoint(
    request: {endpointName}Request,
    current_user: User = Depends(get_current_user),  # If requiresAuth
) -> {endpointName}Response:
    """{description}

    Args:
        request: Request with {fields}
        current_user: Authenticated user

    Returns:
        {endpointName}Response with results

    Raises:
        HTTPException: 400 for invalid input, 500 for server errors
    """
    try:
        # TODO: Implement endpoint logic
        # Example:
        # result = await service.process(request.data)

        return {endpointName}Response(
            # Fill response fields
        )

    except ValueError as e:
        logger.error(f"Validation error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Endpoint failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
```

### 3. Register Router

**Path:** `cortex/api/app.py`

Add to existing app:

```python
from cortex.api.routes import {module_name}

app.include_router({module_name}.router)
```

### 4. Tests

**Path:** `tests/api/test_{module_name}.py`

```python
"""
Tests for {endpointName} endpoint
"""

import pytest
from httpx import AsyncClient
from cortex.api.app import app


@pytest.mark.asyncio
async def test_{endpoint_name}_success():
    """Test successful {endpointName} request."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.{method.lower()}(
            "{path}",
            json={
                # Request data
            },
            headers={"Authorization": "Bearer test-token"},  # If requiresAuth
        )

    assert response.status_code == 200
    data = response.json()
    # Add assertions for response fields
    assert "field_name" in data


@pytest.mark.asyncio
async def test_{endpoint_name}_validation_error():
    """Test validation error for invalid input."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.{method.lower()}(
            "{path}",
            json={
                # Invalid data
            },
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 400
    data = response.json()
    assert "error" in data


@pytest.mark.asyncio
async def test_{endpoint_name}_unauthorized():
    """Test unauthorized request without token."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.{method.lower()}(
            "{path}",
            json={
                # Valid data
            },
            # No Authorization header
        )

    assert response.status_code == 403  # Or 401 depending on setup


@pytest.mark.asyncio
async def test_{endpoint_name}_internal_error():
    """Test internal server error handling."""
    # Mock service to raise exception
    # Test error handling
    pass
```

### 5. Documentation

**Path:** `docs/api/{module_name}.md`

```markdown
# {endpointName} API

{description}

## Endpoint

**{method} `{path}`**

## Authentication

{If requiresAuth: "Requires JWT token in Authorization header"}
{Else: "No authentication required"}

## Request Schema

\```json
{
  // Example request
}
\```

### Parameters

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| {field_name} | {field_type} | {required} | {description} |

## Response Schema

\```json
{
  // Example response
}
\```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| {field_name} | {field_type} | {description} |

## Error Responses

### 400 Bad Request
\```json
{
  "error": "validation_error",
  "message": "Invalid input",
  "details": {}
}
\```

### 401 Unauthorized
\```json
{
  "error": "unauthorized",
  "message": "Invalid or missing token",
  "details": {}
}
\```

### 500 Internal Server Error
\```json
{
  "error": "internal_error",
  "message": "An internal error occurred",
  "details": {}
}
\```

## Examples

### cURL

\```bash
curl -X {METHOD} "{path}" \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer YOUR_TOKEN" \\
  -d '{
    // Request data
  }'
\```

### Python

\```python
import httpx

async with httpx.AsyncClient() as client:
    response = await client.{method.lower()}(
        "http://localhost:8000{path}",
        json={
            // Request data
        },
        headers={"Authorization": "Bearer YOUR_TOKEN"},
    )
    data = response.json()
    print(data)
\```

### JavaScript

\```javascript
const response = await fetch("http://localhost:8000{path}", {
  method: "{METHOD}",
  headers: {
    "Content-Type": "application/json",
    "Authorization": "Bearer YOUR_TOKEN",
  },
  body: JSON.stringify({
    // Request data
  }),
});

const data = await response.json();
console.log(data);
\```

## Rate Limiting

- Limit: 100 requests per minute per user
- Reset: 60 seconds

## Notes

- {Add any additional notes}
```

## Checklist

After creating all files, verify:

- [ ] Request schema added to `cortex/api/schemas.py`
- [ ] Response schema added to `cortex/api/schemas.py`
- [ ] Route handler created in `cortex/api/routes/{module_name}.py`
- [ ] Router registered in `cortex/api/app.py`
- [ ] Tests created with all scenarios (success, validation, auth, error)
- [ ] Documentation created
- [ ] OpenAPI docs generated correctly (check `/docs`)
- [ ] All tests pass: `pytest tests/api/test_{module_name}.py -v`
- [ ] Endpoint accessible: `curl http://localhost:8000{path}`

## Next Steps

1. Implement endpoint business logic
2. Add integration with services/agents
3. Add rate limiting if needed
4. Update API changelog
5. Test with real requests
