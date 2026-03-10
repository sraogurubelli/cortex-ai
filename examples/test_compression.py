"""
Test script for conversation compression.

Demonstrates:
1. Token estimation for messages
2. Automatic compression detection with should_compress()
3. LLM-based summarization of long conversations
4. Fallback compression when LLM unavailable
5. Integration with Agent for long-running conversations

Prerequisites:
    Basic example - no extra dependencies needed

Run with:
    python examples/test_compression.py
"""

import asyncio

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from cortex.orchestration import (
    Agent,
    CompressionConfig,
    ModelConfig,
    compress_conversation_history,
    estimate_tokens,
    should_compress,
)


def demo_token_estimation():
    """Demonstrate token estimation for different content types."""
    print("=" * 70)
    print("Demo 1: Token Estimation")
    print("=" * 70)

    # String estimation
    text = "Hello, world! This is a test message."
    tokens = estimate_tokens(text)
    print(f"\n1. String: '{text}'")
    print(f"   Estimated tokens: {tokens}")
    print(f"   Characters: {len(text)}")
    print(f"   Ratio: ~{len(text) / tokens:.1f} chars/token")

    # Single message
    message = HumanMessage(content="What is Python?")
    tokens = estimate_tokens(message)
    print(f"\n2. Single message: HumanMessage")
    print(f"   Estimated tokens: {tokens}")

    # List of messages
    messages = [
        SystemMessage(content="You are a helpful assistant."),
        HumanMessage(content="What is Python?"),
        AIMessage(content="Python is a high-level programming language..."),
    ]
    tokens = estimate_tokens(messages)
    print(f"\n3. List of {len(messages)} messages")
    print(f"   Estimated tokens: {tokens}")

    # Large conversation
    large_messages = [HumanMessage(content="Question " + str(i)) for i in range(100)]
    tokens = estimate_tokens(large_messages)
    print(f"\n4. Large conversation: {len(large_messages)} messages")
    print(f"   Estimated tokens: {tokens:,}")

    print("\n✓ Token estimation helps track conversation size!")


def demo_compression_detection():
    """Demonstrate automatic compression detection."""
    print("\n" + "=" * 70)
    print("Demo 2: Compression Detection")
    print("=" * 70)

    # Short conversation - no compression needed
    short_messages = [
        HumanMessage(content="Hello"),
        AIMessage(content="Hi there!"),
    ]
    tokens = estimate_tokens(short_messages)
    needs_compression = should_compress(short_messages)

    print(f"\n1. Short conversation:")
    print(f"   Messages: {len(short_messages)}")
    print(f"   Tokens: {tokens:,}")
    print(f"   Needs compression: {needs_compression}")

    # Long conversation - compression recommended
    # Simulate a long conversation
    long_messages = [
        SystemMessage(content="You are a helpful assistant." * 100),
        HumanMessage(content="Question about Python" * 1000),
        AIMessage(content="Python is a programming language..." * 2000),
        HumanMessage(content="Tell me more" * 500),
        AIMessage(content="Python was created by..." * 1500),
    ]
    tokens = estimate_tokens(long_messages)
    needs_compression = should_compress(long_messages)

    print(f"\n2. Long conversation:")
    print(f"   Messages: {len(long_messages)}")
    print(f"   Tokens: {tokens:,}")
    print(f"   Needs compression: {needs_compression}")

    # Custom threshold
    config = CompressionConfig(
        compression_threshold=50000,  # Lower threshold
    )
    needs_compression = should_compress(long_messages, config)
    print(f"\n3. Custom threshold (50k tokens):")
    print(f"   Tokens: {tokens:,}")
    print(f"   Needs compression: {needs_compression}")

    print("\n✓ Compression detection prevents token limit errors!")


async def demo_llm_compression():
    """Demonstrate LLM-based conversation summarization."""
    print("\n" + "=" * 70)
    print("Demo 3: LLM-Based Compression")
    print("=" * 70)

    # Create a conversation to compress
    messages = [
        SystemMessage(content="You are a helpful coding assistant."),
        HumanMessage(content="How do I read a file in Python?"),
        AIMessage(
            content="You can read a file in Python using the `open()` function:\n\n"
            "```python\n"
            "with open('file.txt', 'r') as f:\n"
            "    content = f.read()\n"
            "```\n\n"
            "This automatically closes the file when done."
        ),
        HumanMessage(content="What about writing to a file?"),
        AIMessage(
            content="To write to a file, use mode 'w':\n\n"
            "```python\n"
            "with open('file.txt', 'w') as f:\n"
            "    f.write('Hello, world!')\n"
            "```\n\n"
            "Use 'a' mode to append instead of overwriting."
        ),
        HumanMessage(content="Can I read CSV files?"),
        AIMessage(
            content="Yes! Use the `csv` module:\n\n"
            "```python\n"
            "import csv\n\n"
            "with open('data.csv', 'r') as f:\n"
            "    reader = csv.reader(f)\n"
            "    for row in reader:\n"
            "        print(row)\n"
            "```\n\n"
            "Or use pandas for more features:\n"
            "```python\n"
            "import pandas as pd\n"
            "df = pd.read_csv('data.csv')\n"
            "```"
        ),
        HumanMessage(content="Thanks! What about JSON files?"),
        AIMessage(
            content="Use the `json` module:\n\n"
            "```python\n"
            "import json\n\n"
            "# Reading JSON\n"
            "with open('data.json', 'r') as f:\n"
            "    data = json.load(f)\n\n"
            "# Writing JSON\n"
            "with open('output.json', 'w') as f:\n"
            "    json.dump(data, f, indent=2)\n"
            "```"
        ),
        HumanMessage(content="What is the latest question I asked?"),
        AIMessage(content="Your latest question was about JSON files."),
    ]

    original_tokens = estimate_tokens(messages)
    print(f"\nOriginal conversation:")
    print(f"  Messages: {len(messages)}")
    print(f"  Estimated tokens: {original_tokens:,}")

    # Compress with LLM
    print(f"\n📊 Compressing conversation using LLM...")

    compressed = await compress_conversation_history(
        messages=messages,
        config=CompressionConfig(
            compression_threshold=100,  # Force compression for demo
            preserve_recent_messages=2,  # Keep last 2 messages
        ),
    )

    compressed_tokens = estimate_tokens(compressed)
    print(f"\nCompressed conversation:")
    print(f"  Messages: {len(compressed)}")
    print(f"  Estimated tokens: {compressed_tokens:,}")
    print(
        f"  Token reduction: {100 - (compressed_tokens * 100 // original_tokens)}%"
    )

    print(f"\n📋 Compressed messages:")
    for i, msg in enumerate(compressed):
        msg_type = type(msg).__name__
        content_preview = (
            str(msg.content)[:100] + "..." if len(str(msg.content)) > 100 else msg.content
        )
        print(f"  {i + 1}. {msg_type}: {content_preview}")

    print("\n✓ LLM compression preserves context while reducing tokens!")


async def demo_fallback_compression():
    """Demonstrate fallback compression when LLM unavailable."""
    print("\n" + "=" * 70)
    print("Demo 4: Fallback Compression")
    print("=" * 70)

    # Create a long conversation
    messages = [
        SystemMessage(content="You are a helpful assistant."),
    ]

    # Add many messages to trigger compression
    for i in range(20):
        messages.append(HumanMessage(content=f"Question {i + 1}: Tell me about topic {i}"))
        messages.append(AIMessage(content=f"Answer {i + 1}: Here's info about topic {i}..."))

    original_tokens = estimate_tokens(messages)
    print(f"\nOriginal conversation:")
    print(f"  Messages: {len(messages)}")
    print(f"  Estimated tokens: {original_tokens:,}")

    # Compress without LLM (llm_client=None triggers fallback)
    print(f"\n📊 Compressing using fallback (simple truncation)...")

    compressed = await compress_conversation_history(
        messages=messages,
        llm_client=None,  # No LLM - triggers fallback
        config=CompressionConfig(compression_threshold=100),  # Force compression
    )

    compressed_tokens = estimate_tokens(compressed)
    print(f"\nCompressed conversation:")
    print(f"  Messages: {len(compressed)}")
    print(f"  Estimated tokens: {compressed_tokens:,}")
    print(
        f"  Token reduction: {100 - (compressed_tokens * 100 // original_tokens)}%"
    )

    print(f"\n📋 Fallback keeps:")
    print(f"  - System message (always preserved)")
    print(f"  - Recent half of conversation")
    print(f"  - Tool call-result pairs (if any)")

    print("\n✓ Fallback compression ensures robustness!")


async def demo_agent_integration():
    """Demonstrate using compression with Agent for long conversations."""
    print("\n" + "=" * 70)
    print("Demo 5: Agent Integration")
    print("=" * 70)

    print("\n📊 Simulating long-running conversation...")

    # Create agent
    agent = Agent(
        name="assistant",
        system_prompt="You are a helpful assistant that answers questions concisely.",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
    )

    # Simulate a long conversation
    messages = []
    thread_id = "long-conversation-demo"

    for i in range(5):
        print(f"\nTurn {i + 1}:")
        question = f"Tell me a short fact about the number {i + 1}"

        result = await agent.run(question, thread_id=thread_id)
        print(f"  Q: {question}")
        print(f"  A: {result.response}")

        # Track all messages
        messages = result.messages

        # Check if compression is needed
        token_count = estimate_tokens(messages)
        print(f"  Tokens: {token_count:,}")

    # After many turns, manually compress
    if should_compress(messages):
        print(f"\n⚠️  Conversation needs compression!")
        print(f"   Current tokens: {estimate_tokens(messages):,}")

        compressed = await compress_conversation_history(messages=messages)

        print(f"   Compressed to: {estimate_tokens(compressed):,} tokens")
        print(f"   Reduced by: {len(messages) - len(compressed)} messages")

        # Continue conversation with compressed history
        print(f"\n📝 Continuing with compressed history...")
        result = await agent.run(
            "What was the first fact you told me?",
            messages=compressed,  # Use compressed history
            thread_id=thread_id,
        )
        print(f"  Q: What was the first fact you told me?")
        print(f"  A: {result.response}")

    print("\n✓ Compression enables long-running conversations!")


async def demo_configuration():
    """Demonstrate compression configuration options."""
    print("\n" + "=" * 70)
    print("Demo 6: Compression Configuration")
    print("=" * 70)

    print("\n1. Default configuration:")
    config = CompressionConfig()
    print(f"   max_tokens: {config.max_tokens:,}")
    print(f"   compression_threshold: {config.compression_threshold:,}")
    print(f"   summarization_percentage: {config.summarization_percentage}%")
    print(f"   max_tool_output_tokens: {config.max_tool_output_tokens:,}")
    print(f"   preserve_recent_messages: {config.preserve_recent_messages}")
    print(f"   compression_model: {config.compression_model}")

    print("\n2. Custom configuration for aggressive compression:")
    config = CompressionConfig(
        max_tokens=100_000,  # Lower limit
        compression_threshold=80_000,  # Compress earlier
        summarization_percentage=80,  # Summarize 80% (more aggressive)
        preserve_recent_messages=1,  # Keep fewer recent messages
        compression_model="gpt-4o-mini",  # Fast, cheap model
    )
    print(f"   max_tokens: {config.max_tokens:,}")
    print(f"   compression_threshold: {config.compression_threshold:,}")
    print(f"   summarization_percentage: {config.summarization_percentage}%")

    print("\n3. Conservative configuration:")
    config = CompressionConfig(
        max_tokens=300_000,  # Higher limit
        compression_threshold=250_000,  # Compress later
        summarization_percentage=50,  # Summarize 50% (conservative)
        preserve_recent_messages=5,  # Keep more recent messages
    )
    print(f"   max_tokens: {config.max_tokens:,}")
    print(f"   compression_threshold: {config.compression_threshold:,}")
    print(f"   summarization_percentage: {config.summarization_percentage}%")

    print("\n✓ Flexible configuration for different use cases!")


async def main():
    """Run all compression demos."""
    print("\n" + "=" * 70)
    print("Cortex Orchestration SDK - Conversation Compression")
    print("=" * 70)

    demo_token_estimation()
    demo_compression_detection()
    await demo_llm_compression()
    await demo_fallback_compression()
    await demo_agent_integration()
    await demo_configuration()

    print("\n" + "=" * 70)
    print("All Compression Demos Complete!")
    print("=" * 70)

    print("\n✨ Key Features Demonstrated:")
    print("  1. Token estimation (~4 chars/token heuristic)")
    print("  2. Automatic compression detection (should_compress)")
    print("  3. LLM-based summarization (preserves critical context)")
    print("  4. Fallback compression (simple truncation)")
    print("  5. Agent integration (manual compression of long conversations)")
    print("  6. Flexible configuration (thresholds, models, preservation)")

    print("\n🎯 Use Cases:")
    print("  - Long-running conversations (customer support, tutoring)")
    print("  - Iterative workflows (code generation, debugging)")
    print("  - Multi-turn planning (task decomposition)")
    print("  - Knowledge-intensive tasks (research, analysis)")

    print("\n💡 Best Practices:")
    print("  1. Monitor token counts with estimate_tokens()")
    print("  2. Compress before hitting model limits (use threshold)")
    print("  3. Use LLM summarization for best context preservation")
    print("  4. Keep system message and recent messages uncompressed")
    print("  5. Configure compression based on use case")

    print("\n📊 Compression Strategies:")
    print("  LLM-based (primary):")
    print("    - Summarizes old messages into single context summary")
    print("    - Preserves tool calls, results, task state")
    print("    - Uses fast model (gpt-4o-mini) for cost efficiency")
    print("  Fallback (when LLM unavailable):")
    print("    - Simple truncation (keep recent half)")
    print("    - Preserves tool call-result pairs")
    print("    - Always keeps system message")


if __name__ == "__main__":
    asyncio.run(main())
