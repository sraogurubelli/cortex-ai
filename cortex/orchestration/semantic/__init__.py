"""
Semantic Layer — schema and grammar-driven structured output generation.

Ported from ml-infra's ``capabilities/tools/semantic_layer/`` pattern.
Provides an abstract interface for loading entity schemas and query
grammars from external sources, enabling agents to generate structured
queries, configurations, and API calls.

Usage::

    from cortex.orchestration.semantic import (
        SemanticLayer,
        SchemaDefinition,
        GrammarDefinition,
        InMemorySemanticLayer,
    )

    # In-memory semantic layer with preloaded schemas
    layer = InMemorySemanticLayer()
    layer.register_schema(SchemaDefinition(
        name="deployment",
        entity_type="k8s",
        schema={"type": "object", "properties": {...}},
    ))

    schema = await layer.load_schema("deployment")
    grammar = await layer.load_grammar("hql")
    result = await layer.validate_query("SELECT * FROM deployments", "hql")
"""

from cortex.orchestration.semantic.layer import (
    GrammarDefinition,
    InMemorySemanticLayer,
    SchemaDefinition,
    SemanticLayer,
    ValidationResult,
)

__all__ = [
    "SemanticLayer",
    "SchemaDefinition",
    "GrammarDefinition",
    "ValidationResult",
    "InMemorySemanticLayer",
]
