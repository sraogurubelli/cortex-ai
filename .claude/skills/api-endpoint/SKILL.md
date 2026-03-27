---
name: api-endpoint
description: Create FastAPI Chat API endpoints with SSE streaming. Auto-activates when working with API routes.
paths:
  - "cortex/api/**/*.py"
  - "tests/api/**/*.py"
allowed-tools: Read, Grep, Glob, Edit
model: sonnet
effort: medium
---

# API Endpoint Development

## Purpose

Create new FastAPI endpoints for the Chat API with proper validation, authentication, and SSE streaming.

## When to Use This Skill

**Auto-activates when:**
- Creating new API endpoints in `cortex/api/routes/`
- Adding SSE streaming endpoints
- Writing API tests
- Debugging API errors

**Manual invoke:** `/api-endpoint`

---

## Endpoint Creation Workflow

### Step 1: Define Pydantic Schemas

```python
from pydantic import BaseModel, Field, validator, constr
from typing import Optional

class ChatRequest(BaseModel):
    """Chat request schema."""

    message: constr(min_length=1, max_length=10000) = Field(
        ...,
        description="User message",
        example="What is the capital of France?",
    )
    session_id: constr(regex=r"^[a-zA-Z0-9-]+$") = Field(
        ...,
        description="Session identifier",
        example="session-abc-123",
    )
    model: Optional[str] = Field(
        default="gpt-4o",
        description="LLM model to use",
    )

    @validator("message")
    def message_not_empty(cls, v: str) -> str:
        """Validate message is not empty after stripping."""
        if not v.strip():
            raise ValueError("Message cannot be empty")
        return v.strip()

class ChatResponse(BaseModel):
    """Chat response schema."""

    message: str = Field(..., description="Agent response")
    session_id: str = Field(..., description="Session identifier")
    tokens: dict = Field(..., description="Token usage by model")
```

### Step 2: Create Route Handler

```python
from fastapi import APIRouter, HTTPException, Depends, status
from cortex.api.schemas import ChatRequest, ChatResponse
from cortex.api.dependencies import get_current_user, get_agent_service

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

@router.post("/", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def chat_endpoint(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> ChatResponse:
    """Chat endpoint.

    Args:
        request: Chat request with message and session_id
        current_user: Authenticated user from JWT token
        agent_service: Injected agent service

    Returns:
        ChatResponse with agent's reply

    Raises:
        HTTPException: 400 for invalid input, 500 for server errors
    """
    try:
        result = await agent_service.process_message(
            message=request.message,
            session_id=request.session_id,
            user_id=current_user.id,
        )
        return ChatResponse(
            message=result.response,
            session_id=request.session_id,
            tokens=result.token_usage,
        )
    except ValueError as e:
        logger.error(f"Invalid request: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Chat failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
```

### Step 3: Add SSE Streaming (Optional)

```python
from fastapi import StreamingResponse
from cortex.api.streaming import SSEWriter

@router.post("/stream")
async def chat_stream_endpoint(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> StreamingResponse:
    """Streaming chat endpoint with SSE."""
    async def generate():
        writer = SSEWriter()

        try:
            await agent_service.stream_response(
                message=request.message,
                session_id=request.session_id,
                user_id=current_user.id,
                stream_writer=writer,
            )
        except Exception as e:
            logger.error(f"Streaming error: {e}", exc_info=True)
            yield writer.format_error(str(e))
        finally:
            await writer.close()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
```

### Step 4: Add OpenAPI Documentation

```python
@router.post(
    "/",
    response_model=ChatResponse,
    summary="Send chat message",
    description="Send a message to the AI assistant and receive a response.",
    responses={
        200: {
            "description": "Successful response",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Hello! How can I help you today?",
                        "session_id": "session-abc-123",
                        "tokens": {
                            "gpt-4o": {
                                "prompt_tokens": 50,
                                "completion_tokens": 15,
                                "total_tokens": 65,
                            }
                        },
                    }
                }
            },
        },
        400: {"description": "Invalid request"},
        401: {"description": "Unauthorized"},
        500: {"description": "Internal server error"},
    },
)
async def chat_endpoint(...):
    pass
```

### Step 5: Write Tests

```python
import pytest
from httpx import AsyncClient
from cortex.api.app import app

@pytest.mark.asyncio
async def test_chat_endpoint_success():
    """Test successful chat request."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/chat",
            json={
                "message": "Hello",
                "session_id": "test-session",
            },
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert data["session_id"] == "test-session"

@pytest.mark.asyncio
async def test_chat_endpoint_validation_error():
    """Test validation error for empty message."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/chat",
            json={
                "message": "",  # Invalid
                "session_id": "test-session",
            },
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 400
```

---

## Authentication Pattern

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
import os

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """Extract and validate user from JWT token."""
    try:
        token = credentials.credentials
        payload = jwt.decode(
            token,
            os.getenv("JWT_SECRET_KEY"),
            algorithms=["HS256"],
        )
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )
        user = await user_service.get_by_id(user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )
        return user
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
```

---

## Error Response Format

**Standard format:**

```python
{
    "error": "error_code",
    "message": "Human-readable message",
    "details": {"field": "session_id", "issue": "Invalid format"}
}
```

**Custom exception handler:**

```python
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Handle validation errors."""
    return JSONResponse(
        status_code=400,
        content={
            "error": "validation_error",
            "message": str(exc),
            "details": {},
        },
    )
```

---

## Best Practices

### ✅ Do
- Use Pydantic models for request/response validation
- Include proper error handling with standard format
- Use dependency injection for authentication
- Add OpenAPI documentation with examples
- Write integration tests for all endpoints
- Return appropriate HTTP status codes

### ❌ Don't
- Skip input validation
- Return inconsistent error formats
- Hardcode authentication tokens
- Forget to log errors with context
- Skip rate limiting for public endpoints
- Return stack traces to clients

---

## Common HTTP Status Codes

| Code | Use Case | Example |
|------|----------|---------|
| 200 | Success | Chat response returned |
| 201 | Created | New session created |
| 400 | Bad Request | Invalid input (empty message) |
| 401 | Unauthorized | Missing or invalid token |
| 403 | Forbidden | Valid token, no permission |
| 404 | Not Found | Session not found |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Agent execution failed |

---

## Reference Files

- [FastAPI App](../../../cortex/api/app.py)
- [API Routes](../../../cortex/api/routes/)
- [Schemas](../../../cortex/api/schemas.py)
- [Dependencies](../../../cortex/api/dependencies.py)
- [Chat API Docs](../../../docs/CHAT_API.md)

---

**Need more help?** Check `.claude/rules/api.md` for detailed guidelines.
