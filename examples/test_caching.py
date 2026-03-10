"""
Test script for Anthropic prompt caching.

Run this to verify caching reduces token usage.
Requires ANTHROPIC_API_KEY environment variable.
"""

import asyncio
import os

from cortex.orchestration import Agent, AnthropicCachingStrategy, ModelConfig


async def main():
    # Check API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY environment variable not set")
        return

    # Create a long system prompt (caching works best with 1024+ tokens)
    system_prompt = """You are an expert software architect with deep knowledge of:

1. System Design Patterns:
   - Microservices architecture
   - Event-driven architecture
   - CQRS and Event Sourcing
   - Domain-Driven Design (DDD)
   - Hexagonal Architecture
   - Clean Architecture

2. Scalability & Performance:
   - Load balancing strategies
   - Caching strategies (Redis, Memcached)
   - Database sharding and replication
   - CDN and edge computing
   - Horizontal vs vertical scaling

3. Cloud Infrastructure:
   - AWS services (EC2, S3, Lambda, RDS, DynamoDB)
   - Google Cloud Platform (GCE, Cloud Storage, Cloud Functions)
   - Azure services
   - Kubernetes and container orchestration
   - Infrastructure as Code (Terraform, CloudFormation)

4. Data Engineering:
   - ETL pipelines
   - Data lakes and data warehouses
   - Stream processing (Kafka, Kinesis)
   - Batch processing (Spark, Airflow)
   - OLTP vs OLAP databases

5. Security Best Practices:
   - Authentication and authorization (OAuth2, JWT, SAML)
   - Encryption at rest and in transit
   - Zero-trust security models
   - Secret management (Vault, AWS Secrets Manager)
   - API security and rate limiting

Provide detailed, production-ready architectural recommendations with trade-offs.
"""

    print("=" * 70)
    print("Anthropic Prompt Caching Test")
    print("=" * 70)
    print(f"\nSystem prompt length: ~{len(system_prompt)} characters")
    print("(Caching requires 1024+ tokens, ~4000+ chars)")

    # Create agent with caching enabled
    agent = Agent(
        name="architect",
        system_prompt=system_prompt,
        model=ModelConfig(
            model="claude-sonnet-4",
            caching_strategy=AnthropicCachingStrategy(),
        ),
    )

    # First call - creates cache
    print("\n" + "-" * 70)
    print("CALL 1: Creating cache...")
    print("-" * 70)

    result1 = await agent.run(
        "How would you design a scalable e-commerce platform?",
        thread_id="caching-test",
    )

    print(f"\nResponse preview: {result1.response[:200]}...")
    print(f"\nToken Usage:")
    for model, usage in result1.token_usage.items():
        print(f"  Model: {model}")
        print(f"    Prompt tokens: {usage.get('prompt_tokens', 0)}")
        print(f"    Completion tokens: {usage.get('completion_tokens', 0)}")
        if "cache" in usage:
            cache = usage["cache"]
            print(f"    Cache read: {cache.get('cache_read', 0)}")
            print(f"    Cache creation: {cache.get('cache_creation', 0)}")

    # Second call - reads from cache
    print("\n" + "-" * 70)
    print("CALL 2: Using cache (same thread)...")
    print("-" * 70)

    result2 = await agent.run(
        "What database would you recommend for this platform?",
        thread_id="caching-test",
    )

    print(f"\nResponse preview: {result2.response[:200]}...")
    print(f"\nToken Usage:")
    for model, usage in result2.token_usage.items():
        print(f"  Model: {model}")
        print(f"    Prompt tokens: {usage.get('prompt_tokens', 0)}")
        print(f"    Completion tokens: {usage.get('completion_tokens', 0)}")
        if "cache" in usage:
            cache = usage["cache"]
            print(f"    Cache read: {cache.get('cache_read', 0)}")
            print(f"    Cache creation: {cache.get('cache_creation', 0)}")

    # Calculate savings
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)

    call1_prompt = list(result1.token_usage.values())[0].get("prompt_tokens", 0)
    call2_prompt = list(result2.token_usage.values())[0].get("prompt_tokens", 0)
    call2_cache_read = (
        list(result2.token_usage.values())[0].get("cache", {}).get("cache_read", 0)
    )

    print(f"\nCall 1 prompt tokens: {call1_prompt}")
    print(f"Call 2 prompt tokens: {call2_prompt}")
    print(f"Call 2 cache read tokens: {call2_cache_read}")

    if call2_cache_read > 0:
        savings = ((call1_prompt - call2_prompt) / call1_prompt * 100) if call1_prompt > 0 else 0
        print(f"\n✅ Cache HIT! Token reduction: {savings:.1f}%")
        print(f"💰 Cost savings: ~{savings:.1f}% on prompt tokens")
    else:
        print("\n⚠️  No cache detected. Possible reasons:")
        print("   - System prompt < 1024 tokens (need ~4000+ chars)")
        print("   - Model doesn't support caching")
        print("   - Cache expired (5 min TTL)")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
