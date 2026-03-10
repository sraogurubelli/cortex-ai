"""
Multi-Agent Swarm Demo

Demonstrates multi-agent orchestration with automatic handoffs.

Shows:
- Agent specialization
- Automatic handoff tools
- Task routing between agents
- Conversation persistence
"""

import asyncio

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from cortex.orchestration import ModelConfig, Swarm, ToolRegistry


# =========================================================================
# Demo Setup
# =========================================================================


async def demo_simple_swarm():
    """Demo 1: Simple two-agent swarm with handoffs."""
    print("\n" + "=" * 60)
    print("Demo 1: Simple Two-Agent Swarm")
    print("=" * 60)

    # Create swarm
    swarm = Swarm(model=ModelConfig(model="gpt-4o", use_gateway=False))

    # Add general assistant
    swarm.add_agent(
        name="general",
        description="General assistant for simple questions",
        system_prompt="""You are a general assistant.
You handle simple questions and greetings.
If asked a complex technical question, transfer to the specialist.""",
        can_handoff_to=["specialist"],
    )

    # Add specialist
    swarm.add_agent(
        name="specialist",
        description="Technical specialist for complex questions",
        system_prompt="""You are a technical specialist.
You handle complex technical questions with detailed explanations.
If asked a simple question, transfer back to general.""",
        can_handoff_to=["general"],
    )

    # Compile swarm
    checkpointer = MemorySaver()
    graph = swarm.compile(checkpointer=checkpointer)

    # Test conversation with handoff
    thread_id = "demo-1"

    # Turn 1: Simple question (general agent handles)
    result1 = await graph.ainvoke(
        {"messages": [HumanMessage(content="Hello, how are you?")]},
        config={"configurable": {"thread_id": thread_id}},
    )
    print(f"\nTurn 1 (General):")
    print(f"User: Hello, how are you?")
    print(f"Assistant: {result1['messages'][-1].content}\n")

    # Turn 2: Complex question (should handoff to specialist)
    result2 = await graph.ainvoke(
        {
            "messages": [
                HumanMessage(
                    content="Can you explain the CAP theorem in distributed systems?"
                )
            ]
        },
        config={"configurable": {"thread_id": thread_id}},
    )
    print(f"\nTurn 2 (Should handoff to Specialist):")
    print(f"User: Can you explain the CAP theorem in distributed systems?")
    print(f"Assistant: {result2['messages'][-1].content}\n")


# =========================================================================
# Demo 2: Research & Writing Team
# =========================================================================


async def demo_research_writing_team():
    """Demo 2: Research and writing team with specialized agents."""
    print("\n" + "=" * 60)
    print("Demo 2: Research & Writing Team")
    print("=" * 60)

    from langchain_core.tools import tool

    # Define tools
    @tool
    async def search_web(query: str) -> str:
        """Search the web for information."""
        # Simulated search results
        results = {
            "python async": "Python asyncio is a library for concurrent programming using async/await syntax...",
            "machine learning": "Machine learning is a subset of AI that enables systems to learn from data...",
        }
        return results.get(query.lower(), f"No results found for '{query}'")

    @tool
    async def save_document(title: str, content: str) -> str:
        """Save a document to storage."""
        # Simulated save
        return f"✓ Document '{title}' saved successfully (length: {len(content)} chars)"

    # Create swarm with tools
    registry = ToolRegistry()
    registry.register(search_web)
    registry.register(save_document)

    swarm = Swarm(
        model=ModelConfig(model="gpt-4o", use_gateway=False), tool_registry=registry
    )

    # Add researcher
    swarm.add_agent(
        name="researcher",
        description="Research agent that gathers information",
        system_prompt="""You are a research assistant.
Your job is to search for information using the search_web tool.
Once you've gathered enough information, transfer to the writer to create a document.""",
        tools=["search_web"],  # Only has search tool
        can_handoff_to=["writer"],
    )

    # Add writer
    swarm.add_agent(
        name="writer",
        description="Writing agent that creates documents",
        system_prompt="""You are a professional writer.
You take research and create well-structured documents.
Use the save_document tool to save your work.
If you need more research, transfer back to the researcher.""",
        tools=["save_document"],  # Only has save tool
        can_handoff_to=["researcher"],
    )

    # Compile and run
    graph = swarm.compile(checkpointer=MemorySaver())

    result = await graph.ainvoke(
        {
            "messages": [
                HumanMessage(
                    content="Research Python async programming and write a brief document about it."
                )
            ]
        },
        config={"configurable": {"thread_id": "research-1"}},
    )

    print(f"\nTask: Research Python async and write a document")
    print(f"\nFinal result:")
    print(f"{result['messages'][-1].content}\n")


# =========================================================================
# Demo 3: Customer Support Team
# =========================================================================


async def demo_customer_support_team():
    """Demo 3: Customer support team with escalation."""
    print("\n" + "=" * 60)
    print("Demo 3: Customer Support Team with Escalation")
    print("=" * 60)

    swarm = Swarm(model=ModelConfig(model="gpt-4o", use_gateway=False))

    # Tier 1 support
    swarm.add_agent(
        name="tier1_support",
        description="First-line customer support for common issues",
        system_prompt="""You are Tier 1 customer support.
Handle common questions about account access, password resets, and basic troubleshooting.
For technical issues or billing questions, escalate to tier2_support.
Always be friendly and helpful.""",
        can_handoff_to=["tier2_support", "billing"],
    )

    # Tier 2 support
    swarm.add_agent(
        name="tier2_support",
        description="Technical support specialist",
        system_prompt="""You are a technical support specialist.
Handle complex technical issues, integrations, and API questions.
For billing-related issues, transfer to billing.
Provide detailed technical explanations.""",
        can_handoff_to=["tier1_support", "billing"],
    )

    # Billing specialist
    swarm.add_agent(
        name="billing",
        description="Billing and payment specialist",
        system_prompt="""You are a billing specialist.
Handle all questions about payments, subscriptions, and invoices.
For technical issues, transfer to tier2_support.
For simple questions, transfer to tier1_support.""",
        can_handoff_to=["tier1_support", "tier2_support"],
    )

    graph = swarm.compile(checkpointer=MemorySaver())

    # Test escalation path
    result = await graph.ainvoke(
        {
            "messages": [
                HumanMessage(
                    content="I'm having trouble with API authentication. The access token keeps expiring after 5 minutes."
                )
            ]
        },
        config={"configurable": {"thread_id": "support-1"}},
    )

    print(f"\nCustomer: API authentication issue")
    print(f"Support Response: {result['messages'][-1].content}\n")


# =========================================================================
# Main
# =========================================================================


async def main():
    """Run all swarm demos."""
    print("\n" + "=" * 60)
    print("Cortex Orchestration SDK - Multi-Agent Swarm Examples")
    print("=" * 60)

    await demo_simple_swarm()
    await demo_research_writing_team()
    await demo_customer_support_team()

    print("\n" + "=" * 60)
    print("All swarm demos completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
