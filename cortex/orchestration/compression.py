"""
Conversation Compression for Long-Running Agents.

Handles conversation history compression when token limits are approached:
- LLM-based summarization for critical context preservation
- Simple truncation as fallback
- Token estimation and thresholding

Usage:
    from cortex.orchestration import compress_conversation_history, estimate_tokens

    # Check if compression is needed
    token_count = estimate_tokens(messages)
    if token_count > 150000:
        compressed = await compress_conversation_history(
            messages=messages,
            llm_client=llm_client,
            max_tokens=200000,
            compression_threshold=160000,
        )

Auto-compression in Agent:
    agent = Agent(
        name="assistant",
        model=ModelConfig(model="gpt-4o"),
        enable_compression=True,  # Automatically compresses long conversations
        max_tokens=200000,         # Total token limit
    )
"""

import logging
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

logger = logging.getLogger(__name__)

# Summary instructions for LLM-based compression
SUMMARY_INSTRUCTIONS = """
You are creating a comprehensive summary of conversation history to preserve critical context while managing token limits.

CRITICAL REQUIREMENTS:

1. **TOOL CALLS & RESULTS** (HIGHEST PRIORITY):
   - Record EVERY tool call: name, key parameters, execution status
   - Capture COMPLETE tool results, especially successful outputs
   - Preserve actual data content, file contents, search results, command outputs
   - Note tool failures and error messages
   - Include important discoveries, configurations, insights found

2. **TASK STATE & PROGRESSION**:
   - COMPLETED: List all fully completed tasks with evidence
   - IN-PROGRESS: Current tasks with specific progress made
   - PENDING: Tasks not yet started
   - FAILED: Failed attempts with specific errors and lessons learned

3. **CRITICAL DISCOVERIES & DATA**:
   - Key insights, findings, or data uncovered through tools
   - Important file locations and actual contents (code snippets, configs)
   - Configuration details, environment info, system state
   - Error patterns, root causes, debugging information
   - Successful solutions or workarounds

4. **CONTINUATION CONTEXT**:
   - What tools were tried and their complete outputs
   - Important data/files discovered (include actual content)
   - What approaches worked vs. failed
   - Next logical steps based on current state
   - Any unresolved issues or pending questions

MAXIMUM LENGTH: 10000 tokens
PRIORITY: Tool results and actual data > Task state > Context
"""


@dataclass
class CompressionConfig:
    """Configuration for conversation compression."""

    max_tokens: int = 200_000
    """Total token limit for conversation history."""

    compression_threshold: int = 160_000
    """Trigger compression when tokens exceed this threshold."""

    summarization_percentage: int = 70
    """Percentage of history to summarize (70% = summarize 70%, keep 30%)."""

    max_tool_output_tokens: int = 50_000
    """Maximum tokens for a single tool output (truncate larger outputs)."""

    preserve_recent_messages: int = 2
    """Number of recent messages to always preserve."""

    compression_model: str = "gpt-4o-mini"
    """Fast model to use for summarization (should be cheap and fast)."""


def estimate_tokens(content: str | list[BaseMessage] | BaseMessage) -> int:
    """
    Estimate token count for content.

    Uses a simple heuristic: ~3.5 characters per token (based on OpenAI tokenizers).
    This is a rough estimate but sufficient for compression thresholds.

    Args:
        content: String, single message, or list of messages

    Returns:
        int: Estimated token count

    Example:
        >>> estimate_tokens("Hello, world!")
        4
        >>> estimate_tokens(HumanMessage(content="Test"))
        1
    """
    if isinstance(content, list):
        # List of messages
        total = 0
        for msg in content:
            total += estimate_tokens(msg)
        return total
    elif isinstance(content, BaseMessage):
        # Single message
        total = 0
        if hasattr(msg := content, "content"):
            if isinstance(msg.content, str):
                total += len(msg.content) // 4  # ~4 chars per token
            elif isinstance(msg.content, list):
                # Handle multi-modal content (text + images)
                for item in msg.content:
                    if isinstance(item, dict) and "text" in item:
                        total += len(item["text"]) // 4
                    elif isinstance(item, str):
                        total += len(item) // 4
        # Add overhead for message structure
        total += 10  # ~10 tokens for message wrapper
        return total
    else:
        # String
        return len(str(content)) // 4


def should_compress(
    messages: list[BaseMessage],
    config: CompressionConfig | None = None,
) -> bool:
    """
    Check if conversation history should be compressed.

    Args:
        messages: List of conversation messages
        config: Compression configuration (uses defaults if None)

    Returns:
        bool: True if compression is recommended

    Example:
        >>> messages = [HumanMessage(content="..." * 50000)]
        >>> should_compress(messages)
        True
    """
    config = config or CompressionConfig()
    current_tokens = estimate_tokens(messages)
    return current_tokens > config.compression_threshold


async def compress_conversation_history(
    messages: list[BaseMessage],
    llm_client: Any | None = None,
    config: CompressionConfig | None = None,
) -> list[BaseMessage]:
    """
    Compress conversation history using LLM-based summarization.

    Strategy:
    - Preserve: System message, recent messages (last N), tool call-result pairs
    - Compress: Middle conversation history → single summary message
    - Fallback: Simple truncation if LLM summarization fails

    Args:
        messages: List of conversation messages to compress
        llm_client: LLMClient instance for summarization (optional, uses fallback if None)
        config: Compression configuration (uses defaults if None)

    Returns:
        list[BaseMessage]: Compressed conversation history

    Example:
        from cortex.orchestration import Agent, compress_conversation_history

        # Manual compression
        compressed = await compress_conversation_history(
            messages=long_conversation,
            llm_client=agent_llm_client,
        )

        # Use compressed messages in next run
        result = await agent.run("Continue", messages=compressed)
    """
    config = config or CompressionConfig()

    if len(messages) < 4:
        logger.debug("Conversation too short to compress (< 4 messages)")
        return messages

    original_tokens = estimate_tokens(messages)
    logger.info(
        f"Compressing conversation: {len(messages)} messages, "
        f"~{original_tokens:,} tokens"
    )

    # Separate system message (if present)
    system_message = None
    if messages and isinstance(messages[0], SystemMessage):
        system_message = messages[0]
        messages = messages[1:]

    # Preserve recent messages
    recent_messages = messages[-config.preserve_recent_messages :]
    middle_messages = messages[: -config.preserve_recent_messages]

    if not middle_messages:
        logger.debug("No middle messages to compress")
        return [system_message] + messages if system_message else messages

    # Calculate how much to summarize
    summarization_token_count = (
        config.summarization_percentage * estimate_tokens(middle_messages) // 100
    )
    token_count = 0
    messages_to_summarize = []

    for msg in middle_messages:
        if token_count < summarization_token_count:
            token_count += estimate_tokens(msg)
            messages_to_summarize.append(msg)
        else:
            break

    messages_to_preserve = middle_messages[len(messages_to_summarize) :]

    # Ensure we don't break tool call-result pairs
    if messages_to_summarize:
        # If last message to summarize is an AI message with tool calls,
        # move it to preserve section to keep it with its results
        last_msg = messages_to_summarize[-1]
        if isinstance(last_msg, AIMessage) and _has_tool_calls(last_msg):
            messages_to_preserve.insert(0, messages_to_summarize.pop())

    logger.debug(
        f"Summarizing {len(messages_to_summarize)} messages, "
        f"preserving {len(messages_to_preserve)} middle messages + "
        f"{len(recent_messages)} recent messages"
    )

    # Try LLM-based summarization
    if llm_client and messages_to_summarize:
        try:
            summary = await _summarize_with_llm(
                messages_to_summarize, llm_client, config
            )

            # Build compressed history
            compressed = []
            if system_message:
                compressed.append(system_message)

            # Add summary as AI message
            compressed.append(
                AIMessage(
                    content=f"[CONTEXT SUMMARY]\n{summary}\n[/CONTEXT SUMMARY]",
                )
            )

            # Add preserved middle messages
            compressed.extend(messages_to_preserve)

            # Add recent messages
            compressed.extend(recent_messages)

            new_tokens = estimate_tokens(compressed)
            logger.info(
                f"Compressed: {len(messages)} → {len(compressed)} messages, "
                f"{original_tokens:,} → {new_tokens:,} tokens "
                f"({100 - (new_tokens * 100 // original_tokens)}% reduction)"
            )

            return compressed

        except Exception as e:
            logger.warning(f"LLM summarization failed: {e}. Using fallback compression.")

    # Fallback: simple truncation
    return _compress_simple(messages, system_message, config)


async def _summarize_with_llm(
    messages: list[BaseMessage],
    llm_client: Any,
    config: CompressionConfig,
) -> str:
    """
    Summarize messages using an LLM.

    Args:
        messages: Messages to summarize
        llm_client: LLMClient instance
        config: Compression configuration

    Returns:
        str: Summary text
    """
    # Format messages for summarization
    formatted = _format_messages_for_summary(messages)

    # Create summarization prompt
    system_prompt = (
        "You are an expert summarization assistant that preserves "
        "critical information while being extremely concise."
    )
    system_prompt += SUMMARY_INSTRUCTIONS

    summary_messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=formatted),
    ]

    # Use fast, cheap model for summarization
    from cortex.orchestration.llm import LLMClient
    from cortex.orchestration.config import ModelConfig

    summarizer = LLMClient(
        ModelConfig(
            model=config.compression_model,
            max_tokens=10000,  # Max summary length
            temperature=0.0,  # Deterministic
        )
    )

    # Generate summary
    llm = summarizer.create()
    response = await llm.ainvoke(summary_messages)

    if isinstance(response.content, list):
        # Multi-modal response, extract text
        summary = " ".join(
            item.get("text", str(item)) if isinstance(item, dict) else str(item)
            for item in response.content
        )
    else:
        summary = response.content

    return summary


def _format_messages_for_summary(messages: list[BaseMessage]) -> str:
    """
    Format messages into a text representation for summarization.

    Args:
        messages: Messages to format

    Returns:
        str: Formatted text
    """
    formatted = ""

    for msg in messages:
        if isinstance(msg, HumanMessage):
            formatted += f"USER: {msg.content}\n\n"

        elif isinstance(msg, AIMessage):
            # Check for tool calls
            if _has_tool_calls(msg):
                formatted += "ASSISTANT (TOOL CALLS):\n"
                tool_calls = _extract_tool_calls(msg)
                for call in tool_calls:
                    formatted += f"  - {call['name']}({call['args']})\n"
            else:
                formatted += f"ASSISTANT: {msg.content}\n"

            formatted += "\n"

        elif isinstance(msg, ToolMessage):
            formatted += f"TOOL RESULT ({msg.name}): {msg.content}\n\n"

        elif isinstance(msg, SystemMessage):
            formatted += f"SYSTEM: {msg.content}\n\n"

        else:
            formatted += f"MESSAGE: {str(msg)}\n\n"

    return formatted


def _has_tool_calls(message: AIMessage) -> bool:
    """Check if an AI message contains tool calls."""
    return bool(
        hasattr(message, "tool_calls")
        and message.tool_calls
        or hasattr(message, "additional_kwargs")
        and message.additional_kwargs.get("tool_calls")
    )


def _extract_tool_calls(message: AIMessage) -> list[dict]:
    """Extract tool calls from an AI message."""
    if hasattr(message, "tool_calls") and message.tool_calls:
        return [
            {"name": call.get("name", "unknown"), "args": call.get("args", {})}
            for call in message.tool_calls
        ]
    elif hasattr(message, "additional_kwargs"):
        tool_calls = message.additional_kwargs.get("tool_calls", [])
        return [
            {
                "name": call.get("function", {}).get("name", "unknown"),
                "args": call.get("function", {}).get("arguments", {}),
            }
            for call in tool_calls
        ]
    return []


def _compress_simple(
    messages: list[BaseMessage],
    system_message: SystemMessage | None,
    config: CompressionConfig,
) -> list[BaseMessage]:
    """
    Simple fallback compression: keep recent half of conversation.

    Args:
        messages: Messages to compress
        system_message: System message to preserve
        config: Compression configuration

    Returns:
        list[BaseMessage]: Compressed messages
    """
    logger.info("Using simple compression (truncation)")

    if len(messages) <= 4:
        return [system_message] + messages if system_message else messages

    # Keep the more recent half
    midpoint = len(messages) // 2
    compressed = messages[midpoint:]

    # If first compressed message is a tool result, find its tool call
    if compressed and isinstance(compressed[0], ToolMessage):
        # Look backwards for the AI message with tool calls
        for i in range(midpoint - 1, 0, -1):
            if isinstance(messages[i], AIMessage) and _has_tool_calls(messages[i]):
                compressed.insert(0, messages[i])
                break

    # Prepend system message
    if system_message:
        compressed.insert(0, system_message)

    original_tokens = estimate_tokens(
        [system_message] + messages if system_message else messages
    )
    new_tokens = estimate_tokens(compressed)

    logger.info(
        f"Simple compression: {len(messages)} → {len(compressed)} messages, "
        f"{original_tokens:,} → {new_tokens:,} tokens"
    )

    return compressed
