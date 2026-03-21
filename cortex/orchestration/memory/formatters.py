"""
Context formatters for converting memory to LLM-readable text.

Provides functions to format PreviousInteraction objects into
context strings that can be injected into agent prompts.
"""

from datetime import datetime
from typing import Any

from cortex.orchestration.memory.types import PreviousInteraction, ToolExecution


def format_interactions_for_llm(
    interactions: list[PreviousInteraction],
    include_reasoning: bool = True,
    include_tools: bool = True,
    include_metadata: bool = False,
) -> str:
    """
    Format previous interactions as LLM-readable context.

    Converts compressed interaction history into a structured format
    that agents can use to understand previous work and build upon it.

    Args:
        interactions: List of previous interactions to format
        include_reasoning: Include agent reasoning in output
        include_tools: Include tool execution details
        include_metadata: Include metadata fields

    Returns:
        str: Formatted context string for injection into agent prompt

    Example:
        >>> interactions = [interaction1, interaction2]
        >>> context = format_interactions_for_llm(interactions)
        >>> system_prompt = f"{base_prompt}\\n\\n{context}"
        >>> agent = Agent(system_prompt=system_prompt)
    """
    if not interactions:
        return ""

    parts = [
        "═" * 70,
        "PREVIOUS INTERACTIONS IN THIS CONVERSATION",
        "═" * 70,
        "",
        "The user has continued the conversation with follow-up questions.",
        "Build upon the work already done — do NOT repeat the same analysis.",
        "Reference previous findings when relevant.",
        "",
    ]

    for i, interaction in enumerate(interactions, 1):
        # Timestamp
        timestamp_str = datetime.fromtimestamp(interaction.timestamp).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        parts.append(f"{'─' * 70}")
        parts.append(f"INTERACTION {i} ({timestamp_str})")
        parts.append(f"{'─' * 70}")

        # User query
        parts.append(f"**User Query:** \"{interaction.user_query}\"")
        parts.append("")

        # Agent reasoning (if enabled)
        if include_reasoning and interaction.agent_reasoning:
            parts.append(f"**Agent Reasoning:** {interaction.agent_reasoning}")
            parts.append("")

        # Key decisions
        if interaction.key_decisions:
            parts.append("**Key Decisions:**")
            for decision in interaction.key_decisions:
                parts.append(f"  • {decision}")
            parts.append("")

        # Tools used (if enabled)
        if include_tools and interaction.tools_used:
            parts.append(f"**Tools Executed ({len(interaction.tools_used)}):**")
            for tool in interaction.tools_used:
                parts.append(f"  • **{tool.tool_name}**")
                if tool.parameters:
                    params_str = ", ".join(
                        f"{k}={v}" for k, v in tool.parameters.items()
                    )
                    parts.append(f"    Parameters: {params_str}")
                parts.append(f"    Result: {tool.result_summary}")
                status = "✓ Success" if tool.success else "✗ Failed"
                parts.append(f"    Status: {status}")
            parts.append("")

        # Outcome
        parts.append(f"**Outcome:** {interaction.outcome}")

        # Confidence
        if interaction.confidence < 1.0:
            confidence_pct = int(interaction.confidence * 100)
            parts.append(f"**Confidence:** {confidence_pct}%")

        # Metadata (if enabled)
        if include_metadata and interaction.metadata:
            parts.append(f"**Metadata:** {interaction.metadata}")

        parts.append("")

    # Footer instructions
    parts.append("═" * 70)
    parts.append("INSTRUCTIONS")
    parts.append("═" * 70)
    parts.append("")
    parts.append("Use the above context to:")
    parts.append("  1. Avoid redundant work (don't repeat the same queries/analysis)")
    parts.append("  2. Build on previous findings (reference them in your response)")
    parts.append("  3. Address new aspects of the user's question")
    parts.append(
        "  4. Maintain continuity (acknowledge what was already discovered)"
    )
    parts.append("")

    return "\n".join(parts)


def format_interaction_summary(interaction: PreviousInteraction) -> str:
    """
    Format a single interaction as a brief summary.

    Useful for logging, debugging, or condensed context injection.

    Args:
        interaction: Interaction to summarize

    Returns:
        str: Brief summary (1-2 lines)

    Example:
        >>> summary = format_interaction_summary(interaction)
        >>> print(summary)
        "User asked about unpaid invoices. Agent searched and found 42 totaling $125K."
    """
    tools_summary = ""
    if interaction.tools_used:
        tool_names = [t.tool_name for t in interaction.tools_used]
        tools_summary = f" Used tools: {', '.join(tool_names)}."

    return f'User: "{interaction.user_query}". {interaction.outcome}.{tools_summary}'


def format_tools_for_llm(tools: list[ToolExecution]) -> str:
    """
    Format tool executions as a compact summary.

    Args:
        tools: List of tool executions

    Returns:
        str: Formatted tool execution summary
    """
    if not tools:
        return "No tools were used."

    parts = []
    for i, tool in enumerate(tools, 1):
        status = "✓" if tool.success else "✗"
        params_str = ", ".join(f"{k}={v}" for k, v in tool.parameters.items())
        parts.append(
            f"{i}. {status} {tool.tool_name}({params_str}) → {tool.result_summary}"
        )

    return "\n".join(parts)


def truncate_interaction(
    interaction: PreviousInteraction, max_tokens: int = 500
) -> PreviousInteraction:
    """
    Truncate an interaction to fit within token budget.

    Progressively removes less important information until token count
    is below threshold.

    Args:
        interaction: Interaction to truncate
        max_tokens: Maximum allowed tokens

    Returns:
        PreviousInteraction: Truncated copy

    Example:
        >>> truncated = truncate_interaction(long_interaction, max_tokens=300)
        >>> assert truncated.estimate_tokens() <= 300
    """
    # Quick check - if already under budget, return as-is
    if interaction.estimate_tokens() <= max_tokens:
        return interaction

    # Create mutable copy
    truncated = PreviousInteraction(
        timestamp=interaction.timestamp,
        user_query=interaction.user_query,
        agent_reasoning=interaction.agent_reasoning,
        key_decisions=interaction.key_decisions.copy(),
        tools_used=interaction.tools_used.copy(),
        outcome=interaction.outcome,
        confidence=interaction.confidence,
        metadata=interaction.metadata.copy(),
    )

    # Strategy 1: Remove metadata
    if truncated.estimate_tokens() > max_tokens:
        truncated.metadata = {}

    # Strategy 2: Truncate reasoning
    if truncated.estimate_tokens() > max_tokens:
        truncated.agent_reasoning = truncated.agent_reasoning[:200] + "..."

    # Strategy 3: Remove tool details (keep only names and summaries)
    if truncated.estimate_tokens() > max_tokens:
        truncated.tools_used = [
            ToolExecution(
                tool_name=t.tool_name,
                parameters={},  # Remove params
                result_summary=t.result_summary[:100] + "...",
                success=t.success,
            )
            for t in truncated.tools_used
        ]

    # Strategy 4: Limit key decisions
    if truncated.estimate_tokens() > max_tokens:
        truncated.key_decisions = truncated.key_decisions[:3]

    # Strategy 5: Truncate outcome
    if truncated.estimate_tokens() > max_tokens:
        truncated.outcome = truncated.outcome[:150] + "..."

    return truncated
