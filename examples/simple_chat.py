"""
Simple Chat Example for Cortex-AI

Demonstrates:
- LLM provider initialization
- Conversation management
- Basic chat interaction
- Streaming responses
"""

import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from cortex.core import (
    LLMProviderFactory,
    ConversationManager,
    MessageRole,
    create_stream_writer,
)


async def simple_chat_example():
    """Example of a simple chat interaction."""
    print("🤖 Cortex-AI Simple Chat Example\n")

    # Create LLM client (Anthropic by default)
    # You can also specify: provider="openai" or provider="vertex_ai"
    client = LLMProviderFactory.create(
        provider="anthropic",  # or "openai", "vertex_ai"
        model="claude-sonnet-4",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        temperature=0.0,
    )

    # Create conversation manager
    conversation = ConversationManager(
        llm_client=client,
        agent_name="cortex-demo",
    )

    # Add system message
    conversation.add_message(
        role=MessageRole.SYSTEM,
        content="You are a helpful AI assistant. Keep responses concise and clear.",
    )

    # Simulate a conversation
    user_messages = [
        "Hello! What can you help me with?",
        "What's the capital of France?",
        "Tell me an interesting fact about it.",
    ]

    for user_input in user_messages:
        print(f"\n👤 User: {user_input}")

        # Add user message to history
        conversation.add_message(
            role=MessageRole.USER,
            content=user_input,
        )

        # Get messages for LLM
        messages = conversation.get_messages(as_dict=True)

        # Get response from LLM
        response = await client.create(messages=messages)

        # Add assistant response to history
        conversation.add_message(
            role=MessageRole.ASSISTANT,
            content=response.content,
        )

        # Display response
        print(f"🤖 Assistant: {response.content}")
        print(f"   └─ Tokens: {response.usage.get('total_tokens', 'N/A')}")

    # Display conversation summary
    print("\n" + "="*60)
    print(f"📊 Conversation Summary:")
    print(f"   - Total messages: {len(conversation.get_messages())}")
    print(f"   - Estimated tokens: {conversation.current_token_count}")
    print("="*60)

    # Clean up
    await client.close()


async def streaming_chat_example():
    """Example of streaming chat responses."""
    print("\n\n🌊 Cortex-AI Streaming Chat Example\n")

    # Create LLM client
    client = LLMProviderFactory.create(
        provider="anthropic",
        model="claude-sonnet-4",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
    )

    # Create conversation
    conversation = ConversationManager(agent_name="cortex-streaming")
    conversation.add_message(
        role=MessageRole.SYSTEM,
        content="You are a helpful AI assistant.",
    )

    user_input = "Write a haiku about artificial intelligence."
    print(f"👤 User: {user_input}\n")

    conversation.add_message(role=MessageRole.USER, content=user_input)

    # Stream response
    print("🤖 Assistant: ", end="", flush=True)
    full_response = ""

    async for chunk in client.create_stream(messages=conversation.get_messages(as_dict=True)):
        print(chunk, end="", flush=True)
        full_response += chunk

    print("\n")

    # Add complete response to history
    conversation.add_message(role=MessageRole.ASSISTANT, content=full_response)

    await client.close()


async def multi_provider_example():
    """Example comparing responses from different providers."""
    print("\n\n🔄 Cortex-AI Multi-Provider Example\n")

    providers_config = [
        ("anthropic", "claude-sonnet-4", os.getenv("ANTHROPIC_API_KEY")),
        ("openai", "gpt-4o", os.getenv("OPENAI_API_KEY")),
    ]

    user_input = "What is 2 + 2?"
    print(f"👤 User: {user_input}\n")

    for provider_name, model, api_key in providers_config:
        if not api_key:
            print(f"⚠️  Skipping {provider_name}: No API key found\n")
            continue

        print(f"🤖 {provider_name.upper()} ({model}):")

        try:
            # Create client
            client = LLMProviderFactory.create(
                provider=provider_name,
                model=model,
                api_key=api_key,
            )

            # Get response
            messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": user_input},
            ]
            response = await client.create(messages=messages)

            print(f"   Response: {response.content}")
            print(f"   Tokens: {response.usage.get('total_tokens', 'N/A')}\n")

            await client.close()

        except Exception as e:
            print(f"   Error: {str(e)}\n")


async def main():
    """Run all examples."""
    # Example 1: Simple chat
    await simple_chat_example()

    # Example 2: Streaming chat
    await streaming_chat_example()

    # Example 3: Multi-provider comparison
    await multi_provider_example()


if __name__ == "__main__":
    # Run examples
    asyncio.run(main())
