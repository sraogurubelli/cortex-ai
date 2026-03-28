# Architecture Documentation Rules

**Auto-loads when:** Working with architecture docs, explaining system design, or discussing component interactions

---

## Visual-First Approach

When documenting or explaining architecture, always lead with visual diagrams, not code.

### ✅ Do

- **Lead with visual diagrams** (ASCII art, boxes and arrows)
- **Show data flow** with clear directional arrows (→, ↓, ▼)
- **Label components** with their purpose
- **Include storage layers** (databases, caches, collections)
- **Use layers** to show separation (API → Services → Storage)
- **Show before/after** when proposing changes
- **Number steps** in sequential flows (1, 2, 3, ...)
- **Use tables** for feature comparisons
- **Explain each diagram** with text after the visual
- **Keep diagrams focused** (one concept per diagram)

### ❌ Don't

- Lead with code examples for architecture (code comes after diagrams)
- Mix code and diagrams in the same section
- Create diagrams without labels or explanations
- Skip showing storage/persistence layers
- Assume user knows component relationships
- Use diagrams for implementation details (use code for that)

---

## Diagram Format Standards

### Component Boxes

```
┌─────────────┐
│  Component  │  ← Clear label
│    Name     │
└─────────────┘
```

### Data Flow (Single Direction)

```
┌──────┐      ┌──────┐      ┌──────┐
│  A   │─────▶│  B   │─────▶│  C   │
└──────┘      └──────┘      └──────┘
   ↓
Process description
```

### Multi-Path Flow

```
      ┌──────┐
      │ Start│
      └───┬──┘
          │
    ┌─────┴─────┐
    │           │
    ▼           ▼
┌──────┐    ┌──────┐
│ Path │    │ Path │
│  1   │    │  2   │
└───┬──┘    └───┬──┘
    │           │
    └─────┬─────┘
          ▼
      ┌──────┐
      │  End │
      └──────┘
```

### Layered Architecture

```
┌────────────────────────────────────┐
│         API Layer                  │
├────────────────────────────────────┤
│         Service Layer              │
├────────────────────────────────────┤
│         Storage Layer              │
│  ┌─────────┐  ┌─────────┐        │
│  │ Qdrant  │  │ Neo4j   │        │
│  └─────────┘  └─────────┘        │
└────────────────────────────────────┘
```

### Before/After Comparison

```
┌──────────────────┬──────────────────┐
│     BEFORE       │      AFTER       │
├──────────────────┼──────────────────┤
│                  │                  │
│  [Diagram 1]     │  [Diagram 2]     │
│                  │                  │
│  Problem: ...    │  Solution: ...   │
│                  │                  │
└──────────────────┴──────────────────┘
```

### Storage Topology

```
┌──────────┐  ┌──────────┐  ┌──────────┐
│ Store 1  │  │ Store 2  │  │ Store 3  │
│          │  │          │  │          │
│ Purpose: │  │ Purpose: │  │ Purpose: │
│ [...]    │  │ [...]    │  │ [...]    │
│          │  │          │  │          │
│ Used by: │  │ Used by: │  │ Used by: │
│ [...]    │  │ [...]    │  │ [...]    │
└──────────┘  └──────────┘  └──────────┘
```

---

## Structure for Architecture Documents

Every architecture document should follow this structure:

### 1. Overview Diagram
- High-level system view
- Main components and relationships
- Data flow at a glance

### 2. Component Breakdown
- Each major component explained
- Inputs and outputs
- Purpose and responsibilities

### 3. Detailed Flow Diagrams
- Step-by-step process
- Sequential numbering
- Show decision points

### 4. Storage Architecture
- What's stored where
- Data relationships
- Collection/table purposes

### 5. Integration Points
- How components connect
- API boundaries
- Event flows

### 6. (Optional) Implementation Examples
- **After** visual explanation
- Code snippets for clarity
- Link to actual code files

---

## Examples

### ✅ Good: Visual First

```markdown
## User Authentication Flow

┌──────────────┐
│ User Login   │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Validate     │
│ Credentials  │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Generate JWT │
└──────────────┘

**Explanation:**
1. User submits credentials
2. System validates against database
3. On success, JWT token generated
```

### ❌ Bad: Code First

```markdown
## User Authentication Flow

```python
# Don't lead with this
def login(username, password):
    user = db.get_user(username)
    if verify_password(password, user.hash):
        return generate_jwt(user)
```
```

**Why bad:** No visual context, hard to understand flow

---

## When to Create Architecture Docs

Create or update architecture documentation when:

- [ ] New system component added
- [ ] Significant architectural change
- [ ] Complex data flow needs explanation
- [ ] Integration between multiple systems
- [ ] Before implementation (design phase)
- [ ] User asks "how does X work?"
- [ ] Explaining trade-offs between approaches

---

## File Naming Conventions

```
docs/architecture/
├── SYSTEM_NAME.md          ← Main architecture docs (UPPERCASE)
├── component-name.md       ← Component-specific (lowercase)
├── diagrams/               ← Image files if needed
│   ├── overview.png
│   └── detailed-flow.png
└── README.md               ← Index of all architecture docs
```

**Naming rules:**
- Use `UPPERCASE` for main architecture documents
- Use `lowercase-with-hyphens` for component-specific docs
- Use descriptive names (not generic like `doc1.md`)

---

## Section Headers

Use consistent header style:

```markdown
## 1. Component Name

**Purpose:** One-line description

[Visual diagram here]

**Explanation:**
- Point 1
- Point 2
- Point 3

**Used by:**
- System A
- System B
```

---

## Comparison Tables

When comparing approaches or systems, use tables:

```markdown
| Feature | Approach A | Approach B |
|---------|-----------|------------|
| Speed   | Fast      | Slow       |
| Memory  | High      | Low        |
| Use Case| Real-time | Batch      |
```

---

## Integration with Code

### Reference Code, Don't Duplicate

```markdown
## Implementation

See actual code:
- [Retriever](../../cortex/rag/retriever.py) - Main search logic
- [GraphStore](../../cortex/rag/graph/graph_store.py) - Neo4j operations

**Key function:**
- `graphrag_search()` at line 618 - Hybrid search implementation
```

### Small Snippets Only

If code is necessary, keep it minimal:

```python
# ✅ Good: Concise pseudo-code
query_embedding = embed(query)
results = search(query_embedding)

# ❌ Bad: Full implementation
async def graphrag_search(
    self,
    query: str,
    top_k: int = 5,
    vector_weight: float = 0.7,
    graph_weight: float = 0.3,
    max_hops: int = 2,
    tenant_id: str | None = None,
) -> list[SearchResult]:
    """
    [50 more lines of implementation...]
    """
```

---

## Visual Style Guide

### Box Widths

Keep boxes aligned for readability:

```
✅ Good:
┌──────────┐      ┌──────────┐
│ Component│─────▶│ Component│
└──────────┘      └──────────┘

❌ Bad:
┌────┐      ┌────────────────────┐
│ A  │─────▶│ B                  │
└────┘      └────────────────────┘
```

### Arrows

- `─────▶` for data flow
- `│` for vertical flow
- `└──┘` for connections
- `▼` for emphasis on direction

### Spacing

Use blank lines for visual separation:

```
Component 1
     │
     │ [explain what happens]
     │
     ▼
Component 2
```

---

## Common Patterns

### Request/Response Flow

```
Client
  │
  │ 1. Request
  ▼
Server
  │
  │ 2. Process
  ▼
Database
  │
  │ 3. Return data
  ▼
Server
  │
  │ 4. Response
  ▼
Client
```

### Caching Pattern

```
Request
  │
  ▼
┌─────────┐
│ Cache?  │
└────┬────┘
     │
  ┌──┴──┐
  │     │
 Yes    No
  │     │
  ▼     ▼
Return  Compute
        │
        │ (save to cache)
        ▼
      Return
```

### Parallel Processing

```
Input
  │
  ├─────────┬─────────┐
  │         │         │
  ▼         ▼         ▼
Task 1   Task 2   Task 3
  │         │         │
  └─────────┴─────────┘
  │
  ▼
Merge Results
```

---

## Quality Checklist

Before finalizing architecture documentation:

- [ ] Every diagram has a title
- [ ] Every arrow has a label or explanation
- [ ] Storage layers are shown
- [ ] Data flow is clear (left-to-right or top-to-bottom)
- [ ] Components are labeled with purpose
- [ ] Explanatory text follows each diagram
- [ ] No orphaned components (everything connects)
- [ ] Before/after shown for changes
- [ ] Tables used for comparisons
- [ ] Links to actual code provided

---

## Examples in This Project

Good reference documents:
- [RAG Architecture](../../docs/architecture/RAG_ARCHITECTURE.md) - Visual-first approach
- [GNN Architecture](../../docs/gnn/ARCHITECTURE.md) - Integration points with diagrams

---

**Remember:** Diagrams first, code second. Architecture is about structure and relationships, not implementation details.

---

**Last Updated:** March 28, 2026
**Auto-loads:** When working with architecture
