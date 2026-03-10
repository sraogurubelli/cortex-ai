"""
Unified Agent: Advanced agent implementation for Cortex-AI.

Features:
- Multi-turn conversations with tool calling
- Strategic planning and reasoning
- Context-aware responses
- Streaming support
- Tool orchestration
"""

from typing import Any, Dict, List, Optional
import structlog

from ..providers.llm_provider import BaseLLMClient
from .conversation_manager import ConversationManager
from .base_agent import BaseAgent, BaseTool

logger = structlog.get_logger(__name__)


# Default system prompt for unified agent
DEFAULT_SYSTEM_PROMPT = """
You are an AI assistant with access to various tools through a workbench interface. Your primary function is to understand user queries, determine which tools to use, execute them properly, and deliver concise, actionable responses.

## Core Responsibilities:
1. **Query Analysis**: Analyze user queries to understand intent and required actions
2. **Strategic Planning**: Develop structured approaches for complex tasks
3. **Tool Selection**: Choose the most appropriate tools to address user needs
4. **Tool Execution**: Execute tools with proper parameters and handle results
5. **Response Synthesis**: Provide clear, concise responses based on tool results

## Strategic Planning:
For complex requests, engage in structured planning:
- Break down queries into discrete subtasks
- Map dependencies and determine execution order
- Consider alternatives and evaluate trade-offs
- Anticipate potential failures and prepare fallbacks
- Outline complete strategy before execution

## Workflow Process:

1. **Query Analysis**:
   - Classify the query (domain, intent, required tools)
   - Identify key parameters needed
   - Assess if additional information is needed from user

2. **Strategic Planning**:
   - Think step-by-step about the solution path
   - Formulate multi-stage plan with explicit reasoning
   - Consider information needed at each stage

3. **Tool Selection**:
   - Select appropriate tool(s) for the task
   - Determine proper sequence if multiple tools needed
   - Only use tools when necessary

4. **Tool Execution**:
   - Execute tools with precise parameters
   - Handle tool results appropriately
   - Try alternatives if tools fail

5. **Response Synthesis**:
   - Summarize results clearly and concisely
   - Format for readability
   - Ensure response addresses user's query

## Response Style:
- Be concise and direct - avoid unnecessary words
- Prioritize accuracy over verbosity
- Use bullet points for lists and numbered lists for steps
- Use code blocks with language specification for code examples
- Maintain professional, helpful tone
- Focus on practical, actionable information

## Tool Usage Protocol:
- ALWAYS provide a response after tools return results
- Carefully parse and validate returned data
- Handle errors gracefully and suggest alternatives
- Use progressive disclosure for complex information
- Explain each step when chaining tools
- Never end solely with a tool call execution

## Complete Task Fulfillment:
- Understand the complete intent of user's query
- Track all data from tool calls
- Re-analyze at each step to determine if more information is needed
- Deliver response that fully satisfies the query

Your goal is to leverage tools effectively while maintaining a seamless, helpful experience for the user.
"""


class UnifiedAgent(BaseAgent):
    """
    Unified agent with advanced capabilities for complex task handling.

    Extends BaseAgent with:
    - Enhanced system prompts
    - Better tool orchestration
    - Strategic planning
    - Context management
    """

    def __init__(
        self,
        llm_client: BaseLLMClient,
        tools: Optional[List[BaseTool]] = None,
        conversation_manager: Optional[ConversationManager] = None,
        system_prompt: Optional[str] = None,
        max_iterations: int = 20,
        agent_name: str = "unified-agent",
        additional_context: Optional[str] = None,
    ):
        """
        Initialize unified agent.

        Args:
            llm_client: LLM client for responses
            tools: List of available tools
            conversation_manager: Optional conversation manager
            system_prompt: Custom system prompt (uses default if None)
            max_iterations: Maximum tool calling iterations
            agent_name: Name of the agent
            additional_context: Additional context to append to system prompt
        """
        # Use default system prompt if not provided
        full_system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT

        # Add additional context if provided
        if additional_context:
            full_system_prompt += "\n\n" + additional_context

        # Initialize base agent
        super().__init__(
            llm_client=llm_client,
            conversation_manager=conversation_manager,
            system_prompt=full_system_prompt,
            tools=tools,
            max_iterations=max_iterations,
            agent_name=agent_name,
        )

        logger.info(
            "Initialized unified agent",
            agent_name=agent_name,
            num_tools=len(self.tools) if self.tools else 0,
            has_additional_context=bool(additional_context),
        )

    async def run_with_context(
        self,
        user_message: str,
        context: Optional[Dict[str, Any]] = None,
        stream: bool = False,
    ):
        """
        Run agent with additional context.

        Args:
            user_message: User's input message
            context: Additional context to provide
            stream: Whether to stream the response

        Returns:
            Agent's response
        """
        # If context provided, format and prepend to message
        if context:
            context_str = self._format_context(context)
            enhanced_message = f"{context_str}\n\nUser Query: {user_message}"
        else:
            enhanced_message = user_message

        # Run the agent
        return await self.run(enhanced_message, stream=stream)

    def _format_context(self, context: Dict[str, Any]) -> str:
        """Format context dictionary into a readable string."""
        context_parts = ["Additional Context:"]
        for key, value in context.items():
            context_parts.append(f"- {key}: {value}")
        return "\n".join(context_parts)

    async def add_tool(self, tool: BaseTool):
        """
        Add a tool to the agent's toolset.

        Args:
            tool: Tool to add
        """
        self.tools.append(tool)
        logger.info(
            "Added tool to agent",
            tool_name=tool.name,
            total_tools=len(self.tools),
        )

    async def remove_tool(self, tool_name: str) -> bool:
        """
        Remove a tool from the agent's toolset.

        Args:
            tool_name: Name of tool to remove

        Returns:
            True if tool was removed, False if not found
        """
        original_count = len(self.tools)
        self.tools = [t for t in self.tools if t.name != tool_name]
        removed = len(self.tools) < original_count

        if removed:
            logger.info(
                "Removed tool from agent",
                tool_name=tool_name,
                remaining_tools=len(self.tools),
            )
        else:
            logger.warning(
                "Tool not found for removal",
                tool_name=tool_name,
            )

        return removed

    def list_tools(self) -> List[str]:
        """Get list of available tool names."""
        return [tool.name for tool in self.tools]
