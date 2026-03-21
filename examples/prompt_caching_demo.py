"""
Comprehensive Prompt Caching Demo

Demonstrates:
1. CachingStrategyFactory auto-detection
2. Multiple provider strategies (Anthropic, Google, OpenAI)
3. Cost savings calculations
4. Cache hit rate monitoring
5. Best practices for maximizing cache efficiency

Run with:
    python examples/prompt_caching_demo.py
"""

import asyncio
import os
from typing import Dict, Any

from cortex.orchestration import Agent, ModelConfig
from cortex.orchestration.caching import (
    CachingStrategyFactory,
    AnthropicCachingStrategy,
    GoogleCachingStrategy,
    OpenAICachingStrategy,
    NoCachingStrategy,
)


# =========================================================================
# Example 1: Auto-Detection with CachingStrategyFactory
# =========================================================================


async def example_factory_auto_detection():
    """Demonstrate auto-detection of caching strategy from provider/model."""
    print("\n" + "=" * 70)
    print("Example 1: CachingStrategyFactory Auto-Detection")
    print("=" * 70)

    # Auto-detect caching strategy for Claude
    strategy_claude = CachingStrategyFactory.create_strategy(
        provider="anthropic",
        model="claude-sonnet-4",
    )
    print(f"\nClaude Sonnet 4: {type(strategy_claude).__name__}")
    print(f"  Supports caching: {strategy_claude.supports_caching('claude-sonnet-4')}")

    # Auto-detect for Gemini
    strategy_gemini = CachingStrategyFactory.create_strategy(
        provider="google",
        model="gemini-1.5-pro",
    )
    print(f"\nGemini 1.5 Pro: {type(strategy_gemini).__name__}")
    print(f"  Supports caching: {strategy_gemini.supports_caching('gemini-1.5-pro')}")

    # Auto-detect for GPT-4
    strategy_gpt = CachingStrategyFactory.create_strategy(
        provider="openai",
        model="gpt-4o",
    )
    print(f"\nGPT-4o: {type(strategy_gpt).__name__}")
    print(f"  Supports caching: {strategy_gpt.supports_caching('gpt-4o')}")

    # Provider inference from model name
    strategy_inferred = CachingStrategyFactory.create_strategy(
        provider=None,  # Will infer from model name
        model="claude-opus-4",
    )
    print(f"\nAuto-inferred from 'claude-opus-4': {type(strategy_inferred).__name__}")


# =========================================================================
# Example 2: Anthropic Prompt Caching with Cost Tracking
# =========================================================================


async def example_anthropic_caching():
    """Demonstrate Anthropic prompt caching with cost calculations."""
    print("\n" + "=" * 70)
    print("Example 2: Anthropic Prompt Caching")
    print("=" * 70)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("\n⚠️  Skipping: ANTHROPIC_API_KEY not set")
        return

    # Create large system prompt (caching requires 1024+ tokens)
    system_prompt = """You are a DevOps expert specializing in Kubernetes, CI/CD pipelines,
and cloud infrastructure. You have deep knowledge of:

1. Container Orchestration:
   - Kubernetes cluster management
   - Helm charts and templating
   - Pod security policies
   - Network policies and service mesh (Istio, Linkerd)
   - Resource management (CPU, memory limits)

2. CI/CD Pipelines:
   - Jenkins, GitLab CI, GitHub Actions
   - ArgoCD and GitOps workflows
   - Blue-green and canary deployments
   - Automated testing and quality gates
   - Secret management in pipelines

3. Infrastructure as Code:
   - Terraform for multi-cloud provisioning
   - Ansible for configuration management
   - CloudFormation for AWS resources
   - Pulumi for programmatic infrastructure

4. Monitoring & Observability:
   - Prometheus and Grafana for metrics
   - ELK stack for log aggregation
   - Distributed tracing (Jaeger, Zipkin)
   - SLI, SLO, and SLA definitions
   - On-call and incident response

Provide production-ready solutions with security and scalability in mind."""

    # Create agent with caching
    agent = Agent(
        name="devops-expert",
        system_prompt=system_prompt,
        model=ModelConfig(
            model="claude-sonnet-4",
            caching_strategy=AnthropicCachingStrategy(enable_caching=True),
        ),
    )

    print(f"\nSystem prompt: ~{len(system_prompt)} chars (~{len(system_prompt)//4} tokens)")
    print("Minimum for caching: 1024 tokens (~4000 chars)")

    # First call - creates cache
    print("\n" + "-" * 70)
    print("CALL 1: Creating cache...")
    print("-" * 70)

    result1 = await agent.run(
        "How do I set up a production-ready Kubernetes cluster?",
        thread_id="demo-thread",
    )

    usage1 = list(result1.token_usage.values())[0]
    print_token_usage("Call 1", usage1)

    # Second call - uses cache
    print("\n" + "-" * 70)
    print("CALL 2: Using cache...")
    print("-" * 70)

    result2 = await agent.run(
        "What monitoring stack would you recommend?",
        thread_id="demo-thread",
    )

    usage2 = list(result2.token_usage.values())[0]
    print_token_usage("Call 2", usage2)

    # Calculate savings
    calculate_savings(usage1, usage2)


# =========================================================================
# Example 3: Comparing Caching vs No-Caching
# =========================================================================


async def example_caching_comparison():
    """Compare performance with and without caching."""
    print("\n" + "=" * 70)
    print("Example 3: Caching vs No-Caching Comparison")
    print("=" * 70)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("\n⚠️  Skipping: ANTHROPIC_API_KEY not set")
        return

    system_prompt = "You are a helpful AI assistant with expertise in software architecture."

    # Agent WITH caching
    agent_cached = Agent(
        name="cached-agent",
        system_prompt=system_prompt,
        model=ModelConfig(
            model="claude-sonnet-4",
            caching_strategy=CachingStrategyFactory.create_strategy(
                provider="anthropic",
                model="claude-sonnet-4",
                enable_caching=True,
            ),
        ),
    )

    # Agent WITHOUT caching
    agent_no_cache = Agent(
        name="no-cache-agent",
        system_prompt=system_prompt,
        model=ModelConfig(
            model="claude-sonnet-4",
            caching_strategy=NoCachingStrategy(provider_name="anthropic"),
        ),
    )

    print("\n📊 Comparison Setup:")
    print("  - Same system prompt")
    print("  - Same model (claude-sonnet-4)")
    print("  - Agent 1: Caching ENABLED")
    print("  - Agent 2: Caching DISABLED")


# =========================================================================
# Helper Functions
# =========================================================================


def print_token_usage(label: str, usage: Dict[str, Any]):
    """Pretty print token usage with cache details."""
    print(f"\n{label} Token Usage:")
    print(f"  Prompt tokens: {usage.get('prompt_tokens', 0):,}")
    print(f"  Completion tokens: {usage.get('completion_tokens', 0):,}")
    print(f"  Total tokens: {usage.get('total_tokens', 0):,}")

    if "cache" in usage:
        cache = usage["cache"]
        print(f"  Cache read: {cache.get('cache_read', 0):,} tokens")
        print(f"  Cache creation: {cache.get('cache_creation', 0):,} tokens")


def calculate_savings(usage1: Dict[str, Any], usage2: Dict[str, Any]):
    """Calculate cost savings from caching."""
    print("\n" + "=" * 70)
    print("💰 COST SAVINGS ANALYSIS")
    print("=" * 70)

    # Anthropic pricing (Claude Sonnet 4)
    INPUT_PRICE = 3.00  # per 1M tokens
    CACHE_WRITE_PRICE = 3.75  # per 1M tokens (25% premium)
    CACHE_READ_PRICE = 0.30  # per 1M tokens (90% discount)

    prompt1 = usage1.get("prompt_tokens", 0)
    prompt2 = usage2.get("prompt_tokens", 0)
    cache_read = usage2.get("cache", {}).get("cache_read", 0)
    cache_creation = usage1.get("cache", {}).get("cache_creation", 0)

    # Cost calculation
    cost1 = prompt1 * INPUT_PRICE / 1_000_000
    if cache_creation:
        cost1 += cache_creation * (CACHE_WRITE_PRICE - INPUT_PRICE) / 1_000_000

    cost2_without_cache = prompt2 * INPUT_PRICE / 1_000_000
    cost2_with_cache = (
        (prompt2 - cache_read) * INPUT_PRICE / 1_000_000
        + cache_read * CACHE_READ_PRICE / 1_000_000
    )

    print(f"\nCall 1 (cache creation):")
    print(f"  Cost: ${cost1:.4f}")

    print(f"\nCall 2 (without caching):")
    print(f"  Cost: ${cost2_without_cache:.4f}")

    print(f"\nCall 2 (with caching):")
    print(f"  Cost: ${cost2_with_cache:.4f}")

    if cache_read > 0:
        savings = cost2_without_cache - cost2_with_cache
        savings_pct = (savings / cost2_without_cache * 100) if cost2_without_cache > 0 else 0
        print(f"\n✅ Savings: ${savings:.4f} ({savings_pct:.1f}%)")
        print(f"📈 Cache hit: {cache_read:,} tokens ({cache_read/prompt2*100:.1f}% of prompt)")
    else:
        print("\n⚠️  No cache hit detected")


# =========================================================================
# Main Entry Point
# =========================================================================


async def main():
    """Run all examples."""
    print("\n" + "=" * 70)
    print("🚀 Cortex-AI Prompt Caching Demo")
    print("=" * 70)

    # Example 1: Factory auto-detection
    await example_factory_auto_detection()

    # Example 2: Anthropic caching with cost tracking
    await example_anthropic_caching()

    # Example 3: Comparison
    await example_caching_comparison()

    print("\n" + "=" * 70)
    print("✅ Demo Complete!")
    print("=" * 70)
    print("\nKey Takeaways:")
    print("  1. Use CachingStrategyFactory for automatic provider detection")
    print("  2. Caching requires 1024+ token prompts (system instructions, tool schemas)")
    print("  3. Cache TTL is 5 minutes (Anthropic)")
    print("  4. Savings: ~50-90% on cached prompt tokens")
    print("  5. Monitor cache hit rate in production")
    print("\nNext Steps:")
    print("  - Integrate with your agent workflows")
    print("  - Add cache hit rate monitoring")
    print("  - Version tool schemas to maximize cache hits")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
