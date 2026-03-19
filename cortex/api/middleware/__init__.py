"""
API Middleware Module

FastAPI middleware for:
- Authentication
- Request logging
- Request ID propagation
"""

from cortex.api.middleware.auth import (
    AuthenticationMiddleware,
    get_current_principal,
    require_authentication,
    require_admin,
)

__all__ = [
    "AuthenticationMiddleware",
    "get_current_principal",
    "require_authentication",
    "require_admin",
]
