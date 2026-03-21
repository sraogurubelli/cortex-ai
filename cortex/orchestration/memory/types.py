"""
Memory data structures for semantic context storage.

Defines types for storing compressed interaction history that agents
can reference across conversation turns without re-processing full history.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolExecution:
    """
    Record of a single tool execution.

    Stores compressed summary of tool execution, not full results,
    to minimize token usage when injecting context.

    Example:
        ToolExecution(
            tool_name="search_invoices",
            parameters={"status": "unpaid", "limit": 50},
            result_summary="Found 42 unpaid invoices totaling $125,340",
            success=True,
            execution_time_ms=234
        )
    """

    tool_name: str
    parameters: dict[str, Any]
    result_summary: str
    success: bool
    execution_time_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "tool_name": self.tool_name,
            "parameters": self.parameters,
            "result_summary": self.result_summary,
            "success": self.success,
            "execution_time_ms": self.execution_time_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolExecution":
        """Create from dictionary."""
        return cls(
            tool_name=data["tool_name"],
            parameters=data["parameters"],
            result_summary=data["result_summary"],
            success=data["success"],
            execution_time_ms=data.get("execution_time_ms"),
        )


@dataclass
class PreviousInteraction:
    """
    Compressed context from a previous agent interaction.

    Stores key information from a conversation turn: what was asked,
    how the agent reasoned, what tools were used, and what was decided.

    This compressed format allows agents to reference previous context
    without reloading full conversation history, reducing token usage
    by 80%+ in multi-turn conversations.

    Example:
        PreviousInteraction(
            timestamp=1234567890.0,
            user_query="Find all unpaid invoices for ACME Corp",
            agent_reasoning="Need to search by customer name and payment status",
            key_decisions=[
                "Search invoices with status=unpaid",
                "Filter by customer_name=ACME Corp",
                "Prioritize by due date"
            ],
            tools_used=[
                ToolExecution(
                    tool_name="search_invoices",
                    parameters={"customer": "ACME", "status": "unpaid"},
                    result_summary="Found 42 unpaid invoices totaling $125,340",
                    success=True
                )
            ],
            outcome="Successfully identified 42 unpaid invoices. Oldest is 90 days overdue.",
            confidence=0.95,
            metadata={"thread_id": "session-123", "agent_name": "billing-agent"}
        )
    """

    timestamp: float
    user_query: str
    agent_reasoning: str
    key_decisions: list[str]
    tools_used: list[ToolExecution]
    outcome: str
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "user_query": self.user_query,
            "agent_reasoning": self.agent_reasoning,
            "key_decisions": self.key_decisions,
            "tools_used": [t.to_dict() for t in self.tools_used],
            "outcome": self.outcome,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PreviousInteraction":
        """Create from dictionary."""
        tools = [ToolExecution.from_dict(t) for t in data.get("tools_used", [])]
        return cls(
            timestamp=data["timestamp"],
            user_query=data["user_query"],
            agent_reasoning=data["agent_reasoning"],
            key_decisions=data.get("key_decisions", []),
            tools_used=tools,
            outcome=data["outcome"],
            confidence=data.get("confidence", 1.0),
            metadata=data.get("metadata", {}),
        )

    def estimate_tokens(self) -> int:
        """
        Estimate token count for this interaction (rough approximation).

        Returns:
            int: Estimated number of tokens
        """
        text = (
            f"{self.user_query} {self.agent_reasoning} "
            f"{' '.join(self.key_decisions)} {self.outcome}"
        )
        for tool in self.tools_used:
            text += f" {tool.result_summary}"

        # Rough approximation: 1 token ≈ 4 characters
        return len(text) // 4


@dataclass
class MemoryConfig:
    """
    Configuration for semantic memory behavior.

    Controls how many interactions to store, TTL, compression settings, etc.

    Example:
        MemoryConfig(
            max_interactions_per_conversation=5,
            ttl_seconds=3600,  # 1 hour
            auto_compress=True,
            max_tokens_per_interaction=500
        )
    """

    max_interactions_per_conversation: int = 5
    ttl_seconds: int = 3600  # 1 hour default
    auto_compress: bool = True
    max_tokens_per_interaction: int = 500
    enable_metadata: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "max_interactions_per_conversation": self.max_interactions_per_conversation,
            "ttl_seconds": self.ttl_seconds,
            "auto_compress": self.auto_compress,
            "max_tokens_per_interaction": self.max_tokens_per_interaction,
            "enable_metadata": self.enable_metadata,
        }
