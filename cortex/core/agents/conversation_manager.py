"""
ConversationManager: Conversation history management for Cortex-AI.

Handles:
- Message history tracking
- Token estimation and limits
- LLM-based conversation compression
- Tool output size limits
- JSON serialization
"""

import json
import structlog
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, asdict
from enum import Enum

logger = structlog.get_logger(__name__)


class MessageRole(str, Enum):
    """Message roles in a conversation."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    """Base message structure."""
    role: MessageRole
    content: Union[str, List[Dict[str, Any]]]
    source: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "role": self.role.value if isinstance(self.role, MessageRole) else self.role,
            "content": self.content,
            "source": self.source,
        }


@dataclass
class ToolCall:
    """Tool/function call structure."""
    id: str
    name: str
    arguments: Union[str, Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class ToolResult:
    """Tool execution result."""
    call_id: str
    name: str
    content: str
    is_error: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


# Summary instructions for LLM-based compression
SUMMARY_INSTRUCTIONS = """
You are creating a comprehensive summary of conversation history to preserve critical context.

CRITICAL REQUIREMENTS:

1. **TOOL CALLS & RESULTS** (HIGHEST PRIORITY):
    - Record EVERY tool call: name, parameters, and execution status
    - Capture COMPLETE tool results, especially successful outputs
    - Preserve actual data content, file contents, command outputs
    - Note tool failures and error messages

2. **TASK STATE & PROGRESSION**:
    - COMPLETED: List all fully completed tasks
    - IN-PROGRESS: Current tasks with progress made
    - PENDING: Tasks not yet started
    - FAILED: Failed attempts with specific errors

3. **CRITICAL DISCOVERIES**:
    - Key insights or data uncovered
    - Important file locations and contents
    - Configuration details or system state
    - Error patterns or root causes
    - Successful solutions or workarounds

4. **CONTINUATION CONTEXT**:
    - What tools were tried and their outputs
    - What approaches worked vs. failed
    - Next logical steps based on current state
    - Any unresolved issues

MAXIMUM LENGTH: 10000 tokens
PRIORITY: Tool results > Task state > Context
"""


class ConversationManager:
    """
    Manages conversation history with token limits and compression.
    """

    def __init__(
        self,
        llm_client=None,
        agent_name: str = "cortex",
        token_threshold: int = 100000,
        token_limit: int = 200000,
        summarization_percentage: int = 50,
        max_tool_output_tokens: int = 50000,
    ):
        """
        Initialize conversation manager.

        Args:
            llm_client: LLM client for summarization (optional)
            agent_name: Name of the agent (for message source tracking)
            token_threshold: Token count that triggers compression
            token_limit: Absolute maximum token limit
            summarization_percentage: Percentage of history to summarize
            max_tool_output_tokens: Maximum tokens allowed in tool outputs
        """
        self.conversation_history: List[Message] = []
        self.llm_client = llm_client
        self.agent_name = agent_name
        self.token_threshold = token_threshold
        self.token_limit = token_limit
        self.summarization_percentage = summarization_percentage
        self.max_tool_output_tokens = max_tool_output_tokens
        self.current_token_count = 0

    def estimate_token_count(self, content: Union[str, List, Dict]) -> int:
        """
        Estimate token count from content.

        Uses simple heuristic: ~3.5 characters per token.

        Args:
            content: Content to estimate tokens for

        Returns:
            Estimated token count
        """
        if isinstance(content, (list, dict)):
            content = json.dumps(content)
        return int(len(str(content)) // 3.5)

    def recalculate_token_count(self):
        """Recalculate total token count from all messages."""
        self.current_token_count = 0
        for msg in self.conversation_history:
            self.current_token_count += self.estimate_token_count(msg.content)

    def add_message(
        self,
        role: Union[str, MessageRole],
        content: Union[str, List[Dict[str, Any]]],
        source: Optional[str] = None,
    ) -> None:
        """
        Add a message to conversation history.

        Args:
            role: Message role (system, user, assistant, tool)
            content: Message content
            source: Source of the message (defaults to agent_name)
        """
        if isinstance(role, str):
            role = MessageRole(role)

        # Skip empty messages
        if (isinstance(content, str) and not content.strip()) or (
            isinstance(content, list) and not content
        ):
            logger.warning("Attempted to add empty message. Skipping.")
            return

        message = Message(
            role=role,
            content=content,
            source=source or self.agent_name,
        )

        self.conversation_history.append(message)
        self.current_token_count += self.estimate_token_count(content)

        logger.debug(
            "Added message to history",
            role=role.value,
            tokens=self.estimate_token_count(content),
            total_tokens=self.current_token_count,
        )

    def add_tool_results(
        self, tool_results: List[ToolResult]
    ) -> None:
        """
        Add tool execution results to history.

        Args:
            tool_results: List of tool execution results
        """
        processed_results = []
        oversized_count = 0

        for result in tool_results:
            result_tokens = self.estimate_token_count(result.content)

            if result_tokens > self.max_tool_output_tokens:
                # Create error result for oversized output
                oversized_count += 1
                error_message = (
                    f"ERROR: Tool output exceeded maximum size limit.\n\n"
                    f"Tool: {result.name}\n"
                    f"Output size: {result_tokens:,} tokens\n"
                    f"Maximum allowed: {self.max_tool_output_tokens:,} tokens\n\n"
                    f"SUGGESTED ALTERNATIVES:\n"
                    f"1. Use more specific filters/queries\n"
                    f"2. Process data in smaller chunks\n"
                    f"3. Use pagination if available\n"
                    f"4. Write results to file and read selectively\n"
                )

                error_result = ToolResult(
                    call_id=result.call_id,
                    name=result.name,
                    content=error_message,
                    is_error=True,
                )
                processed_results.append(error_result)

                logger.warning(
                    "Tool output exceeded size limit",
                    tool=result.name,
                    tokens=result_tokens,
                    limit=self.max_tool_output_tokens,
                )
            else:
                processed_results.append(result)

        # Add as a tool message
        self.add_message(
            role=MessageRole.TOOL,
            content=[r.to_dict() for r in processed_results],
        )

        if oversized_count > 0:
            logger.info(f"Rejected {oversized_count} oversized tool output(s)")

    def get_messages(
        self, as_dict: bool = False
    ) -> Union[List[Message], List[Dict[str, Any]]]:
        """
        Get conversation history.

        Args:
            as_dict: If True, return as list of dicts instead of Message objects

        Returns:
            Conversation history
        """
        if as_dict:
            return [msg.to_dict() for msg in self.conversation_history]
        return self.conversation_history

    def to_json(self, include_metadata: bool = True) -> Dict[str, Any]:
        """
        Serialize conversation to JSON-compatible dictionary.

        Args:
            include_metadata: Include metadata like token counts

        Returns:
            Dictionary with conversation data
        """
        result = {
            "messages": [msg.to_dict() for msg in self.conversation_history],
            "message_count": len(self.conversation_history),
        }

        if include_metadata:
            result["metadata"] = {
                "agent_name": self.agent_name,
                "current_token_count": self.current_token_count,
                "token_limit": self.token_limit,
                "token_threshold": self.token_threshold,
            }

        return result

    def to_json_string(self, indent: int = 2, include_metadata: bool = True) -> str:
        """
        Serialize conversation to JSON string.

        Args:
            indent: JSON indentation
            include_metadata: Include metadata

        Returns:
            JSON string
        """
        return json.dumps(
            self.to_json(include_metadata=include_metadata),
            indent=indent,
            ensure_ascii=False,
        )

    def clear_history(self, keep_system_message: bool = True) -> None:
        """
        Clear conversation history.

        Args:
            keep_system_message: Keep the first system message
        """
        previous_count = len(self.conversation_history)

        if keep_system_message and self.conversation_history:
            self.conversation_history = self.conversation_history[:1]
        else:
            self.conversation_history = []

        self.current_token_count = 0

        logger.debug(
            "Cleared conversation history",
            removed_messages=previous_count - len(self.conversation_history),
        )

    def should_compress(self) -> bool:
        """Check if conversation should be compressed."""
        return (
            self.current_token_count >= self.token_threshold
            and len(self.conversation_history) >= 4
        )

    async def compress_with_llm(
        self, complete_summarization: bool = False
    ) -> bool:
        """
        Compress conversation history using LLM summarization.

        Args:
            complete_summarization: Summarize entire history vs. partial

        Returns:
            True if compression was successful
        """
        if not self.llm_client:
            logger.warning("No LLM client available for compression")
            return self._compress_simple()

        if len(self.conversation_history) < 4:
            return False

        logger.debug(
            "Compressing conversation with LLM",
            current_tokens=self.current_token_count,
            threshold=self.token_threshold,
        )

        try:
            # Determine which messages to summarize
            if complete_summarization:
                # Summarize everything except system and first user message
                segments_to_summarize = self.conversation_history[2:]
                segments_to_preserve = []
                summarized_history = self.conversation_history[:2]
            else:
                # Summarize a percentage of older messages
                segment = self.conversation_history[2:-2]
                summarization_token_count = (
                    self.summarization_percentage * self.current_token_count // 100
                )

                token_count = 0
                total_msg_available = 0
                for msg in segment:
                    if token_count < summarization_token_count:
                        token_count += self.estimate_token_count(msg.content)
                        total_msg_available += 1
                    else:
                        break

                segments_to_summarize = segment[:total_msg_available]
                segments_to_preserve = segment[total_msg_available:]
                summarized_history = self.conversation_history[:2]

            logger.debug(
                "Compression plan",
                to_summarize=len(segments_to_summarize),
                to_preserve=len(segments_to_preserve),
            )

            if segments_to_summarize:
                # Create summary prompt
                summary_prompt = self._format_messages_for_summary(segments_to_summarize)

                # Call LLM for summarization
                summary_messages = [
                    {
                        "role": "system",
                        "content": f"You are an expert summarization assistant. {SUMMARY_INSTRUCTIONS}",
                    },
                    {"role": "user", "content": summary_prompt},
                ]

                summary_response = await self.llm_client.create(messages=summary_messages)
                summary_content = summary_response.content

                # Add summary as assistant message
                summarized_history.append(
                    Message(
                        role=MessageRole.ASSISTANT,
                        content=f"[CONTEXT SUMMARY]\n{summary_content}\n[/CONTEXT SUMMARY]",
                        source=self.agent_name,
                    )
                )

                logger.debug("Generated summary", length=len(summary_content))

            # Reconstruct history
            summarized_history.extend(segments_to_preserve)
            if not complete_summarization:
                summarized_history.extend(self.conversation_history[-2:])

            # Update conversation history
            original_length = len(self.conversation_history)
            original_tokens = self.current_token_count
            self.conversation_history = summarized_history
            self.recalculate_token_count()

            logger.info(
                "Compression successful",
                original_messages=original_length,
                new_messages=len(summarized_history),
                original_tokens=original_tokens,
                new_tokens=self.current_token_count,
            )

            return True

        except Exception as e:
            logger.error("LLM compression failed", error=str(e), exc_info=True)
            return self._compress_simple()

    def _format_messages_for_summary(self, messages: List[Message]) -> str:
        """Format messages for summarization prompt."""
        formatted = ""

        for msg in messages:
            role = msg.role.value.upper()
            content = msg.content

            if isinstance(content, list):
                # Handle structured content (e.g., tool results)
                formatted += f"{role}:\n"
                for item in content:
                    if isinstance(item, dict):
                        formatted += f"  {json.dumps(item)}\n"
                    else:
                        formatted += f"  {item}\n"
            else:
                formatted += f"{role}: {content}\n"

        return formatted

    def _compress_simple(self) -> bool:
        """
        Simple compression: keep system message and recent half of history.

        Returns:
            True if compression was successful
        """
        if len(self.conversation_history) <= 4:
            return False

        logger.debug("Using simple compression (cutting history in half)")

        original_length = len(self.conversation_history)

        # Keep system message and recent half
        system_message = self.conversation_history[0]
        midpoint = len(self.conversation_history) // 2
        compressed_history = [system_message] + self.conversation_history[midpoint:]

        self.conversation_history = compressed_history
        self.recalculate_token_count()

        logger.debug(
            "Simple compression complete",
            original_messages=original_length,
            new_messages=len(compressed_history),
        )

        return True
