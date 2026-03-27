# Commands & Agents - Cortex-AI

**Commands** and **Agents** are different from **Skills**:

- **Skills** - Reusable instruction bundles (invoke with `/skill-name`)
- **Commands** - Code generation workflows (invoke with `/command-name`)
- **Agents** - Specialized review/analysis agents (spawned by Claude or you)

---

## Commands (Code Generation)

Commands are workflows for generating boilerplate code.

### Available Commands

| Command | Purpose | Usage |
|---------|---------|-------|
| `/add-agent` | Generate new orchestration agent | `/add-agent` then provide YAML spec |
| `/add-api-endpoint` | Generate new FastAPI endpoint | `/add-api-endpoint` then provide YAML spec |

### How to Use Commands

#### Example: Create New Agent

```bash
# In Claude Code chat:
/add-agent
```

Then provide the specification:

```yaml
agentName: DataAnalysisAgent
moduleName: data_analysis
description: Analyzes data and generates insights
tools:
  - name: query_database
    description: Query the database
    parameters:
      - name: query
        type: str
        description: SQL query to execute
systemPrompt: |
  You are a data analysis assistant.
  Your role is to analyze data and provide insights.
```

**What happens:**
Claude will generate all necessary files:
- `cortex/orchestration/agents/data_analysis/agent.py`
- `cortex/orchestration/agents/data_analysis/tools.py`
- `cortex/orchestration/agents/data_analysis/config.py`
- `cortex/orchestration/agents/data_analysis/__init__.py`
- `tests/orchestration/agents/test_data_analysis.py`
- `examples/data_analysis_demo.py`
- `docs/agents/data_analysis.md`

#### Example: Create API Endpoint

```bash
# In Claude Code chat:
/add-api-endpoint
```

Then provide:

```yaml
endpointName: DataAnalysis
path: /api/v1/analysis
method: POST
description: Analyze data and return insights
requiresAuth: true
requestSchema:
  - name: data
    type: dict
    required: true
    description: Data to analyze
responseSchema:
  - name: analysis
    type: str
    description: Analysis results
```

---

## Agents (Code Review & Analysis)

Agents are specialized reviewers that can be spawned to analyze code.

### Available Agents

| Agent | Purpose | When to Use |
|-------|---------|-------------|
| `orchestration-reviewer` | Reviews orchestration agent code | After creating/modifying agents |
| `api-security-checker` | Checks API endpoints for vulnerabilities | After creating/modifying API routes |

### How to Use Agents

#### Method 1: Ask Claude to Spawn an Agent

```
User: "Can you review my orchestration code for best practices?"

Claude: [Spawns orchestration-reviewer agent]
        [Agent analyzes code and returns findings]
        [Claude summarizes results for you]
```

#### Method 2: Explicitly Request Agent

```
User: "Please use the orchestration-reviewer agent to check my changes in cortex/orchestration/agents/data_analysis/agent.py"
```

#### Method 3: In Agent Tool

```python
from cortex.orchestration import Agent

# You can create an agent that uses these agents
agent = Agent(
    name="code_reviewer",
    # ... configuration
)
```

### Agent Output Examples

#### orchestration-reviewer Output

```markdown
## Orchestration Code Review

### Issues Found

#### Critical (2)
1. Missing await keyword (Line 45)
2. User ID in system prompt (Line 23)

#### High (1)
1. No error handling (Line 45)

### Recommendation: REQUEST CHANGES
```

#### api-security-checker Output

```markdown
## API Security Review

### Vulnerabilities Found

#### Critical (1)
1. No Authentication Required (Line 15)
   - CVSS Score: 9.1
   - Fix: Add Depends(get_current_user)

### Security Score: 4/10 ⚠️
### Risk Level: HIGH
```

---

## Differences: Skills vs Commands vs Agents

| Aspect | Skills | Commands | Agents |
|--------|--------|----------|--------|
| **Purpose** | Reference & workflows | Code generation | Code review/analysis |
| **Invoke** | `/skill-name` | `/command-name` | Spawned by Claude |
| **File** | `SKILL.md` | `{command}.md` | `{agent}.md` |
| **Location** | `.claude/skills/` | `.claude/commands/` | `.claude/agents/` |
| **Output** | Instructions/guidance | Generated code files | Analysis report |
| **Auto-activate** | Based on paths | No | No |
| **User-facing** | Yes (`/` menu) | Yes (`/` menu) | No (spawned by Claude) |

### When to Use What

**Use Skills when:**
- You need reference material (patterns, examples)
- You want workflow guidance (how to create something)
- Path-specific help needed

**Use Commands when:**
- You need to generate boilerplate code
- You're creating new modules/files
- You want scaffolding/templates

**Use Agents when:**
- You need code review
- You want security analysis
- You need quality assessment

---

## Creating Custom Commands

### Structure

```markdown
---
description: What this command does
---

Instructions for Claude to follow...

## Input Format

YAML specification user provides

## Files to Create

List of files to generate with templates

## Checklist

Verification steps
```

### Example: Simple Command

**File:** `.claude/commands/add-test.md`

```markdown
---
description: Generate test file for a module
---

Generate a test file for the specified module.

## Input

```yaml
moduleName: data_analysis
testType: unit  # or integration
```

## Files to Create

**Path:** `tests/{testType}/test_{moduleName}.py`

```python
import pytest

# Tests here
```
```

---

## Creating Custom Agents

### Structure

```markdown
---
name: agent-name
description: What this agent does
allowed_tools:
  - Read, Glob, Grep
---

# Agent Title

Your expertise...

## Review Checklist
...

## Common Issues
...

## Review Output Format
...
```

### Example: Simple Agent

**File:** `.claude/agents/test-reviewer.md`

```markdown
---
name: test-reviewer
description: Reviews test files for coverage and best practices
allowed_tools:
  - Read, Grep
---

# Test Code Reviewer

You review test files for:

1. Test coverage (all functions tested)
2. Async tests use @pytest.mark.asyncio
3. Tests are independent
4. Proper assertions

## Review Checklist

- [ ] All public functions have tests
- [ ] Tests use proper markers
- [ ] No shared state between tests
- [ ] Specific assertions (not just `assert True`)

## Output

List issues with severity and fixes.
```

---

## Best Practices

### Commands

✅ **Do:**
- Provide clear YAML schema
- Include examples
- Generate complete, runnable code
- Include tests in generated code
- Provide checklist for verification

❌ **Don't:**
- Generate code without templates
- Skip test generation
- Forget documentation

### Agents

✅ **Do:**
- Focus on specific domain (orchestration, API, security)
- Provide actionable feedback
- Include severity levels
- Give fix suggestions
- Use allowed_tools efficiently

❌ **Don't:**
- Try to review everything at once
- Give vague feedback
- Skip severity classification

---

## Directory Structure

```
cortex-ai/.claude/
├── skills/              # Reusable workflows
│   ├── orchestration-dev/
│   ├── rag-query/
│   └── api-endpoint/
├── commands/            # Code generation
│   ├── add-agent.md
│   └── add-api-endpoint.md
├── agents/              # Code review/analysis
│   ├── orchestration-reviewer.md
│   └── api-security-checker.md
└── rules/               # Path-specific rules
    ├── orchestration.md
    ├── api.md
    └── ...
```

---

## Testing Your Commands/Agents

### Test a Command

```bash
# In Claude Code:
/add-agent

# Provide test specification
# Verify all files generated correctly
# Run tests: pytest tests/orchestration/agents/test_myagent.py
```

### Test an Agent

```bash
# Create some code with issues
# Ask Claude to review it
"Please review my orchestration code for issues"

# Claude should spawn orchestration-reviewer agent
# Verify issues are detected correctly
```

---

## Tips

1. **Keep commands focused** - One command = one type of generation
2. **Make agents specialized** - One agent = one type of review
3. **Use templates** - Commands should generate consistent code
4. **Provide examples** - Show expected YAML input
5. **Include verification** - Checklists ensure completeness

---

## Reference

- **Commands:** [`.claude/commands/`](commands/)
- **Agents:** [`.claude/agents/`](agents/)
- **Skills:** [`.claude/skills/`](skills/)
- **Rules:** [`.claude/rules/`](rules/)

---

**Questions?** See [`CLAUDE_CODE_GUIDE.md`](../docs/CLAUDE_CODE_GUIDE.md) for complete reference.
