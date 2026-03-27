# Claude Code Guide: Project Configuration & Skills

**Complete reference for CLAUDE.md files, AGENTS.md files, and Skills in Claude Code**

**Status:** Production
**Updated:** March 2026
**Target Audience:** Developers working on cortex-ai

---

## Table of Contents

1. [Introduction](#introduction)
2. [CLAUDE.md Files](#claudemd-files)
3. [AGENTS.md Files](#agentsmd-files)
4. [Skills](#skills)
5. [Practical Setup for Cortex-AI](#practical-setup-for-cortex-ai)
6. [Best Practices](#best-practices)
7. [Examples](#examples)
8. [Troubleshooting](#troubleshooting)
9. [Advanced Topics](#advanced-topics)
10. [Next Steps & References](#next-steps--references)

---

## Introduction

### What is Claude Code?

Claude Code is Anthropic's official CLI and IDE extension that brings Claude AI directly into your development workflow. It provides:

- **Interactive coding assistance** with full codebase context
- **Project memory** via CLAUDE.md configuration files
- **Reusable workflows** via Skills
- **Multi-agent orchestration** for complex tasks

### Why These Concepts Matter

When working on cortex-ai, you'll encounter three key configuration concepts:

| Concept | Purpose | Use Case |
|---------|---------|----------|
| **CLAUDE.md** | Persistent project instructions | "Always use async/await for Agent methods" |
| **AGENTS.md** | Multi-tool compatibility | Share instructions across Claude Code and other AI tools |
| **Skills** | Reusable task bundles | `/orchestration-dev` skill for agent creation patterns |

### Relationship Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     Claude Code Session                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────┐      ┌─────────────┐      ┌─────────────┐ │
│  │ CLAUDE.md   │      │ AGENTS.md   │      │   Skills    │ │
│  │             │      │             │      │             │ │
│  │ Project     │◄─────│ Import via  │      │ Invoked via │ │
│  │ rules &     │      │ @AGENTS.md  │      │ /skill-name │ │
│  │ guidelines  │      │             │      │             │ │
│  └─────────────┘      └─────────────┘      └─────────────┘ │
│        │                                           │         │
│        └──────────────────┬────────────────────────┘         │
│                           ▼                                  │
│              ┌─────────────────────────┐                     │
│              │   Claude's Context      │                     │
│              │   (Loaded at session    │                     │
│              │    start or on-demand)  │                     │
│              └─────────────────────────┘                     │
└─────────────────────────────────────────────────────────────┘
```

**Key Insight:** CLAUDE.md files are loaded automatically at session start. Skills are invoked on-demand. AGENTS.md is for other tools but can be imported by Claude Code.

---

## CLAUDE.md Files

### What Are CLAUDE.md Files?

CLAUDE.md files give Claude persistent instructions for your project. They carry knowledge **across sessions** since each Claude Code session starts with a fresh context window.

Think of CLAUDE.md as:
- **Project README for Claude** - Explains how your codebase works
- **Team coding standards** - Enforces patterns and conventions
- **Development guidelines** - Build commands, test strategies, architecture notes

### File Format

CLAUDE.md is plain markdown with optional `@import` syntax:

```markdown
# Project Name

## Build Commands
- Run tests: `pytest tests/`
- Start server: `uvicorn app:app --reload`

## Architecture
API handlers live in `cortex/api/`.
Orchestration agents in `cortex/orchestration/agent.py`.

## Imports
See @README.md for project overview
See @docs/ORCHESTRATION_ARCHITECTURE.md for architecture details
```

**Supported features:**
- ✅ Markdown headers, bullets, code blocks
- ✅ `@path/to/file` to import other files
- ✅ HTML comments (stripped before injection, don't consume tokens)
- ❌ No special frontmatter or YAML (that's for Skills)

### Loading Hierarchy

CLAUDE.md files can live in multiple locations with specific precedence:

| Location | Path | Scope | Precedence |
|----------|------|-------|------------|
| **Managed Policy** | • macOS: `/Library/Application Support/ClaudeCode/CLAUDE.md`<br/>• Linux: `/etc/claude-code/CLAUDE.md`<br/>• Windows: `C:\Program Files\ClaudeCode\CLAUDE.md` | Organization-wide | **Highest** |
| **Project** | `./CLAUDE.md` or `./.claude/CLAUDE.md` | Team-shared (via git) | Middle |
| **User** | `~/.claude/CLAUDE.md` | Personal preferences | **Lowest** |

**How loading works:**

1. Claude walks **up the directory tree** from your working directory
2. Loads all CLAUDE.md files found (merged together)
3. More specific paths **override** broader ones
4. CLAUDE.md in subdirectories load **on-demand** when Claude reads files in those directories

**Example:**
```
/Users/dev/
├── .claude/CLAUDE.md           # Personal preferences (loaded)
└── cortex-ai/
    ├── CLAUDE.md                # Project root (loaded)
    └── cortex/
        └── orchestration/
            └── CLAUDE.md        # Loaded when working with orchestration code
```

### Best Practices

#### Size Limits

Target **under 200 lines per file**. Longer files:
- Consume more context tokens
- Reduce adherence (Claude may skip parts)
- Are harder to maintain

**Solution:** Use `.claude/rules/` directory for large projects (see below).

#### Structure

Use markdown headers and bullets. Claude scans structure like readers do:

```markdown
# ✅ Good - Organized, scannable
## Code Style
- Use 2-space indentation
- Follow ESLint configuration

## Testing
- Run `pytest` before committing
- Aim for 80% coverage

# ❌ Bad - Dense paragraph
Here are some guidelines: use 2-space indentation and follow ESLint,
also run pytest before committing and aim for 80% coverage...
```

#### Specificity

Write concrete, verifiable instructions:

```markdown
# ✅ Good - Specific
- API handlers live in `cortex/api/routes/`
- Use `ModelConfig(model="gpt-4o")` for default model
- All async functions must include proper error handling

# ❌ Bad - Vague
- Keep files organized
- Use good models
- Handle errors properly
```

#### Imports

Use `@path/to/file` to pull in existing documentation:

```markdown
# Cortex-AI Development Guide

@README.md  <!-- Imports project overview -->
@docs/ORCHESTRATION_ARCHITECTURE.md  <!-- Imports architecture details -->

## Additional Guidelines
- Always use `await agent.run()` not blocking calls
- Context injection via `ToolRegistry.set_context()`
```

**Benefits:**
- No duplication
- Always up-to-date (reads latest file content)
- Saves context tokens

### `.claude/rules/` Directory

For larger projects, organize instructions into multiple files:

```
cortex-ai/
├── .claude/
│   ├── CLAUDE.md           # Main entry point (short)
│   └── rules/
│       ├── orchestration.md  # Agent development rules
│       ├── api.md            # API endpoint conventions
│       ├── testing.md        # Testing requirements
│       └── rag/
│           └── graphrag.md   # GraphRAG specific rules
```

#### Main CLAUDE.md (Entry Point)

```markdown
# Cortex-AI Development Guide

@README.md
@CONTRIBUTING.md

See `.claude/rules/` for detailed guidelines.
```

#### Path-Specific Rules

Rules can use **frontmatter** to apply only to certain files:

**File:** `.claude/rules/api.md`
```markdown
---
paths:
  - "cortex/api/**/*.py"
  - "tests/api/**/*.py"
---

# API Development Rules

## Endpoint Structure
- All endpoints must use FastAPI dependency injection
- Include OpenAPI documentation with examples
- Validate input with Pydantic models

## Error Handling
- Use standard HTTPException for client errors
- Log all 500 errors to Sentry
- Return consistent error response format:
  ```python
  {
    "error": "error_code",
    "message": "Human readable message",
    "details": {...}
  }
  ```

## Testing
- All endpoints must have integration tests
- Mock external services (LLM providers, databases)
```

**How it works:**
- Rules only load when Claude works with files matching the path patterns
- Saves context space (irrelevant rules stay out)
- Keeps guidelines modular and maintainable

#### Cortex-AI Example Structure

Recommended for cortex-ai:

```markdown
.claude/rules/
├── orchestration.md    # paths: cortex/orchestration/**/*.py
├── api.md              # paths: cortex/api/**/*.py
├── rag.md              # paths: cortex/rag/**/*.py
├── memory.md           # paths: cortex/memory/**/*.py
└── testing.md          # paths: tests/**/*.py
```

---

## AGENTS.md Files

### What Are AGENTS.md Files?

AGENTS.md is a file format used by **other AI coding agents** (not Claude Code). If your repository already has an AGENTS.md file for another tool, Claude Code won't read it directly.

**Key distinction:**

| File | Reader | Purpose |
|------|--------|---------|
| **CLAUDE.md** | Claude Code | Instructions for Claude Code sessions |
| **AGENTS.md** | Other AI tools | Instructions for Cursor, Cody, GitHub Copilot, etc. |

### Why Use AGENTS.md?

**Scenario:** Your team uses multiple AI coding tools:
- Claude Code for complex refactoring
- Cursor for daily development
- GitHub Copilot for autocomplete

**Problem:** Maintaining separate instruction files (CLAUDE.md, cursor-rules.md, copilot-instructions.md) leads to duplication and drift.

**Solution:** Single source of truth in AGENTS.md.

### Import Pattern

Make Claude Code read AGENTS.md using `@import` syntax:

**File:** `CLAUDE.md`
```markdown
# Claude Code Configuration

@AGENTS.md  <!-- Import shared instructions -->

## Claude Code Specific

Use plan mode for changes under `cortex/orchestration/`.
Use Explore agent for codebase searches.
```

**Result:**
- AGENTS.md remains the source of truth shared across tools
- Claude Code reads the imported content at session start
- You can add Claude-specific instructions below the import
- No duplication

### Cortex-AI Recommendation

**For cortex-ai project:**

✅ **Use CLAUDE.md only** (recommended)
- Team primarily uses Claude Code
- No need for multi-tool compatibility yet
- Simpler to maintain

⚠️ **Use AGENTS.md + import** (if needed)
- Team uses multiple AI tools
- Want single source of truth
- Create CLAUDE.md that imports AGENTS.md

---

## Skills

### What Are Skills?

Skills are **reusable instructions packaged as tools**. They extend what Claude can do by bundling:
- Step-by-step instructions for specific actions
- Reference material and guidelines
- Supporting files (templates, examples, scripts)
- Dynamic context injection

**Invoke skills with:**
- `/skill-name` (you type this explicitly)
- Auto-activation (Claude loads when relevant to your conversation)

### File Format & Structure

Skills use the `SKILL.md` file format with optional YAML frontmatter:

#### Basic Structure

**File:** `.claude/skills/my-skill/SKILL.md`
```markdown
---
name: my-skill
description: What this skill does and when to use it
---

# My Skill Title

## Instructions

Step-by-step instructions Claude will follow when this skill is invoked.

1. Do this
2. Then do that
3. Finally, verify

## Reference Material

[Link to resource files](resources/patterns.md)
```

#### Directory Structure

```
my-skill/
├── SKILL.md              # Main instructions (required)
├── resources/
│   ├── patterns.md       # Reference material
│   └── examples.md       # Code examples
├── templates/
│   └── template.py       # Template Claude can fill in
└── scripts/
    └── helper.sh         # Scripts Claude can execute
```

### Frontmatter Reference

Complete field reference for `SKILL.md`:

| Field | Type | Purpose | Example |
|-------|------|---------|---------|
| `name` | String | Display name (becomes `/skill-name` command). Lowercase, alphanumeric, hyphens only. | `orchestration-dev` |
| `description` | String | What the skill does. Claude uses this to decide when to auto-load. | `Agent development patterns for cortex-ai orchestration` |
| `disable-model-invocation` | Boolean | Only you can invoke (not Claude). Use for side-effect operations (deploy, commit). | `true` |
| `user-invocable` | Boolean | Only Claude can invoke (not shown in `/` menu). Use for background knowledge. | `false` |
| `allowed-tools` | String | Comma-separated list of tools Claude can use without permission. | `Read, Grep, Glob` |
| `context` | String | Run in isolated subagent context. | `fork` |
| `agent` | String | Which subagent type to use with `context: fork`. | `Explore`, `Plan`, `general-purpose` |
| `paths` | Array | Glob patterns limiting when skill auto-activates. | `cortex/api/**/*.py` |
| `model` | String | Specific model to use. | `sonnet`, `opus`, `haiku` |
| `effort` | String | Effort level. | `low`, `medium`, `high`, `max` |
| `argument-hint` | String | Hint for autocomplete. | `[agent-name]` |
| `shell` | String | Shell for command blocks. | `bash` (default), `powershell` |

### Invocation Methods

#### 1. User-Invoked (Manual)

Type `/skill-name` in your Claude Code session:

```bash
# Example
/orchestration-dev

# With arguments
/migrate-component SearchBar React Vue
```

**When to use:**
- Explicit workflows (deploy, commit, create PR)
- User decision required
- Side-effect operations

**Frontmatter:**
```yaml
---
name: deploy
description: Deploy application to production
disable-model-invocation: true  # Only user can invoke
---
```

#### 2. Auto-Activation (Automatic)

Claude loads the skill when it detects relevance based on:
- Keywords in your request
- File paths you're working with
- Code content patterns

**Example:**

```python
# You ask: "How do I create a new orchestration agent?"
# Claude auto-loads: /orchestration-dev skill
# You see: Claude follows the skill's agent creation pattern
```

**Frontmatter:**
```yaml
---
name: orchestration-dev
description: Agent development patterns for cortex-ai orchestration. Auto-activates when creating or modifying agents.
# disable-model-invocation: false (default, allows auto-activation)
---
```

### Scope and Priority

Skills can live in multiple locations:

| Location | Path | Scope | Priority |
|----------|------|-------|----------|
| **Enterprise** | Managed settings | All users in organization | **Highest** |
| **Personal** | `~/.claude/skills/skill-name/SKILL.md` | All your projects | Middle |
| **Project** | `.claude/skills/skill-name/SKILL.md` | This project only | Lower |
| **Plugin** | `<plugin>/skills/skill-name/SKILL.md` | Where plugin is enabled | **Lowest** |

When skills share the same name, **higher-priority locations win**.

### Creating Custom Skills

#### Step-by-Step Guide

**Step 1: Create skill directory**

```bash
mkdir -p .claude/skills/orchestration-dev
```

**Step 2: Create SKILL.md**

**File:** `.claude/skills/orchestration-dev/SKILL.md`
```markdown
---
name: orchestration-dev
description: Agent development patterns for cortex-ai orchestration
paths:
  - "cortex/orchestration/**/*.py"
  - "tests/orchestration/**/*.py"
allowed-tools: Read, Grep, Glob
---

# Orchestration Agent Development

## When to Use This Skill

Use this skill when:
- Creating new orchestration agents
- Modifying existing Agent class
- Debugging agent execution flow
- Adding new middleware

## Agent Creation Pattern

Follow this pattern for new agents:

### 1. Define AgentConfig

```python
from cortex.orchestration import Agent, ModelConfig

config = AgentConfig(
    name="agent_name",
    description="What this agent does",
    system_prompt="You are a...",
    model=ModelConfig(model="gpt-4o", use_gateway=False),
)
```

### 2. Add Tools (Optional)

```python
from langchain_core.tools import tool

@tool
def my_tool(query: str) -> str:
    """Tool description."""
    return result
```

### 3. Initialize Agent

```python
agent = Agent(
    name="agent_name",
    system_prompt="...",
    model=ModelConfig(...),
    tools=[my_tool],
)
```

### 4. Run Agent

```python
# Single turn
result = await agent.run("User query")

# Multi-turn with thread
result = await agent.run("Query", thread_id="session-123")
```

## Best Practices

✅ **Do:**
- Use async/await for all agent operations
- Include proper error handling
- Set thread_id for multi-turn conversations
- Use context injection for secure tool calls

❌ **Don't:**
- Block on agent.run() without await
- Put sensitive data in system prompts
- Create new thread for every message (loses context)

## Reference Files

See [Agent class](../../../cortex/orchestration/agent.py) for implementation.
See [ORCHESTRATION_ARCHITECTURE.md](../../../docs/ORCHESTRATION_ARCHITECTURE.md) for design.
```

**Step 3: Test the skill**

```bash
# In Claude Code session
/orchestration-dev

# Or work on an orchestration file (auto-activates)
claude code edit cortex/orchestration/new_agent.py
```

### Skills vs Subagents

**Common confusion:** Skills and Subagents are different concepts.

| Aspect | Skills | Subagents |
|--------|--------|-----------|
| **What** | Reusable instruction bundles in SKILL.md | Background workers spawned by Claude |
| **Invocation** | `/skill-name` or auto-activation | Claude spawns via Agent tool |
| **File** | `.claude/skills/name/SKILL.md` | Defined in prompt/tool, not files |
| **Context** | Inline (default) or fork | Always separate context |
| **Use Case** | Standardized workflows, reference material | Complex multi-step investigations |
| **Parallelization** | One at a time | Claude can spawn multiple in parallel |
| **Memory** | Shares main session | Independent (unless checkpointed) |

**Simple analogy:**
- **Skills** = Command-line utilities (focused, fast, reusable)
- **Subagents** = Specialized consultants (complex thinking, isolated work, investigation)

**When to use which:**

```markdown
# ✅ Use a Skill when:
- You have a repeatable workflow (create PR, deploy, commit)
- You want reference material loaded on-demand
- Pattern is well-defined and stable

# ✅ Use a Subagent (spawned by Claude) when:
- Task requires deep codebase exploration
- Investigation needs isolation (won't clutter main context)
- Multi-step research with many file reads
```

### Cortex-AI Skill Ideas

Recommended skills for cortex-ai development:

#### 1. `/orchestration-dev` - Agent Development
**Purpose:** Patterns for creating orchestration agents
**Auto-activates:** When working with `cortex/orchestration/**/*.py`
**Provides:** Agent creation templates, best practices, common pitfalls

#### 2. `/rag-query` - RAG Implementation
**Purpose:** GraphRAG and vector store query patterns
**Auto-activates:** When working with `cortex/rag/**/*.py`
**Provides:** Query optimization, embedding strategies, retrieval patterns

#### 3. `/memory-debug` - Memory Middleware
**Purpose:** Debug memory middleware and checkpointing
**Auto-activates:** When working with `cortex/memory/**/*.py`
**Provides:** Checkpoint troubleshooting, session persistence patterns

#### 4. `/api-endpoint` - Chat API Endpoints
**Purpose:** Create new Chat API endpoints
**Auto-activates:** When working with `cortex/api/routes/**/*.py`
**Provides:** FastAPI patterns, SSE streaming, error handling

#### 5. `/test-orchestration` - Orchestration Tests
**Purpose:** Write tests for orchestration agents
**Auto-activates:** When working with `tests/orchestration/**/*.py`
**Provides:** Test patterns, mocking strategies, async test helpers

---

## Practical Setup for Cortex-AI

### Recommended Structure

```
cortex-ai/
├── .claude/
│   ├── CLAUDE.md           # Main project instructions
│   ├── rules/
│   │   ├── orchestration.md  # Agent development rules
│   │   ├── api.md            # API endpoint conventions
│   │   ├── rag.md            # RAG implementation rules
│   │   ├── memory.md         # Memory middleware patterns
│   │   └── testing.md        # Testing requirements
│   └── skills/
│       ├── orchestration-dev/
│       │   └── SKILL.md
│       ├── rag-query/
│       │   └── SKILL.md
│       └── api-endpoint/
│           └── SKILL.md
├── CLAUDE.md  (symlink to .claude/CLAUDE.md)
└── ...
```

### Example: Main CLAUDE.md

**File:** `.claude/CLAUDE.md`
```markdown
# Cortex-AI Development Guide

**Production AI orchestration platform**

@../README.md
@../CONTRIBUTING.md

---

## Quick Commands

```bash
# Run tests
pytest tests/

# Start API server
uvicorn cortex.api.app:app --reload

# Type check
mypy cortex/
```

## Project Structure

```
cortex/
├── orchestration/  # Multi-agent orchestration (Agent, ModelConfig)
├── api/            # FastAPI Chat API
├── rag/            # GraphRAG and vector stores
├── memory/         # Memory middleware and checkpointing
├── tools/          # MCP integration
└── platform/       # Platform features
```

## Development Rules

See `.claude/rules/` for detailed guidelines:
- `orchestration.md` - Agent development patterns
- `api.md` - API endpoint conventions
- `rag.md` - RAG query optimization
- `testing.md` - Test requirements

## Key Patterns

### Agent Creation
```python
from cortex.orchestration import Agent, ModelConfig

agent = Agent(
    name="assistant",
    system_prompt="You are...",
    model=ModelConfig(model="gpt-4o", use_gateway=False),
)

result = await agent.run("Query", thread_id="session-id")
```

### Context Injection (Security)
```python
# ✅ Good: Server-side context injection
registry = ToolRegistry()
registry.set_context(user_id=request.user_id)  # LLM never sees this
agent = Agent(tool_registry=registry, ...)

# ❌ Bad: LLM controls user_id
# Never put user_id in prompt!
```

### Error Handling
```python
try:
    result = await agent.run(query)
except Exception as e:
    logger.error(f"Agent error: {e}", exc_info=True)
    # Handle gracefully
```

## Skills

Available skills:
- `/orchestration-dev` - Agent development patterns
- `/rag-query` - RAG query optimization
- `/api-endpoint` - Create Chat API endpoints

## Links

- [Architecture](docs/ORCHESTRATION_ARCHITECTURE.md)
- [Quick Start](docs/QUICK_START.md)
- [Memory Strategy](docs/MEMORY_STRATEGY.md)
```

### Example: Path-Specific Rule

**File:** `.claude/rules/orchestration.md`
```markdown
---
paths:
  - "cortex/orchestration/**/*.py"
  - "tests/orchestration/**/*.py"
---

# Orchestration Development Rules

## Agent Initialization

**Pattern:**
```python
agent = Agent(
    name="agent_name",
    description="Purpose of this agent",
    system_prompt="Detailed instructions...",
    model=ModelConfig(model="gpt-4o", temperature=0.7),
    tools=[tool1, tool2],  # Or None for all from registry
    tool_registry=registry,  # Pre-configured with context
    max_iterations=25,
)
```

## Async/Await Requirements

✅ **All agent operations must be async:**
```python
# ✅ Correct
result = await agent.run(query)

# ❌ Wrong
result = agent.run(query)  # Missing await
```

## Thread Management

✅ **Use thread_id for multi-turn:**
```python
# Conversation state persists
thread_id = f"{user_id}-{session_id}"
result = await agent.run(message, thread_id=thread_id)
```

❌ **Don't lose context:**
```python
# New thread every time (loses context)
result = await agent.run(message)
```

## Error Handling

**All agent calls must have try/except:**
```python
try:
    result = await agent.run(query)
except Exception as e:
    logger.error(f"Agent execution failed: {e}", exc_info=True)
    # Return user-friendly error
    raise HTTPException(status_code=500, detail="Agent error")
```

## Testing

**Use pytest-asyncio for agent tests:**
```python
import pytest
from cortex.orchestration import Agent, ModelConfig

@pytest.mark.asyncio
async def test_agent_execution():
    agent = Agent(
        name="test_agent",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
    )

    result = await agent.run("Test query")

    assert result.response is not None
    assert "gpt-4o" in result.token_usage
```

## Performance

**Monitor token usage:**
```python
result = await agent.run(query)

logger.info(
    "Agent completed",
    extra={
        "agent": agent.name,
        "tokens": result.token_usage,
        "duration_ms": result.duration_ms,
    }
)
```
```

### Example: Skill for Cortex-AI

**File:** `.claude/skills/orchestration-dev/SKILL.md`
```markdown
---
name: orchestration-dev
description: Agent development patterns for cortex-ai orchestration. Auto-activates when creating or modifying agents.
paths:
  - "cortex/orchestration/**/*.py"
  - "tests/orchestration/**/*.py"
allowed-tools: Read, Grep, Glob, Edit
model: sonnet
effort: medium
---

# Orchestration Agent Development

## Purpose

This skill provides patterns and best practices for developing orchestration agents in cortex-ai.

## When to Use This Skill

Auto-activates when:
- Creating new Agent classes
- Modifying existing agents
- Adding tools to agents
- Debugging agent execution

## Agent Creation Workflow

### 1. Define Your Agent

```python
from cortex.orchestration import Agent, ModelConfig

agent = Agent(
    name="my_agent",
    description="What this agent does",
    system_prompt="""
You are a helpful assistant specialized in [domain].

Your responsibilities:
- [Responsibility 1]
- [Responsibility 2]

Guidelines:
- [Guideline 1]
- [Guideline 2]
    """,
    model=ModelConfig(
        model="gpt-4o",  # or claude-sonnet-4, gemini-2.0-flash
        temperature=0.7,
        use_gateway=False,  # or True for tracking
    ),
)
```

### 2. Add Tools (If Needed)

```python
from langchain_core.tools import tool
from pydantic import Field

@tool
def search_database(
    query: str = Field(..., description="Search query"),
) -> str:
    """Search the knowledge base."""
    # Implementation
    return results
```

### 3. Configure Context Injection (Security)

```python
from cortex.orchestration import ToolRegistry

# Setup registry with secure context
registry = ToolRegistry()
registry.register(search_database)
registry.set_context(user_id="user123")  # LLM never sees this

agent = Agent(
    name="assistant",
    tool_registry=registry,
    tools=None,  # Use all from registry
)
```

### 4. Execute Agent

```python
# Single turn
result = await agent.run("What is the weather?")

# Multi-turn conversation
thread_id = f"{user_id}-{session_id}"
result = await agent.run("Follow-up question", thread_id=thread_id)
```

### 5. Handle Streaming (Optional)

```python
from cortex.orchestration import SimpleStreamWriter

writer = SimpleStreamWriter()

result = await agent.stream_to_writer(
    "Tell me a story",
    stream_writer=writer,
)
```

## Best Practices

### ✅ Do

- Use async/await for all agent operations
- Set thread_id for multi-turn conversations
- Use ToolRegistry.set_context() for sensitive data
- Include proper error handling
- Monitor token usage for cost optimization
- Add type hints to all functions

### ❌ Don't

- Block on agent.run() without await
- Put user_id or sensitive data in system prompts
- Create new thread for every message (loses context)
- Ignore error handling
- Skip token usage logging

## Common Patterns

### Pattern 1: Request/Response Agent

```python
async def handle_request(request: ChatRequest) -> ChatResponse:
    agent = Agent(
        name="assistant",
        model=ModelConfig(model="gpt-4o"),
    )

    try:
        result = await agent.run(
            request.message,
            thread_id=request.session_id,
        )

        return ChatResponse(
            message=result.response,
            tokens=result.token_usage,
        )
    except Exception as e:
        logger.error(f"Agent failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Agent error")
```

### Pattern 2: Tool-Enabled Agent

```python
@tool
def calculator(operation: str, a: float, b: float) -> str:
    """Perform math operations."""
    ops = {"add": lambda x, y: x + y, "multiply": lambda x, y: x * y}
    return str(ops[operation](a, b))

agent = Agent(
    name="math_assistant",
    system_prompt="Use the calculator tool for math.",
    tools=[calculator],
)

result = await agent.run("What is 15 times 7?")
# Agent will use calculator tool
```

### Pattern 3: Context-Aware Agent

```python
@tool
def get_user_preferences(
    user_id: str = Field(..., description="User ID"),
    setting: str = Field(..., description="Setting name"),
) -> str:
    """Get user preferences."""
    # user_id injected by registry, not controlled by LLM
    return f"User {user_id} prefers {setting}"

registry = ToolRegistry()
registry.register(get_user_preferences)
registry.set_context(user_id=current_user.id)

agent = Agent(tool_registry=registry, tools=None)
result = await agent.run("What are my preferences?")
```

## Testing

### Unit Test Example

```python
import pytest
from cortex.orchestration import Agent, ModelConfig

@pytest.mark.asyncio
async def test_agent_basic_execution():
    agent = Agent(
        name="test_agent",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
    )

    result = await agent.run("Say hello")

    assert result.response is not None
    assert len(result.messages) > 0
    assert "gpt-4o" in result.token_usage

@pytest.mark.asyncio
async def test_agent_with_tools():
    @tool
    def test_tool(query: str) -> str:
        """Test tool."""
        return f"Result: {query}"

    agent = Agent(
        name="tool_agent",
        tools=[test_tool],
    )

    result = await agent.run("Use the test tool with 'hello'")

    assert "Result: hello" in result.response
```

## Reference Files

- [Agent Implementation](../../../cortex/orchestration/agent.py)
- [ModelConfig](../../../cortex/orchestration/config.py)
- [ToolRegistry](../../../cortex/orchestration/tools/registry.py)
- [Architecture Docs](../../../docs/ORCHESTRATION_ARCHITECTURE.md)
- [Quick Start](../../../docs/QUICK_START.md)

## Troubleshooting

**Q: Agent not calling tools?**
A: Check tool docstrings are descriptive. LLM uses docstrings to decide when to call.

**Q: Token usage very high?**
A: Monitor system_prompt length. Use concise prompts. Enable prompt caching.

**Q: Conversation losing context?**
A: Ensure thread_id is consistent across turns. Check checkpointer configuration.

**Q: Async errors?**
A: All agent methods are async. Always use `await agent.run()`.
```

---

## Best Practices

### CLAUDE.md Best Practices

#### ✅ Do

**Keep under 200 lines per file:**
```markdown
# ✅ Good - Concise main file
# Cortex-AI Guide

@README.md
@CONTRIBUTING.md

See `.claude/rules/` for detailed guidelines.

## Quick Commands
- Test: `pytest tests/`
- Run: `uvicorn app:app --reload`
```

**Use `@imports` to pull in existing docs:**
```markdown
# ✅ Good - No duplication
@README.md  <!-- Project overview -->
@docs/ARCHITECTURE.md  <!-- Technical details -->
```

**Be specific and concrete:**
```markdown
# ✅ Good - Actionable
- API routes in `cortex/api/routes/`
- Use `ModelConfig(model="gpt-4o")` for default
- All async functions need error handling
```

**Organize with `.claude/rules/` for large projects:**
```
.claude/
├── CLAUDE.md           # Main entry (< 100 lines)
└── rules/
    ├── api.md          # paths: cortex/api/**/*.py
    ├── orchestration.md  # paths: cortex/orchestration/**/*.py
    └── testing.md      # paths: tests/**/*.py
```

#### ❌ Don't

**Don't create massive monolithic files:**
```markdown
# ❌ Bad - 500+ lines in one file
# This will reduce adherence and waste tokens
```

**Don't duplicate content from code/docs:**
```markdown
# ❌ Bad - Duplicates README
## Project Structure
cortex/ contains...
api/ contains...
orchestration/ contains...

# ✅ Good - Reference existing docs
@README.md  <!-- Already explains structure -->
```

**Don't be vague:**
```markdown
# ❌ Bad - Unclear
- Keep code organized
- Use good patterns
- Handle errors

# ✅ Good - Specific
- API routes in cortex/api/routes/
- Use async/await for agent calls
- Wrap agent.run() in try/except
```

### Skills Best Practices

#### ✅ Do

**Use `disable-model-invocation: true` for destructive operations:**
```yaml
---
name: deploy
description: Deploy to production
disable-model-invocation: true  # Only user can invoke
---
```

**Use `context: fork` for complex multi-step tasks:**
```yaml
---
name: codebase-audit
description: Audit entire codebase for security issues
context: fork  # Runs in isolated subagent
agent: Explore
---
```

**Use path-specific activation:**
```yaml
---
name: api-endpoint
description: API endpoint development patterns
paths:
  - "cortex/api/**/*.py"
  - "tests/api/**/*.py"
---
```

**Provide clear examples in skill content:**
```markdown
# ✅ Good skill content

## Pattern

```python
# Code example here
```

## When to Use
- Scenario 1
- Scenario 2
```

#### ❌ Don't

**Don't create skills for one-off tasks:**
```markdown
# ❌ Bad - Too specific
---
name: fix-bug-123
description: Fix specific bug in ticket 123
---
```

**Don't forget to set allowed-tools:**
```yaml
# ❌ Bad - No tools specified
---
name: orchestration-dev
---

# ✅ Good - Tools specified
---
name: orchestration-dev
allowed-tools: Read, Grep, Glob, Edit
---
```

**Don't make description too broad:**
```yaml
# ❌ Bad - Will activate too often
description: General development help

# ✅ Good - Specific activation criteria
description: Agent development patterns for cortex-ai orchestration. Auto-activates when creating or modifying agents.
```

### Common Patterns

#### Pattern 1: Context Injection (Security)

**Problem:** Tool needs user_id but LLM shouldn't control it.

**Solution:** Use ToolRegistry.set_context()

```python
# ✅ Good: Server-side injection
@tool
def get_user_data(
    user_id: str = Field(..., description="User ID"),
    query: str = Field(..., description="What to fetch"),
) -> str:
    """Get user data."""
    # user_id is injected, not from LLM
    return f"Data for {user_id}: {query}"

registry = ToolRegistry()
registry.register(get_user_data)
registry.set_context(user_id=current_user.id)  # Injected automatically

agent = Agent(tool_registry=registry, tools=None)
# LLM schema only shows: get_user_data(query: str)
# Runtime calls: get_user_data(user_id="user123", query="...")
```

```python
# ❌ Bad: LLM controls user_id
system_prompt = f"You are helping user {user_id}"  # Don't do this!
```

#### Pattern 2: Path-Specific Rules

**Problem:** Different rules for API vs orchestration code.

**Solution:** Use `.claude/rules/` with frontmatter paths.

**File:** `.claude/rules/api.md`
```markdown
---
paths:
  - "cortex/api/**/*.py"
---

# API Development Rules
- All endpoints use FastAPI dependency injection
- Include OpenAPI docs with examples
```

**File:** `.claude/rules/orchestration.md`
```markdown
---
paths:
  - "cortex/orchestration/**/*.py"
---

# Orchestration Rules
- All agent operations are async
- Use thread_id for multi-turn conversations
```

#### Pattern 3: Dynamic Skill Content

**Problem:** Skill needs current git status or file list.

**Solution:** Use `` !`command` `` syntax to inject shell output.

```markdown
---
name: pr-summary
description: Summarize PR changes
---

# PR Summary

## Changed Files
!`git diff --name-only main...HEAD`

## Diff
!`git diff main...HEAD`

## Your Task
Summarize the changes in this PR.
```

**How it works:** The `` !`command` `` runs before sending to Claude—output replaces the placeholder.

---

## Examples

### Example 1: Complete CLAUDE.md for Cortex-AI

**File:** `.claude/CLAUDE.md`
```markdown
# Cortex-AI Development Guide

**Production AI orchestration platform with multi-agent support**

@../README.md
@../CONTRIBUTING.md

---

## Project Overview

Cortex-AI provides:
- Multi-agent orchestration (LangGraph-based)
- GraphRAG knowledge retrieval
- Chat API with SSE streaming
- Memory middleware and persistence
- MCP tool integration

## Quick Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ -v

# Type check
mypy cortex/

# Start API server
uvicorn cortex.api.app:app --reload --port 8000

# Run examples
python examples/orchestration_demo.py
```

## Project Structure

```
cortex/
├── orchestration/  # Agent, ModelConfig, LangGraph integration
├── api/            # FastAPI Chat API with SSE
├── rag/            # GraphRAG, vector stores, embeddings
├── memory/         # Memory middleware, checkpointing
├── tools/          # MCP integration and tool registry
├── platform/       # Platform features
└── skills/         # Global skills (future)
```

## Development Guidelines

### Rules Organization

See `.claude/rules/` for detailed guidelines:
- `orchestration.md` - Agent development patterns (async/await, tools, context injection)
- `api.md` - API endpoint conventions (FastAPI, SSE, error handling)
- `rag.md` - RAG query optimization (GraphRAG, embeddings, retrieval)
- `memory.md` - Memory middleware patterns (checkpointing, session persistence)
- `testing.md` - Test requirements (pytest-asyncio, mocking, coverage)

### Tech Stack

- **Python:** 3.11+ (specified in pyproject.toml)
- **Framework:** FastAPI for API, LangGraph for orchestration
- **LLMs:** Multi-provider (OpenAI, Anthropic, Google, Vertex AI)
- **Database:** PostgreSQL for persistence, Neo4j for GraphRAG
- **Vector Store:** Chroma, Pinecone, or custom
- **Async:** All agent operations use async/await

### Code Style

- Use type hints for all function signatures
- Follow PEP 8 (enforced by ruff)
- Docstrings for all public functions (Google style)
- Async/await for I/O operations

## Key Patterns

### 1. Agent Creation

```python
from cortex.orchestration import Agent, ModelConfig

agent = Agent(
    name="assistant",
    description="General purpose assistant",
    system_prompt="You are a helpful assistant specialized in...",
    model=ModelConfig(model="gpt-4o", temperature=0.7),
    tools=[tool1, tool2],  # Optional
)

result = await agent.run("Query", thread_id="session-id")
```

### 2. Secure Context Injection

```python
from cortex.orchestration import ToolRegistry

# ✅ Good: Server-side context
registry = ToolRegistry()
registry.set_context(user_id=request.user_id)  # LLM never sees this
agent = Agent(tool_registry=registry, tools=None)

# ❌ Bad: LLM controls user_id
# Never: system_prompt = f"User ID is {user_id}"
```

### 3. Error Handling

```python
try:
    result = await agent.run(query)
except Exception as e:
    logger.error(f"Agent error: {e}", exc_info=True)
    raise HTTPException(status_code=500, detail="Agent execution failed")
```

### 4. Streaming (SSE)

```python
from cortex.orchestration import SimpleStreamWriter

writer = SimpleStreamWriter()
result = await agent.stream_to_writer(query, stream_writer=writer)
```

## Testing

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/orchestration/test_agent.py

# Run with coverage
pytest --cov=cortex --cov-report=html tests/

# Run async tests
pytest tests/ -v -k "asyncio"
```

## Environment Setup

```bash
# Required environment variables
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GOOGLE_API_KEY="..."  # Optional

# Database (for GraphRAG)
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="password"

# PostgreSQL (for checkpointing)
export DATABASE_URL="postgresql://user:pass@localhost/cortex"
```

## Skills

Available skills (in `.claude/skills/`):
- `/orchestration-dev` - Agent development patterns
- `/rag-query` - GraphRAG query optimization
- `/api-endpoint` - Create Chat API endpoints
- `/memory-debug` - Debug memory middleware

## Links

- [Quick Start](docs/QUICK_START.md)
- [Architecture](docs/ORCHESTRATION_ARCHITECTURE.md)
- [Memory Strategy](docs/MEMORY_STRATEGY.md)
- [GraphRAG](docs/GRAPHRAG.md)
- [Chat API](docs/CHAT_API.md)

## DON'Ts

- ❌ Never block on agent.run() without await
- ❌ Never put user_id in system prompts
- ❌ Never create new thread_id for every message
- ❌ Never skip error handling on agent calls
- ❌ Never ignore token usage (monitor costs)
```

### Example 2: Skill for RAG Query Debugging

**File:** `.claude/skills/rag-query/SKILL.md`
```markdown
---
name: rag-query
description: GraphRAG and vector store query optimization. Auto-activates when working with RAG implementation.
paths:
  - "cortex/rag/**/*.py"
  - "tests/rag/**/*.py"
allowed-tools: Read, Grep, Glob, Edit
model: sonnet
effort: medium
---

# RAG Query Optimization

## Purpose

Optimize GraphRAG queries, debug retrieval issues, and improve relevance scoring.

## When to Use This Skill

Auto-activates when:
- Writing GraphRAG queries
- Debugging retrieval quality
- Optimizing embedding strategies
- Troubleshooting knowledge graph queries

## Query Optimization Workflow

### 1. Understand Query Types

**Vector Search (Similarity):**
```python
from cortex.rag import VectorStore

results = await vector_store.similarity_search(
    query="User question",
    k=5,  # Top 5 results
    filter={"source": "documentation"},
)
```

**Graph Traversal (GraphRAG):**
```python
from cortex.rag import GraphRAG

results = await graph_rag.query(
    query="User question",
    depth=2,  # Traversal depth
    include_relationships=True,
)
```

**Hybrid (Vector + Graph):**
```python
results = await graph_rag.hybrid_search(
    query="User question",
    vector_weight=0.7,
    graph_weight=0.3,
)
```

### 2. Debug Poor Retrieval

**Check embedding quality:**
```python
# Test embedding similarity
embedding1 = await embedder.embed("query text")
embedding2 = await embedder.embed("document text")

similarity = cosine_similarity(embedding1, embedding2)
print(f"Similarity: {similarity}")  # Should be > 0.7 for relevant docs
```

**Inspect retrieved chunks:**
```python
results = await vector_store.similarity_search(query, k=10)

for i, doc in enumerate(results):
    print(f"{i}. Score: {doc.score:.3f}")
    print(f"   Content: {doc.content[:100]}...")
    print(f"   Metadata: {doc.metadata}")
```

### 3. Optimize Chunk Size

**Problem:** Chunks too large or too small affect retrieval.

**Solution:** Experiment with chunk size and overlap.

```python
# ✅ Good - Balanced chunks
chunker = TextChunker(
    chunk_size=512,  # Tokens per chunk
    chunk_overlap=50,  # Overlap for context
)

# ❌ Bad - Too large (loses precision)
chunker = TextChunker(chunk_size=2048, chunk_overlap=0)

# ❌ Bad - Too small (loses context)
chunker = TextChunker(chunk_size=128, chunk_overlap=0)
```

### 4. Improve Graph Structure

**For GraphRAG:**

```python
# ✅ Good - Rich relationships
graph.add_entity(
    id="entity_id",
    type="Person",
    properties={"name": "John", "role": "Engineer"},
)

graph.add_relationship(
    source="entity_1",
    target="entity_2",
    type="WORKS_WITH",
    properties={"since": "2020"},
)

# ❌ Bad - Flat structure
# Just vector embeddings without relationships
```

## Best Practices

### ✅ Do

- Use hybrid search (vector + graph) for best results
- Monitor retrieval latency (should be < 200ms)
- Log query performance metrics
- Implement caching for frequent queries
- Use filters to scope search (metadata, date, source)

### ❌ Don't

- Embed entire documents (chunk them first)
- Ignore embedding model choice (affects quality)
- Skip relevance scoring (monitor precision/recall)
- Hardcode chunk size (make it configurable)

## Common Issues

### Issue 1: Low Retrieval Relevance

**Symptoms:** Retrieved chunks not relevant to query.

**Debug:**
1. Check embedding model (try different models)
2. Inspect chunk quality (are they coherent?)
3. Adjust k (try more results, then re-rank)
4. Add metadata filters

**Solution:**
```python
# Try re-ranking
from cortex.rag import Reranker

reranker = Reranker(model="cross-encoder/ms-marco-MiniLM-L-12-v2")

# Get more candidates
candidates = await vector_store.similarity_search(query, k=20)

# Re-rank for precision
reranked = await reranker.rerank(query, candidates, top_k=5)
```

### Issue 2: Slow Queries

**Symptoms:** Queries take > 1 second.

**Debug:**
1. Check vector store index (is it built?)
2. Monitor embedding generation time
3. Profile graph traversal depth

**Solution:**
```python
# ✅ Good - Caching and batching
@lru_cache(maxsize=1000)
async def get_embeddings(text: str):
    return await embedder.embed(text)

# Batch queries
results = await vector_store.batch_search(queries, k=5)
```

### Issue 3: Missing Context

**Symptoms:** Chunks lack surrounding context.

**Solution:**
```python
# ✅ Good - Chunk with overlap
chunker = TextChunker(
    chunk_size=512,
    chunk_overlap=100,  # Include surrounding context
)

# ✅ Good - Retrieve parent chunks
results = await vector_store.similarity_search(query, k=5)

for doc in results:
    # Fetch parent document for context
    parent = await doc_store.get(doc.metadata["parent_id"])
```

## Performance Metrics

**Monitor these:**

```python
metrics = {
    "query_latency_ms": time_elapsed,
    "num_candidates": len(candidates),
    "num_results": len(filtered_results),
    "avg_relevance_score": avg_score,
    "embedding_cache_hit_rate": cache_hits / total_queries,
}

logger.info("RAG query completed", extra=metrics)
```

## Reference Files

- [GraphRAG Implementation](../../../cortex/rag/graphrag.py)
- [Vector Store](../../../cortex/rag/vector_store.py)
- [Embeddings](../../../cortex/rag/embeddings.py)
- [GraphRAG Docs](../../../docs/GRAPHRAG.md)
- [RAG Architecture](../../../docs/RAG.md)

## Testing

```python
import pytest
from cortex.rag import VectorStore, GraphRAG

@pytest.mark.asyncio
async def test_vector_search_relevance():
    vector_store = VectorStore(...)

    results = await vector_store.similarity_search(
        query="How do I create an agent?",
        k=5,
    )

    assert len(results) == 5
    assert all(r.score > 0.5 for r in results)
    assert "agent" in results[0].content.lower()
```
```

### Example 3: Path-Specific API Rules

**File:** `.claude/rules/api.md`
```markdown
---
paths:
  - "cortex/api/**/*.py"
  - "tests/api/**/*.py"
---

# API Development Rules

## Endpoint Structure

**All API routes in `cortex/api/routes/`:**

```python
from fastapi import APIRouter, HTTPException, Depends
from cortex.api.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/api/v1", tags=["chat"])

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    """Chat endpoint with streaming support."""
    try:
        # Implementation
        return ChatResponse(...)
    except Exception as e:
        logger.error(f"Chat failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Chat error")
```

## Input Validation

**Use Pydantic models:**

```python
from pydantic import BaseModel, Field, validator

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    session_id: str = Field(..., regex="^[a-zA-Z0-9-]+$")
    model: str = Field(default="gpt-4o")

    @validator("message")
    def message_not_empty(cls, v):
        if not v.strip():
            raise ValueError("Message cannot be empty")
        return v
```

## Error Handling

**Standard error format:**

```python
# ✅ Good - Consistent format
{
    "error": "validation_error",
    "message": "Invalid session_id format",
    "details": {"field": "session_id", "issue": "Invalid characters"}
}

# ❌ Bad - Inconsistent
{
    "msg": "Error occurred",
    "status": "failed"
}
```

**Error handler:**

```python
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)

    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": "An internal error occurred",
            "details": {},
        }
    )
```

## SSE Streaming

**Pattern for streaming responses:**

```python
from fastapi import StreamingResponse
from cortex.api.streaming import SSEWriter

@router.post("/chat/stream")
async def chat_stream_endpoint(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    async def generate():
        writer = SSEWriter()

        try:
            await agent.stream_to_writer(
                request.message,
                stream_writer=writer,
                thread_id=request.session_id,
            )
        except Exception as e:
            yield writer.format_error(str(e))
        finally:
            await writer.close()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
    )
```

## Authentication

**Use FastAPI dependency injection:**

```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer

security = HTTPBearer()

async def get_current_user(
    token: str = Depends(security),
) -> User:
    try:
        user = await auth.verify_token(token.credentials)
        return user
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

@router.post("/chat")
async def chat(
    request: ChatRequest,
    user: User = Depends(get_current_user),  # Auto-validates
):
    # user is authenticated
    pass
```

## Testing

**All endpoints must have integration tests:**

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_chat_endpoint(client: AsyncClient):
    response = await client.post(
        "/api/v1/chat",
        json={
            "message": "Hello",
            "session_id": "test-session",
        },
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert data["session_id"] == "test-session"
```

## Performance

**Monitor endpoint latency:**

```python
import time
from starlette.middleware.base import BaseHTTPMiddleware

class LatencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = time.time()
        response = await call_next(request)
        duration = (time.time() - start) * 1000

        logger.info(
            "Request completed",
            extra={
                "path": request.url.path,
                "method": request.method,
                "status": response.status_code,
                "duration_ms": duration,
            }
        )

        return response
```

## OpenAPI Documentation

**All endpoints must include:**
- Summary and description
- Request/response examples
- Error responses

```python
@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Send chat message",
    description="Send a message to the AI assistant and receive a response.",
    responses={
        200: {
            "description": "Successful response",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Hello! How can I help?",
                        "session_id": "abc-123",
                    }
                }
            }
        },
        400: {"description": "Invalid request"},
        401: {"description": "Unauthorized"},
        500: {"description": "Internal server error"},
    },
)
async def chat_endpoint(...):
    pass
```
```

### Example 4: Testing Rules

**File:** `.claude/rules/testing.md`
```markdown
---
paths:
  - "tests/**/*.py"
---

# Testing Requirements

## Test Structure

```
tests/
├── orchestration/       # Agent tests
├── api/                 # API endpoint tests
├── rag/                 # RAG retrieval tests
├── memory/              # Memory middleware tests
└── conftest.py          # Shared fixtures
```

## Async Testing

**Use pytest-asyncio:**

```python
import pytest

@pytest.mark.asyncio
async def test_agent_execution():
    agent = Agent(name="test")
    result = await agent.run("Test")
    assert result.response is not None
```

## Fixtures

**Share common setup in conftest.py:**

```python
# tests/conftest.py
import pytest
from cortex.orchestration import Agent, ModelConfig

@pytest.fixture
async def test_agent():
    """Reusable test agent."""
    return Agent(
        name="test_agent",
        model=ModelConfig(model="gpt-4o", use_gateway=False),
    )

@pytest.fixture
def mock_tool():
    """Mock tool for testing."""
    @tool
    def test_tool(query: str) -> str:
        return f"Mock result: {query}"
    return test_tool
```

## Mocking

**Mock external services:**

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_agent_with_mocked_llm():
    with patch("cortex.orchestration.agent.LLMProvider") as mock_llm:
        mock_llm.return_value.generate = AsyncMock(
            return_value="Mocked response"
        )

        agent = Agent(name="test")
        result = await agent.run("Test")

        assert result.response == "Mocked response"
        mock_llm.return_value.generate.assert_called_once()
```

## Coverage

**Aim for 80% coverage:**

```bash
pytest --cov=cortex --cov-report=html --cov-report=term tests/

# View HTML report
open htmlcov/index.html
```

## Test Categories

### Unit Tests
- Test individual functions in isolation
- Mock all external dependencies
- Fast execution (< 100ms each)

### Integration Tests
- Test component interactions
- Use real dependencies where possible
- Reasonable execution time (< 5s each)

### End-to-End Tests
- Test full workflows
- Minimal mocking
- Longer execution (< 30s each)

## Best Practices

### ✅ Do

- Use descriptive test names: `test_agent_handles_empty_message`
- One assertion per test (or related assertions)
- Use fixtures for shared setup
- Clean up resources in teardown
- Test both success and error cases

### ❌ Don't

- Share state between tests
- Use hardcoded values (use fixtures/factories)
- Skip error case testing
- Ignore flaky tests (fix them)
- Test implementation details (test behavior)
```

---

## Troubleshooting

### CLAUDE.md Issues

#### Q: Why aren't my rules being followed?

**Possible causes:**

1. **File not in correct location**
   ```bash
   # Check Claude is finding your file
   ls -la .claude/CLAUDE.md
   ls -la CLAUDE.md
   ```

2. **Rules too long (> 200 lines)**
   - Solution: Split into `.claude/rules/` directory

3. **Rules too vague**
   ```markdown
   # ❌ Bad - Vague
   - Write good code

   # ✅ Good - Specific
   - All async functions must include try/except error handling
   ```

4. **Path-specific rules not matching**
   ```markdown
   # Check frontmatter paths
   ---
   paths:
     - "cortex/api/**/*.py"  # Make sure this matches your files
   ---
   ```

#### Q: How do I know which CLAUDE.md is being loaded?

**Answer:** Claude loads all CLAUDE.md files found while walking up the directory tree.

```
/Users/dev/.claude/CLAUDE.md          # Always loaded (personal)
/Users/dev/cortex-ai/CLAUDE.md        # Loaded when working in cortex-ai
/Users/dev/cortex-ai/cortex/api/CLAUDE.md  # Loaded when working with API code
```

**Priority:** More specific paths override broader ones.

#### Q: Can I see what Claude loaded?

**Answer:** Not directly, but you can test by asking Claude:

```
User: "What are the testing requirements for this project?"
Claude: [Should mention rules from testing.md if loaded]
```

### Skills Issues

#### Q: Skill isn't activating automatically

**Debug checklist:**

1. **Check description is specific enough:**
   ```yaml
   # ❌ Bad - Too generic
   description: General help

   # ✅ Good - Specific
   description: Agent development patterns for cortex-ai orchestration. Auto-activates when creating or modifying agents.
   ```

2. **Check paths match your files:**
   ```yaml
   paths:
     - "cortex/orchestration/**/*.py"  # Does this match the file you're editing?
   ```

3. **Check skill directory structure:**
   ```bash
   ls -la .claude/skills/orchestration-dev/
   # Should see: SKILL.md
   ```

4. **Verify `disable-model-invocation` is NOT true:**
   ```yaml
   # ❌ This prevents auto-activation
   disable-model-invocation: true

   # ✅ Allow auto-activation (default)
   # disable-model-invocation: false (or omit)
   ```

#### Q: Skill activates too often

**Solution:** Make activation criteria more specific.

```yaml
# ❌ Activates for all Python files
paths:
  - "**/*.py"

# ✅ Only for orchestration
paths:
  - "cortex/orchestration/**/*.py"
  - "tests/orchestration/**/*.py"
```

```yaml
# ❌ Generic description
description: Help with coding

# ✅ Specific description
description: GraphRAG query optimization. Auto-activates when working with RAG retrieval code.
```

#### Q: Can't see skill in `/` menu

**Possible causes:**

1. **Skill has `user-invocable: false`**
   ```yaml
   # ❌ Hidden from menu
   user-invocable: false

   # ✅ Visible in menu (default)
   # user-invocable: true (or omit)
   ```

2. **Skill name has invalid characters**
   ```yaml
   # ❌ Invalid
   name: orchestration_dev  # Underscores not allowed

   # ✅ Valid
   name: orchestration-dev  # Hyphens OK
   ```

3. **SKILL.md file missing**
   ```bash
   # Check file exists
   ls .claude/skills/my-skill/SKILL.md
   ```

### Debugging Commands

**Check skill exists:**
```bash
ls -la .claude/skills/
```

**Validate YAML frontmatter:**
```bash
# Extract frontmatter and validate
head -n 10 .claude/skills/orchestration-dev/SKILL.md
```

**Test skill manually:**
```
# In Claude Code session
/orchestration-dev
```

---

## Advanced Topics

### Skill Auto-Activation

Skills auto-activate based on pattern matching:

#### 1. Keyword Matching

Claude checks your message for keywords:

```yaml
# In skill-rules.json (advanced configuration)
{
  "orchestration-dev": {
    "promptTriggers": {
      "keywords": ["agent", "orchestration", "langraph", "tools"]
    }
  }
}
```

**How it works:**
- User: "How do I create an agent?"
- Claude detects "agent" keyword → loads `/orchestration-dev` skill

#### 2. Path Pattern Matching

Skills activate when working with matching files:

```yaml
# In SKILL.md frontmatter
---
paths:
  - "cortex/api/**/*.py"
  - "tests/api/**/*.py"
---
```

**How it works:**
- You edit `cortex/api/routes/chat.py`
- Claude loads skill automatically

#### 3. Content Pattern Matching

**Advanced:** Match code content patterns (requires skill-rules.json):

```json
{
  "orchestration-dev": {
    "fileTriggers": {
      "contentPatterns": [
        "from cortex\\.orchestration import",
        "Agent\\(",
        "ModelConfig\\("
      ]
    }
  }
}
```

**How it works:**
- File contains `from cortex.orchestration import Agent`
- Claude loads skill automatically

### Managed Policies

**Enterprise-wide CLAUDE.md** for organization standards.

#### Setup (macOS)

```bash
# Requires admin privileges
sudo mkdir -p "/Library/Application Support/ClaudeCode"
sudo vim "/Library/Application Support/ClaudeCode/CLAUDE.md"
```

#### Example Managed Policy

```markdown
# Organization Coding Standards

## Security Requirements

- All API endpoints must validate authentication
- Never log sensitive data (passwords, tokens, PII)
- Use parameterized queries (prevent SQL injection)

## Code Quality

- Python 3.11+ required
- Type hints mandatory for all functions
- 80% test coverage minimum

## Git Workflow

- Branch naming: `feature/TICKET-123-description`
- Commit format: `type(scope): description`
- All PRs require 2 approvals
```

**Effect:** All users get these rules automatically, highest priority.

### Skill Inheritance

How project skills override personal skills:

```
~/.claude/skills/deploy/SKILL.md           # Personal skill (all projects)
/project/.claude/skills/deploy/SKILL.md    # Project skill (cortex-ai only)
```

**Priority:** Project skill wins (overrides personal).

**Use case:**
- Personal skill: Generic deploy pattern
- Project skill: Cortex-ai specific deploy (include DB migrations, cache warming)

### Dynamic Context in Skills

Use `` !`command` `` syntax to inject shell command output:

```markdown
---
name: pr-context
description: Load PR context for review
---

# PR Review Context

## Changed Files
!`git diff --name-only main...HEAD`

## Recent Commits
!`git log --oneline main...HEAD`

## PR Description
!`gh pr view --json body --jq .body`

## Your Task
Review the above changes and provide feedback on:
- Code quality
- Test coverage
- Breaking changes
```

**Execution:**
1. User invokes `/pr-context`
2. Claude runs the shell commands before processing
3. Output replaces `` !`command` `` placeholders
4. Claude sees the actual file list, commits, and PR description

**Security note:** Commands run in your shell with your permissions. Only use in trusted skills.

---

## Next Steps & References

### Getting Started with Cortex-AI

**For new developers:**

1. **Read core docs:**
   - [QUICK_START.md](QUICK_START.md) - Get up and running in 5 minutes
   - [ORCHESTRATION_ARCHITECTURE.md](ORCHESTRATION_ARCHITECTURE.md) - Understand the design
   - [README.md](../README.md) - Project overview

2. **Set up CLAUDE.md:**
   - Copy the [Example CLAUDE.md](#example-1-complete-claudemd-for-cortex-ai) to `.claude/CLAUDE.md`
   - Customize for your workflow

3. **Create your first skill:**
   - Use the [Step-by-step guide](#creating-custom-skills)
   - Start with `/orchestration-dev` example
   - Test with `/skill-name` in Claude Code session

### Official Claude Code Documentation

- **CLAUDE.md Guide:** https://code.claude.com/docs/en/memory.md
- **Skills Guide:** https://code.claude.com/docs/en/skills.md
- **Subagents:** https://code.claude.com/docs/en/sub-agents.md
- **CLI Reference:** https://code.claude.com/docs/en/cli.md

### Related Cortex-AI Docs

| Doc | Purpose |
|-----|---------|
| [QUICK_START.md](QUICK_START.md) | Get started with cortex-ai in 5 minutes |
| [ORCHESTRATION_ARCHITECTURE.md](ORCHESTRATION_ARCHITECTURE.md) | Deep dive into agent orchestration |
| [MEMORY_STRATEGY.md](MEMORY_STRATEGY.md) | Memory middleware and persistence |
| [GRAPHRAG.md](GRAPHRAG.md) | GraphRAG implementation details |
| [CHAT_API.md](CHAT_API.md) | Chat API endpoints and SSE streaming |
| [RAG.md](RAG.md) | RAG architecture and query optimization |

### Suggested Learning Path

**Week 1: Understand the basics**
1. Read this guide (you are here!)
2. Set up `.claude/CLAUDE.md` for cortex-ai
3. Try existing skills: `/orchestration-dev`

**Week 2: Create custom content**
4. Organize rules into `.claude/rules/`
5. Create path-specific rules for API, orchestration, RAG
6. Test that rules activate correctly

**Week 3: Advanced patterns**
7. Build a custom skill for your workflow
8. Experiment with skill auto-activation
9. Use dynamic context (`` !`command` ``) in skills

### Community Resources

- **GitHub Issues:** Report bugs or request features
- **Discussions:** Ask questions, share patterns
- **Examples:** See `examples/` directory for working code

---

**Questions or feedback?** Open an issue on GitHub or check the [official Claude Code docs](https://code.claude.com/docs).

**Happy coding with Claude Code + Cortex-AI!** 🎯
