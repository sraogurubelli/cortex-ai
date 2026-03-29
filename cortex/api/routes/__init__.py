"""
API Routes Module

FastAPI route handlers for Cortex platform.

Core routes (enabled):
- auth: Authentication (signup, login, OAuth)
- accounts: Account management
- organizations: Organization CRUD
- projects: Project CRUD
- documents: Document upload and processing
- health: Health check endpoints

Non-core routes (disabled - can be added back incrementally):
- chat, chat_extensions, websocket_chat: Require Conversation, Message models
- audit_logs: Requires AuditLog model
- usage: Requires UsageRecord model
- feature_flags: Requires FeatureFlag model
- webhooks: Requires Webhook, WebhookDelivery models
- analytics: Requires Message model
"""

__all__ = []
