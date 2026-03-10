"""
Test script for OpenTelemetry distributed tracing.

Demonstrates:
1. Initializing OpenTelemetry with OTLP exporter
2. Creating custom spans for agent operations
3. Automatic span propagation in multi-agent workflows
4. Exporting traces to Jaeger/Tempo collectors
5. Graceful fallback when collector is unavailable

Prerequisites:
    pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp

Optional (for testing):
    # Run Jaeger all-in-one for local testing
    docker run -d --name jaeger \
        -e COLLECTOR_OTLP_ENABLED=true \
        -p 16686:16686 \
        -p 4318:4318 \
        jaegertracing/all-in-one:latest

    # View traces at: http://localhost:16686

Run with:
    # Auto-initialize via environment variable
    CORTEX_TELEMETRY_ENABLED=1 python examples/test_telemetry.py

    # Or programmatically
    python examples/test_telemetry.py
"""

import asyncio
import time

from cortex.orchestration import (
    Agent,
    ModelConfig,
    get_tracer,
    initialize_telemetry,
    is_telemetry_enabled,
    shutdown_telemetry,
)


async def demo_basic_tracing():
    """Demonstrate basic OpenTelemetry tracing."""
    print("=" * 70)
    print("Demo 1: Basic OpenTelemetry Tracing")
    print("=" * 70)

    # Initialize telemetry
    success = initialize_telemetry(
        service_name="cortex-demo",
        service_version="1.0.0",
        deployment_env="development",
    )

    if not success:
        print("\n⚠️  OpenTelemetry packages not installed")
        print("Install with: pip install opentelemetry-api opentelemetry-sdk")
        return

    print(f"\n✓ Telemetry enabled: {is_telemetry_enabled()}")

    # Get tracer
    tracer = get_tracer(__name__)

    # Create custom span
    with tracer.start_as_current_span("demo-operation") as span:
        span.set_attribute("demo.type", "basic")
        span.set_attribute("demo.id", "123")
        span.add_event("Operation started")

        print("\n📊 Creating span 'demo-operation'...")
        time.sleep(0.5)

        span.add_event("Operation completed")
        print("✓ Span created with attributes and events")

    print("\n✓ Spans are being exported to OTLP collector")
    print("  View traces at: http://localhost:16686 (if using Jaeger)")


async def demo_agent_tracing():
    """Demonstrate automatic tracing of agent operations."""
    print("\n" + "=" * 70)
    print("Demo 2: Agent Operation Tracing")
    print("=" * 70)

    # Initialize telemetry if not already done
    if not is_telemetry_enabled():
        initialize_telemetry(service_name="cortex-agent-demo")

    # Get tracer for custom spans
    tracer = get_tracer(__name__)

    # Create agent
    agent = Agent(
        name="assistant",
        system_prompt="You are a helpful assistant.",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
    )

    # Wrap agent call in custom span
    with tracer.start_as_current_span("agent-conversation") as parent_span:
        parent_span.set_attribute("agent.name", "assistant")
        parent_span.set_attribute("conversation.id", "conv-123")

        print("\n📊 Creating parent span 'agent-conversation'...")

        # Make agent call (this will create child spans internally)
        with tracer.start_as_current_span("agent-query-1") as span:
            span.set_attribute("query.text", "What is 2+2?")
            result1 = await agent.run("What is 2 + 2?")
            span.set_attribute("response.length", len(result1.response))

        print(f"  Query 1: {result1.response}")

        # Another query in same conversation
        with tracer.start_as_current_span("agent-query-2") as span:
            span.set_attribute("query.text", "What is Python?")
            result2 = await agent.run("What is Python?")
            span.set_attribute("response.length", len(result2.response))

        print(f"  Query 2: {result2.response[:100]}...")

        parent_span.set_attribute("conversation.total_queries", 2)

    print("\n✓ Agent operations traced with nested spans")
    print("  Parent: agent-conversation")
    print("    ├─ agent-query-1")
    print("    └─ agent-query-2")


async def demo_multi_agent_tracing():
    """Demonstrate tracing of multi-agent workflows."""
    print("\n" + "=" * 70)
    print("Demo 3: Multi-Agent Workflow Tracing")
    print("=" * 70)

    if not is_telemetry_enabled():
        initialize_telemetry(service_name="cortex-multi-agent")

    tracer = get_tracer(__name__)

    # Create multiple agents
    researcher = Agent(
        name="researcher",
        system_prompt="You are a research assistant.",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
    )

    writer = Agent(
        name="writer",
        system_prompt="You are a writing assistant.",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
    )

    # Multi-agent workflow
    with tracer.start_as_current_span("multi-agent-workflow") as workflow_span:
        workflow_span.set_attribute("workflow.type", "research-and-write")
        workflow_span.set_attribute("workflow.id", "workflow-123")

        print("\n📊 Creating multi-agent workflow span...")

        # Step 1: Research
        with tracer.start_as_current_span("research-phase") as research_span:
            research_span.set_attribute("agent.name", "researcher")
            research_span.add_event("Research started")

            print("  Step 1: Research phase...")
            result1 = await researcher.run("What are key features of Python?")

            research_span.add_event("Research completed")
            research_span.set_attribute("result.length", len(result1.response))

        # Step 2: Writing
        with tracer.start_as_current_span("writing-phase") as writing_span:
            writing_span.set_attribute("agent.name", "writer")
            writing_span.add_event("Writing started")

            print("  Step 2: Writing phase...")
            result2 = await writer.run(
                f"Summarize this in one sentence: {result1.response[:200]}"
            )

            writing_span.add_event("Writing completed")
            writing_span.set_attribute("result.length", len(result2.response))

        workflow_span.set_attribute("workflow.status", "completed")

    print("\n✓ Multi-agent workflow traced:")
    print("  multi-agent-workflow")
    print("    ├─ research-phase (researcher agent)")
    print("    └─ writing-phase (writer agent)")


async def demo_error_tracing():
    """Demonstrate tracing of errors and exceptions."""
    print("\n" + "=" * 70)
    print("Demo 4: Error Tracing")
    print("=" * 70)

    if not is_telemetry_enabled():
        initialize_telemetry(service_name="cortex-error-demo")

    tracer = get_tracer(__name__)

    print("\n📊 Creating span with error...")

    with tracer.start_as_current_span("error-operation") as span:
        span.set_attribute("operation.type", "intentional-error")

        try:
            # Simulate an error
            raise ValueError("This is a test error")
        except ValueError as e:
            # Record exception in span
            from opentelemetry.trace import Status, StatusCode

            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)

            print(f"  ✗ Error recorded in span: {e}")

    print("\n✓ Error traced with exception details")
    print("  Span status: ERROR")
    print("  Exception details captured in trace")


async def demo_baggage_propagation():
    """Demonstrate baggage propagation across spans."""
    print("\n" + "=" * 70)
    print("Demo 5: Baggage Propagation")
    print("=" * 70)

    if not is_telemetry_enabled():
        initialize_telemetry(service_name="cortex-baggage-demo")

    try:
        from opentelemetry import baggage

        tracer = get_tracer(__name__)

        print("\n📊 Setting baggage context...")

        # Set baggage (context that propagates to all child spans)
        ctx = baggage.set_baggage("user.id", "user-123")
        ctx = baggage.set_baggage("session.id", "session-456", context=ctx)
        ctx = baggage.set_baggage("tenant.id", "tenant-789", context=ctx)

        print("  ✓ Baggage set: user.id=user-123, session.id=session-456")

        # Create spans with baggage context
        with tracer.start_as_current_span("parent-with-baggage", context=ctx) as parent:
            parent.set_attribute("operation", "parent")

            print("\n  Creating parent span...")

            # Child span automatically inherits baggage
            with tracer.start_as_current_span("child-with-baggage") as child:
                child.set_attribute("operation", "child")

                print("  Creating child span (inherits baggage)...")

                # Verify baggage is accessible
                user_id = baggage.get_baggage("user.id")
                session_id = baggage.get_baggage("session.id")
                print(f"    Retrieved: user.id={user_id}, session.id={session_id}")

        print("\n✓ Baggage propagated to child spans")
        print("  All spans will have user.id, session.id, tenant.id attributes")

    except ImportError:
        print("\n⚠️  opentelemetry-processor-baggage not installed")
        print("Install with: pip install opentelemetry-processor-baggage")


async def demo_custom_attributes():
    """Demonstrate adding custom attributes to spans."""
    print("\n" + "=" * 70)
    print("Demo 6: Custom Span Attributes")
    print("=" * 70)

    if not is_telemetry_enabled():
        initialize_telemetry(service_name="cortex-attributes-demo")

    tracer = get_tracer(__name__)

    print("\n📊 Creating span with custom attributes...")

    with tracer.start_as_current_span("llm-call") as span:
        # Add custom attributes
        span.set_attribute("llm.provider", "openai")
        span.set_attribute("llm.model", "gpt-4o")
        span.set_attribute("llm.temperature", 0.7)
        span.set_attribute("llm.max_tokens", 1000)
        span.set_attribute("llm.prompt_length", 250)

        print("  ✓ Custom attributes added:")
        print("    - llm.provider: openai")
        print("    - llm.model: gpt-4o")
        print("    - llm.temperature: 0.7")
        print("    - llm.max_tokens: 1000")

        # Simulate LLM call
        await asyncio.sleep(0.3)

        # Add result attributes
        span.set_attribute("llm.response_length", 1234)
        span.set_attribute("llm.tokens_used", 1500)
        span.set_attribute("llm.cost_usd", 0.045)

        print("  ✓ Result attributes added:")
        print("    - llm.response_length: 1234")
        print("    - llm.tokens_used: 1500")
        print("    - llm.cost_usd: 0.045")

    print("\n✓ Custom attributes enable rich filtering and analysis in trace viewer")


async def main():
    """Run all telemetry demos."""
    print("\n" + "=" * 70)
    print("Cortex Orchestration SDK - OpenTelemetry Integration")
    print("=" * 70)

    # Check if auto-initialized
    if is_telemetry_enabled():
        print("\n✓ Telemetry auto-initialized via CORTEX_TELEMETRY_ENABLED")
    else:
        print("\nℹ️  Telemetry not auto-initialized")
        print("  Set CORTEX_TELEMETRY_ENABLED=1 to enable automatically")

    # Run demos
    await demo_basic_tracing()
    await demo_agent_tracing()
    await demo_multi_agent_tracing()
    await demo_error_tracing()
    await demo_baggage_propagation()
    await demo_custom_attributes()

    print("\n" + "=" * 70)
    print("All Telemetry Demos Complete!")
    print("=" * 70)

    print("\n✨ Key Features Demonstrated:")
    print("  1. TracerProvider initialization with resource attributes")
    print("  2. Custom spans for tracking operations")
    print("  3. Nested spans for multi-step workflows")
    print("  4. Multi-agent workflow tracing")
    print("  5. Error and exception tracking")
    print("  6. Baggage propagation for context sharing")
    print("  7. Custom attributes for rich metadata")

    print("\n📊 Viewing Traces:")
    print("  1. Jaeger: http://localhost:16686")
    print("  2. Tempo: Query via Grafana")
    print("  3. Other OTLP-compatible backends")

    print("\n🔧 Configuration:")
    print("  Environment Variables:")
    print("    - OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318")
    print("    - OTEL_SERVICE_NAME=cortex-ai")
    print("    - OTEL_SERVICE_VERSION=1.0.0")
    print("    - OTEL_DEPLOYMENT_ENV=production")
    print("    - DISABLE_OTEL=true (disable exporting)")
    print("    - CORTEX_TELEMETRY_ENABLED=1 (auto-initialize)")

    # Shutdown telemetry
    print("\n🔄 Shutting down telemetry (flushing pending spans)...")
    shutdown_telemetry()
    print("✓ Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
