"""
Semantic Memory - Domain-specific interaction memory for agents.

Provides PostgreSQL-backed or in-memory storage for compressed interaction
history, enabling agents to reference previous work without re-processing
full conversation history.

Key Features:
- 80%+ token reduction in multi-turn conversations
- TTL-based automatic expiry
- PostgreSQL or in-memory fallback
- Configurable compression

Example:
    from cortex.orchestration.memory import SemanticMemory

    memory = SemanticMemory()

    # Save interaction
    await memory.save_interaction(
        conversation_id="session-123",
        user_query="Find unpaid invoices",
        agent_reasoning="Need to search by status",
        key_decisions=["Use search_invoices tool"],
        tools_used=[...],
        outcome="Found 42 unpaid invoices"
    )

    # Load previous context
    interactions = await memory.load_context("session-123")

    # Format for LLM
    context = memory.format_for_llm(interactions)
"""

import json
import logging
import time
from typing import Any

from cortex.orchestration.memory.types import (
    MemoryConfig,
    PreviousInteraction,
    ToolExecution,
)
from cortex.orchestration.memory.formatters import (
    format_interactions_for_llm,
    truncate_interaction,
)

logger = logging.getLogger(__name__)

# In-memory fallback when PostgreSQL is not available
_memory_store: dict[str, str] = {}


class SemanticMemory:
    """
    Semantic memory storage for agent interactions.

    Stores compressed interaction history with TTL-based expiry.
    Uses PostgreSQL when available, falls back to in-memory storage.

    Example:
        # Initialize
        memory = SemanticMemory(
            config=MemoryConfig(
                max_interactions_per_conversation=5,
                ttl_seconds=3600  # 1 hour
            )
        )

        # Save interaction
        await memory.save_interaction(
            conversation_id="conv-123",
            user_query="Find all invoices",
            agent_reasoning="Search by date range",
            key_decisions=["Use last 30 days"],
            tools_used=[tool_exec],
            outcome="Found 156 invoices"
        )

        # Load context
        interactions = await memory.load_context("conv-123")

        # Format for agent
        context = memory.format_for_llm(interactions)
        agent = Agent(system_prompt=f"{base_prompt}\\n\\n{context}")
    """

    def __init__(self, config: MemoryConfig | None = None):
        """
        Initialize semantic memory.

        Args:
            config: Memory configuration (uses defaults if not provided)
        """
        self.config = config or MemoryConfig()
        logger.debug(f"Initialized SemanticMemory with config: {self.config.to_dict()}")

    async def save_interaction(
        self,
        conversation_id: str,
        user_query: str,
        agent_reasoning: str,
        key_decisions: list[str],
        tools_used: list[ToolExecution],
        outcome: str,
        confidence: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Save a compressed interaction for future reference.

        Args:
            conversation_id: Unique conversation identifier
            user_query: User's original query
            agent_reasoning: Agent's reasoning process
            key_decisions: List of key decisions made
            tools_used: List of tool executions
            outcome: Final outcome/result
            confidence: Confidence score (0-1)
            metadata: Optional metadata dict

        Example:
            await memory.save_interaction(
                conversation_id="session-123",
                user_query="Show me overdue payments",
                agent_reasoning="Need to filter by due date and payment status",
                key_decisions=[
                    "Search payments with status=pending",
                    "Filter by due_date < today"
                ],
                tools_used=[
                    ToolExecution(
                        tool_name="search_payments",
                        parameters={"status": "pending"},
                        result_summary="Found 23 overdue payments",
                        success=True
                    )
                ],
                outcome="Successfully identified 23 overdue payments totaling $45K",
                confidence=0.95
            )
        """
        try:
            interaction = PreviousInteraction(
                timestamp=time.time(),
                user_query=user_query,
                agent_reasoning=agent_reasoning,
                key_decisions=key_decisions,
                tools_used=tools_used,
                outcome=outcome,
                confidence=confidence,
                metadata=metadata or {},
            )

            # Auto-compress if enabled and exceeds token limit
            if self.config.auto_compress:
                if interaction.estimate_tokens() > self.config.max_tokens_per_interaction:
                    interaction = truncate_interaction(
                        interaction, self.config.max_tokens_per_interaction
                    )
                    logger.debug(
                        f"Auto-compressed interaction to {interaction.estimate_tokens()} tokens"
                    )

            # Load existing interactions
            thread_id = self._build_thread_id(conversation_id)
            existing = await self._load_raw(thread_id)

            # Append new interaction
            existing.append(interaction.to_dict())

            # Limit to max interactions
            existing = existing[-self.config.max_interactions_per_conversation :]

            # Save back to storage
            await self._save_raw(thread_id, self._serialize(existing))

            logger.info(
                f"Saved semantic memory for conversation {conversation_id} "
                f"({len(existing)} interactions, {interaction.estimate_tokens()} tokens)"
            )

        except Exception as e:
            logger.exception(f"Failed to save interaction: {e}")

    async def load_context(
        self,
        conversation_id: str,
        max_interactions: int | None = None,
    ) -> list[PreviousInteraction]:
        """
        Load previous interactions for a conversation.

        Automatically filters out expired interactions based on TTL.

        Args:
            conversation_id: Conversation to load context for
            max_interactions: Override default max interactions

        Returns:
            list[PreviousInteraction]: Previous interactions (oldest first)

        Example:
            interactions = await memory.load_context("session-123")
            if interactions:
                context = memory.format_for_llm(interactions)
                # Inject into agent prompt
        """
        try:
            thread_id = self._build_thread_id(conversation_id)
            interactions_data = await self._load_raw(thread_id)

            if not interactions_data:
                return []

            # Filter expired interactions (TTL check)
            now = time.time()
            interactions_data = [
                i
                for i in interactions_data
                if now - i.get("timestamp", 0) < self.config.ttl_seconds
            ]

            if not interactions_data:
                logger.debug(f"No valid interactions found for {conversation_id} (all expired)")
                return []

            # Limit to max interactions
            max_count = max_interactions or self.config.max_interactions_per_conversation
            interactions_data = interactions_data[-max_count:]

            # Convert to PreviousInteraction objects
            interactions = [
                PreviousInteraction.from_dict(data) for data in interactions_data
            ]

            logger.info(
                f"Loaded {len(interactions)} interactions for conversation {conversation_id}"
            )
            return interactions

        except Exception as e:
            logger.exception(f"Failed to load context: {e}")
            return []

    def format_for_llm(
        self,
        interactions: list[PreviousInteraction],
        include_reasoning: bool = True,
        include_tools: bool = True,
    ) -> str:
        """
        Format interactions as LLM-readable context.

        Args:
            interactions: Interactions to format
            include_reasoning: Include agent reasoning
            include_tools: Include tool execution details

        Returns:
            str: Formatted context string

        Example:
            interactions = await memory.load_context("session-123")
            context = memory.format_for_llm(interactions)
            system_prompt = f"{base_prompt}\\n\\n{context}"
        """
        return format_interactions_for_llm(
            interactions,
            include_reasoning=include_reasoning,
            include_tools=include_tools,
            include_metadata=self.config.enable_metadata,
        )

    async def clear_conversation(self, conversation_id: str) -> None:
        """
        Clear all interactions for a conversation.

        Args:
            conversation_id: Conversation to clear

        Example:
            await memory.clear_conversation("session-123")
        """
        try:
            thread_id = self._build_thread_id(conversation_id)
            await self._save_raw(thread_id, self._serialize([]))
            logger.info(f"Cleared semantic memory for conversation {conversation_id}")
        except Exception as e:
            logger.exception(f"Failed to clear conversation: {e}")

    async def get_statistics(self, conversation_id: str) -> dict[str, Any]:
        """
        Get statistics about stored interactions.

        Args:
            conversation_id: Conversation to get stats for

        Returns:
            dict: Statistics including count, total tokens, etc.

        Example:
            stats = await memory.get_statistics("session-123")
            print(f"Stored {stats['interaction_count']} interactions")
            print(f"Total tokens: {stats['total_tokens']}")
        """
        interactions = await self.load_context(conversation_id)

        total_tokens = sum(i.estimate_tokens() for i in interactions)
        successful_tools = sum(
            1 for i in interactions for t in i.tools_used if t.success
        )
        total_tools = sum(len(i.tools_used) for i in interactions)

        return {
            "conversation_id": conversation_id,
            "interaction_count": len(interactions),
            "total_tokens": total_tokens,
            "avg_tokens_per_interaction": total_tokens // len(interactions)
            if interactions
            else 0,
            "total_tools_used": total_tools,
            "successful_tools": successful_tools,
            "tool_success_rate": successful_tools / total_tools if total_tools > 0 else 0,
            "oldest_interaction": datetime.fromtimestamp(interactions[0].timestamp).isoformat()
            if interactions
            else None,
            "newest_interaction": datetime.fromtimestamp(
                interactions[-1].timestamp
            ).isoformat()
            if interactions
            else None,
        }

    # -------------------------------------------------------------------------
    # Private methods
    # -------------------------------------------------------------------------

    def _build_thread_id(self, conversation_id: str) -> str:
        """Build thread ID for storage."""
        return f"semantic_memory:{conversation_id}"

    def _serialize(self, interactions: list[dict]) -> str:
        """Serialize interactions to JSON."""
        return json.dumps({"interactions": interactions})

    def _deserialize(self, data: str) -> list[dict]:
        """Deserialize interactions from JSON."""
        try:
            parsed = json.loads(data)
            return parsed.get("interactions", [])
        except (json.JSONDecodeError, TypeError):
            return []

    async def _get_pool(self) -> Any:
        """Get PostgreSQL connection pool from checkpointer infrastructure."""
        try:
            from cortex.orchestration.session.checkpointer import (
                _pool,
                is_checkpointing_enabled,
            )

            if is_checkpointing_enabled() and _pool is not None:
                return _pool
        except ImportError:
            pass
        return None

    async def _load_raw(self, thread_id: str) -> list[dict]:
        """Load raw interactions list from storage."""
        pool = await self._get_pool()

        # Try PostgreSQL first
        if pool is not None:
            try:
                async with pool.connection() as conn:
                    row = await conn.fetchrow(
                        "SELECT data FROM semantic_memory WHERE thread_id = $1",
                        thread_id,
                    )
                    if row:
                        return self._deserialize(row["data"])
                    return []
            except Exception as e:
                logger.warning(
                    f"PostgreSQL load failed, using memory fallback: {e}",
                    exc_info=True,
                )

        # Fallback to in-memory
        data = _memory_store.get(thread_id)
        if data:
            return self._deserialize(data)
        return []

    async def _save_raw(self, thread_id: str, data: str) -> None:
        """Save raw data to storage."""
        pool = await self._get_pool()

        # Try PostgreSQL first
        if pool is not None:
            try:
                async with pool.connection() as conn:
                    await conn.execute(
                        """
                        INSERT INTO semantic_memory (thread_id, data, updated_at)
                        VALUES ($1, $2, NOW())
                        ON CONFLICT (thread_id)
                        DO UPDATE SET data = $2, updated_at = NOW()
                        """,
                        thread_id,
                        data,
                    )
                    return
            except Exception as e:
                logger.warning(
                    f"PostgreSQL save failed, using memory fallback: {e}",
                    exc_info=True,
                )

        # Fallback to in-memory
        _memory_store[thread_id] = data


# Import for datetime formatting
from datetime import datetime
