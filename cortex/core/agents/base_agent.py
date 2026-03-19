"""
Base Agent: Foundation for agent implementations in Cortex-AI.

⚠️ DEPRECATED: This module is deprecated and will be removed in a future version.
Please use cortex.orchestration.Agent instead for new implementations.

Migration Guide:
- Old: from cortex.core.agents.base_agent import BaseAgent, BaseTool
- New: from cortex.orchestration.agent import Agent
       from cortex.orchestration.tools import Tool

The new orchestration layer provides:
- LangGraph-based agent orchestration
- Better tool management with ToolRegistry
- Enhanced observability and middleware support
- Multi-agent swarm capabilities

Provides:
- Multi-turn conversation support
- Tool/function calling
- Streaming responses
- Token management
"""

import warnings
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional, Union
import structlog

from ..providers.llm_provider import BaseLLMClient, LLMResponse
from .conversation_manager import ConversationManager, MessageRole, ToolCall, ToolResult

logger = structlog.get_logger(__name__)

# Issue deprecation warning when module is imported
warnings.warn(
    "cortex.core.agents.base_agent is deprecated and will be removed in a future version. "
    "Please migrate to cortex.orchestration.Agent for new implementations. "
    "See module docstring for migration guide.",
    DeprecationWarning,
    stacklevel=2,
)


class BaseTool(ABC):
    """
    Base class for tools/functions that agents can use.

    ⚠️ DEPRECATED: Use cortex.orchestration.tools.Tool instead.

    Migration:
        from cortex.orchestration.tools import Tool, ToolRegistry
    """

    def __init__(self, name: str, description: str):
        warnings.warn(
            f"BaseTool is deprecated. Please use cortex.orchestration.tools.Tool instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.name = name
        self.description = description

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """Execute the tool with given parameters."""
        pass

    @abstractmethod
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        pass


class BaseAgent(ABC):
    """
    Base class for AI agents with tool-calling capabilities.

    ⚠️ DEPRECATED: Use cortex.orchestration.Agent instead.

    Migration:
        # Old approach:
        from cortex.core.agents.base_agent import BaseAgent
        agent = BaseAgent(llm_client=client, tools=tools)

        # New approach:
        from cortex.orchestration.agent import Agent
        from cortex.orchestration.builder import AgentBuilder

        agent = AgentBuilder()\\
            .with_model(...)\\
            .with_tools(...)\\
            .build()

    The new orchestration layer provides better:
    - LangGraph-based orchestration for complex workflows
    - Middleware support for cross-cutting concerns
    - Enhanced observability and tracing
    - Multi-agent swarm capabilities
    """

    def __init__(
        self,
        llm_client: BaseLLMClient,
        conversation_manager: Optional[ConversationManager] = None,
        system_prompt: Optional[str] = None,
        tools: Optional[List[BaseTool]] = None,
        max_iterations: int = 10,
        agent_name: str = "agent",
    ):
        """
        Initialize the base agent.

        Args:
            llm_client: LLM client for generating responses
            conversation_manager: Manager for conversation history
            system_prompt: System instructions for the agent
            tools: List of tools the agent can use
            max_iterations: Maximum iterations for tool calling loops
            agent_name: Name of the agent
        """
        warnings.warn(
            f"BaseAgent is deprecated. Please use cortex.orchestration.Agent instead. "
            f"See class docstring for migration guide.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.llm_client = llm_client
        self.conversation_manager = conversation_manager or ConversationManager(
            llm_client=llm_client,
            agent_name=agent_name,
        )
        self.tools = tools or []
        self.max_iterations = max_iterations
        self.agent_name = agent_name

        # Set system prompt if provided
        if system_prompt:
            self.conversation_manager.add_message(
                role=MessageRole.SYSTEM,
                content=system_prompt,
            )

        logger.info(
            "Initialized agent",
            agent_name=agent_name,
            num_tools=len(self.tools),
            max_iterations=max_iterations,
        )

    def _get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Get JSON schemas for all available tools."""
        return [tool.get_schema() for tool in self.tools]

    def _find_tool(self, tool_name: str) -> Optional[BaseTool]:
        """Find a tool by name."""
        for tool in self.tools:
            if tool.name == tool_name:
                return tool
        return None

    async def _execute_tool(self, tool_name: str, **kwargs) -> Any:
        """Execute a tool and return its result."""
        tool = self._find_tool(tool_name)
        if not tool:
            raise ValueError(f"Tool '{tool_name}' not found")

        logger.debug(
            "Executing tool",
            tool_name=tool_name,
            kwargs=kwargs,
        )

        try:
            result = await tool.execute(**kwargs)
            logger.info(
                "Tool execution successful",
                tool_name=tool_name,
            )
            return result
        except Exception as e:
            logger.error(
                "Tool execution failed",
                tool_name=tool_name,
                error=str(e),
                exc_info=True,
            )
            raise

    async def run(
        self,
        user_message: str,
        stream: bool = False,
    ) -> Union[AsyncIterator[str], str]:
        """
        Run the agent with a user message.

        Args:
            user_message: User's input message
            stream: Whether to stream the response

        Returns:
            Agent's response (streaming or complete)
        """
        # Add user message to conversation
        self.conversation_manager.add_message(
            role=MessageRole.USER,
            content=user_message,
        )

        if stream:
            return self._run_streaming()
        else:
            return await self._run_complete()

    async def _run_complete(self) -> str:
        """Run agent and return complete response."""
        iteration = 0
        final_response = ""

        while iteration < self.max_iterations:
            iteration += 1

            # Get messages for LLM
            messages = self.conversation_manager.get_messages(as_dict=True)

            # Get tool schemas if tools are available
            tool_schemas = self._get_tool_schemas() if self.tools else None

            # Call LLM
            response = await self.llm_client.create(
                messages=messages,
                tools=tool_schemas,
            )

            # Check if LLM wants to call tools
            if response.tool_calls and len(response.tool_calls) > 0:
                logger.debug(
                    "LLM requested tool calls",
                    num_tools=len(response.tool_calls),
                    iteration=iteration,
                )

                # Add assistant message with tool calls to history
                self.conversation_manager.add_message(
                    role=MessageRole.ASSISTANT,
                    content=response.tool_calls,  # Store tool calls
                )

                # Execute tools
                tool_results = []
                for tool_call in response.tool_calls:
                    try:
                        # Parse arguments if needed
                        import json
                        if isinstance(tool_call["arguments"], str):
                            args = json.loads(tool_call["arguments"])
                        else:
                            args = tool_call["arguments"]

                        # Execute tool
                        result = await self._execute_tool(
                            tool_call["name"],
                            **args
                        )

                        tool_results.append(
                            ToolResult(
                                call_id=tool_call.get("id", ""),
                                name=tool_call["name"],
                                content=str(result),
                                is_error=False,
                            )
                        )
                    except Exception as e:
                        tool_results.append(
                            ToolResult(
                                call_id=tool_call.get("id", ""),
                                name=tool_call["name"],
                                content=f"Error: {str(e)}",
                                is_error=True,
                            )
                        )

                # Add tool results to conversation
                self.conversation_manager.add_tool_results(tool_results)

                # Continue loop to get next response
                continue

            else:
                # No tool calls, this is the final response
                final_response = response.content

                # Add assistant response to history
                self.conversation_manager.add_message(
                    role=MessageRole.ASSISTANT,
                    content=final_response,
                )

                logger.info(
                    "Agent completed",
                    iterations=iteration,
                    response_length=len(final_response),
                )

                break

        # Check if we hit max iterations
        if iteration >= self.max_iterations:
            logger.warning(
                "Agent hit max iterations",
                max_iterations=self.max_iterations,
            )
            final_response = final_response or "I apologize, but I've reached my iteration limit. Please try a simpler request."

        return final_response

    async def _run_streaming(self) -> AsyncIterator[str]:
        """Run agent with streaming response."""
        # For now, implement basic streaming without tool calls
        # (Tool calling with streaming is more complex)

        messages = self.conversation_manager.get_messages(as_dict=True)

        full_response = ""
        async for chunk in self.llm_client.create_stream(messages=messages):
            full_response += chunk
            yield chunk

        # Add complete response to history
        self.conversation_manager.add_message(
            role=MessageRole.ASSISTANT,
            content=full_response,
        )

    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """Get the conversation history."""
        return self.conversation_manager.get_messages(as_dict=True)

    def clear_history(self, keep_system_message: bool = True):
        """Clear conversation history."""
        self.conversation_manager.clear_history(keep_system_message=keep_system_message)

    async def close(self):
        """Close the agent and cleanup resources."""
        await self.llm_client.close()
        logger.debug("Agent closed")
