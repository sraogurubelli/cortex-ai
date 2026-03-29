# Prompt Caching Quick Start Guide

**TL;DR**: Save 50-90% on LLM costs by caching system prompts and tool schemas.

---

## 🚀 Quick Start (30 seconds)

```python
from cortex.orchestration import Agent, ModelConfig
from cortex.orchestration.caching import CachingStrategyFactory

# Auto-detect caching from model name
strategy = CachingStrategyFactory.create_strategy(
    provider=None,  # Auto-infer
    model="claude-sonnet-4"
)

agent = Agent(
    name="assistant",
    system_prompt="Your large system prompt here...",  # Will be cached
    model=ModelConfig(
        model="claude-sonnet-4",
        caching_strategy=strategy
    )
)

# First call - creates cache
result1 = await agent.run("Hello!", thread_id="demo")

# Second call - uses cache (90% cheaper on cached tokens)
result2 = await agent.run("How are you?", thread_id="demo")
```

---

## 💰 Cost Savings

### Without Caching
```
Request 1: 7200 tokens × $3.00/1M = $0.0216
Request 2: 7200 tokens × $3.00/1M = $0.0216
Total: $0.0432
```

### With Caching
```
Request 1: 7200 tokens × $3.75/1M = $0.0270 (cache write, 25% premium)
Request 2: 7000 cached × $0.30/1M + 200 fresh × $3.00/1M = $0.0027
Total: $0.0297

Savings: 31% ($0.0135)
```

With **70% cache hit rate** over 1000 requests: **~55% total savings**.

---

## 📋 Requirements

### What Gets Cached

✅ System prompts (1024+ tokens)
✅ Tool schemas (large tool lists)
✅ Few-shot examples
✅ Static instructions

❌ User messages (always fresh)
❌ Dynamic context (timestamps, user IDs)

### Minimum Size

- **Anthropic**: 1024 tokens (~4000 characters)
- **Google**: Similar for Gemini 1.5+

### TTL (Time to Live)

- **Anthropic**: 5 minutes of inactivity
- **Google**: Configurable up to 1 hour

---

## 🎯 Supported Providers

| Provider | Status | Models | Strategy |
|----------|--------|--------|----------|
| **Anthropic** | ✅ Full Support | Claude 4.6, 4.5, 4, 3.7, 3.5, 3 | `AnthropicCachingStrategy` |
| **Google** | 🟡 Ready | Gemini 1.5+, 2.0+ | `GoogleCachingStrategy` |
| **OpenAI** | ❌ Not Available | N/A (API not released) | `NoCachingStrategy` |

---

## 📖 Usage Patterns

### Pattern 1: Auto-Detection (Recommended)

```python
from cortex.orchestration.caching import CachingStrategyFactory

# Automatically infers provider from model name
strategy = CachingStrategyFactory.create_strategy(
    provider=None,  # Will infer "anthropic" from "claude-*"
    model="claude-opus-4"
)
```

### Pattern 2: Explicit Strategy

```python
from cortex.orchestration.caching import AnthropicCachingStrategy

config = ModelConfig(
    model="claude-sonnet-4",
    caching_strategy=AnthropicCachingStrategy(enable_caching=True)
)
```

### Pattern 3: Disable Caching

```python
from cortex.orchestration.caching import NoCachingStrategy

config = ModelConfig(
    model="claude-sonnet-4",
    caching_strategy=NoCachingStrategy(provider_name="anthropic")
)

# Or simply:
config = ModelConfig(model="claude-sonnet-4")  # No caching_strategy
```

### Pattern 4: Conditional Caching

```python
import os

enable_cache = os.getenv("ENABLE_PROMPT_CACHING", "true").lower() == "true"

strategy = CachingStrategyFactory.create_strategy(
    provider="anthropic",
    model="claude-sonnet-4",
    enable_caching=enable_cache
)
```

---

## 📊 Monitoring Cache Performance

### Check Token Usage

```python
result = await agent.run("query", thread_id="session-123")

for model, usage in result.token_usage.items():
    print(f"Model: {model}")
    print(f"  Prompt tokens: {usage['prompt_tokens']:,}")
    print(f"  Completion tokens: {usage['completion_tokens']:,}")

    if "cache" in usage:
        cache = usage["cache"]
        print(f"  Cache read: {cache.get('cache_read', 0):,}")
        print(f"  Cache creation: {cache.get('cache_creation', 0):,}")
```

### Calculate Cache Hit Rate

```python
cache_read = usage.get("cache", {}).get("cache_read", 0)
total_prompt = usage.get("prompt_tokens", 0)

if total_prompt > 0:
    hit_rate = (cache_read / total_prompt) * 100
    print(f"Cache hit rate: {hit_rate:.1f}%")

    if hit_rate < 50:
        print("⚠️  Low cache hit rate - investigate cache expiry")
```

---

## ✅ Best Practices

### DO ✅

1. **Keep system prompts static**
   ```python
   # Good - static
   system_prompt = "You are a DevOps expert..."

   # Bad - dynamic (breaks caching)
   system_prompt = f"You are a DevOps expert. Today is {datetime.now()}..."
   ```

2. **Put dynamic data in user messages**
   ```python
   # Good
   system_prompt = "You are an assistant for users."
   user_message = f"I'm {user_name}. Help me with..."

   # Bad
   system_prompt = f"You are an assistant for {user_name}."
   ```

3. **Version tool schemas**
   ```python
   # Good - stable schema
   TOOLS_V1 = [tool1, tool2, tool3]
   agent = Agent(tools=TOOLS_V1)

   # Bad - frequently changing
   agent = Agent(tools=get_latest_tools())  # Changes often
   ```

4. **Batch requests within TTL window**
   ```python
   # Within 5 minutes - cache hits
   result1 = await agent.run("query 1", thread_id="session")  # Cache write
   result2 = await agent.run("query 2", thread_id="session")  # Cache hit ✓
   result3 = await agent.run("query 3", thread_id="session")  # Cache hit ✓
   ```

### DON'T ❌

1. **Don't use caching for short prompts**
   ```python
   # Bad - too short (<1024 tokens)
   system_prompt = "You are helpful."
   # Caching won't activate
   ```

2. **Don't include timestamps in cached content**
   ```python
   # Bad
   system_prompt = f"Current time: {datetime.now()}. You are..."
   # Cache breaks on every request
   ```

3. **Don't cache user-specific data**
   ```python
   # Bad
   system_prompt = f"User ID: {user_id}. User preferences: {prefs}..."
   # Defeats caching purpose
   ```

---

## 🔍 Troubleshooting

### Cache Not Working?

**Symptom**: `cache_read` is always 0

**Checks**:
1. System prompt long enough? (1024+ tokens ≈ 4000 chars)
2. Model supports caching? (Claude 3+, not Claude 2)
3. Same thread_id across requests?
4. Requests within 5-minute window?
5. System prompt changed between requests?

**Debug**:
```python
strategy = CachingStrategyFactory.create_strategy(
    provider="anthropic",
    model="claude-sonnet-4"
)

print(f"Strategy: {type(strategy).__name__}")
print(f"Supports caching: {strategy.supports_caching('claude-sonnet-4')}")

# Check system prompt length
chars = len(system_prompt)
estimated_tokens = chars // 4
print(f"System prompt: {chars} chars ≈ {estimated_tokens} tokens")
if estimated_tokens < 1024:
    print("⚠️  Too short for caching (need 1024+ tokens)")
```

### Low Cache Hit Rate?

**Target**: >50% cache hit rate

**Common causes**:
- TTL expiry (5 min gap between requests)
- Changing system prompts
- Different thread IDs
- Rapidly evolving tool schemas

**Fix**:
```python
# Lock tool schema version
TOOL_SCHEMA_VERSION = "v1"
tools = get_tools(version=TOOL_SCHEMA_VERSION)

# Use consistent thread grouping
thread_id = f"user-{user_id}-session"  # Groups user requests

# Monitor TTL
last_request_time = time.time()
# ... later ...
if time.time() - last_request_time > 240:  # 4 min
    print("⚠️  Approaching TTL expiry, cache may miss")
```

---

## 📚 Examples

### Example 1: Billing Agent with Tool Schemas

```python
from cortex.orchestration import Agent, ModelConfig
from cortex.orchestration.caching import CachingStrategyFactory

# Large system prompt + tool schemas = great for caching
system_prompt = """
You are a billing expert with knowledge of:
- Invoice processing and validation
- Payment reconciliation
- Subscription management
- Revenue recognition (ASC 606)
- Dunning and collections
... (2000+ words of instructions)
"""

tools = [
    get_invoice_tool(),
    search_customers_tool(),
    create_payment_tool(),
    # ... 20 tools total
]

agent = Agent(
    name="billing-agent",
    system_prompt=system_prompt,
    tools=tools,
    model=ModelConfig(
        model="claude-sonnet-4",
        caching_strategy=CachingStrategyFactory.create_strategy(
            provider="anthropic",
            model="claude-sonnet-4"
        )
    )
)

# Session with multiple queries (cache hits after first)
result1 = await agent.run("Find invoice INV-001", thread_id="user-123")
result2 = await agent.run("What's the status?", thread_id="user-123")  # Cache hit!
result3 = await agent.run("Send reminder", thread_id="user-123")  # Cache hit!
```

### Example 2: Multi-Provider Setup

```python
from cortex.orchestration.caching import CachingStrategyFactory

# Anthropic with caching
claude_agent = Agent(
    name="claude",
    model=ModelConfig(
        model="claude-sonnet-4",
        caching_strategy=CachingStrategyFactory.create_strategy(
            provider="anthropic",
            model="claude-sonnet-4"
        )
    )
)

# Google with caching
gemini_agent = Agent(
    name="gemini",
    model=ModelConfig(
        model="gemini-1.5-pro",
        caching_strategy=CachingStrategyFactory.create_strategy(
            provider="google",
            model="gemini-1.5-pro"
        )
    )
)

# OpenAI without caching (not supported)
gpt_agent = Agent(
    name="gpt",
    model=ModelConfig(
        model="gpt-4o"
        # No caching_strategy - OpenAI doesn't support it
    )
)
```

---

## 🎓 Advanced: Custom Strategies

Extend the factory with custom providers:

```python
from cortex.orchestration.caching import CachingStrategy, CachingStrategyFactory

class CustomCachingStrategy(CachingStrategy):
    def supports_caching(self, model_name: str) -> bool:
        return "custom-model" in model_name.lower()

    def get_cache_config(self) -> dict:
        return {"custom_cache_param": True}

    def extract_cache_tokens(self, response) -> CacheTokens:
        # Custom extraction logic
        return CacheTokens()

# Register custom strategy
CachingStrategyFactory.register_strategy("custom", CustomCachingStrategy)

# Use it
strategy = CachingStrategyFactory.create_strategy(
    provider="custom",
    model="custom-model-v1"
)
```

---

## 📖 Further Reading

- **Implementation Doc**: [prompt-caching-implementation.md](./prompt-caching-implementation.md)
- **Anthropic Docs**: https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
- **Examples**: `examples/prompt_caching_demo.py`, `examples/test_caching.py`
- **Source Code**: `cortex/orchestration/caching/`

---

## ❓ FAQ

**Q: Does caching work across different thread_ids?**
A: No, each thread has its own cache. Use the same `thread_id` for related requests.

**Q: What happens if my system prompt is 900 tokens?**
A: Caching won't activate. Need 1024+ tokens. Add more instructions or examples.

**Q: Can I cache user messages?**
A: Anthropic allows it, but it's rarely useful since user messages are always unique.

**Q: Does caching slow down the first request?**
A: Slightly (cache write has 25% cost premium), but subsequent requests are 90% cheaper.

**Q: How do I know if caching is working?**
A: Check `result.token_usage[model]["cache"]["cache_read"]` > 0

**Q: What if I don't provide a caching_strategy?**
A: No caching will be used. It's opt-in.

---

**Last Updated**: 2026-03-19
**Version**: 1.0
