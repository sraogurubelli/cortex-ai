"""
Semantic Memory for Cortex AI Agents

Provides multi-layered memory capabilities for agents to remember and build
upon previous interactions across conversation turns.

Current Implementation:
- Layer 2: Semantic Memory (compressed interaction history)
- PostgreSQL or in-memory storage
- TTL-based expiry
- 80%+ token reduction in multi-turn conversations

Future Layers:
- Layer 3: Knowledge Memory (long-term entity knowledge, Neo4j/Vector DB)

Quick Start:
    from cortex.orchestration.memory import SemanticMemory, MemoryConfig

    # Initialize memory
    memory = SemanticMemory(
        config=MemoryConfig(
            max_interactions_per_conversation=5,
            ttl_seconds=3600  # 1 hour
        )
    )

    # Save interaction
    await memory.save_interaction(
        conversation_id="session-123",
        user_query="Find invoices",
        agent_reasoning="Search by date",
        key_decisions=["Use last 30 days"],
        tools_used=[...],
        outcome="Found 156 invoices"
    )

    # Load and format for LLM
    interactions = await memory.load_context("session-123")
    context = memory.format_for_llm(interactions)

    # Inject into agent
    agent = Agent(system_prompt=f"{base_prompt}\\n\\n{context}")
"""

from cortex.orchestration.memory.types import (
    MemoryConfig,
    PreviousInteraction,
    ToolExecution,
)
from cortex.orchestration.memory.semantic import SemanticMemory
from cortex.orchestration.memory.formatters import (
    format_interactions_for_llm,
    format_interaction_summary,
    format_tools_for_llm,
    truncate_interaction,
)

__all__ = [
    # Core classes
    "SemanticMemory",
    # Data types
    "MemoryConfig",
    "PreviousInteraction",
    "ToolExecution",
    # Formatters
    "format_interactions_for_llm",
    "format_interaction_summary",
    "format_tools_for_llm",
    "truncate_interaction",
]
