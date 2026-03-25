"""
Semantic layer interfaces and implementations.

Defines the abstract ``SemanticLayer`` protocol and a concrete
in-memory implementation. Domain-specific implementations can load
schemas from gRPC services, HTTP APIs, or files.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class SchemaDefinition:
    """A loaded entity schema.

    Attributes:
        name: Schema identifier (e.g. "deployment", "pipeline").
        entity_type: Category of the entity (e.g. "k8s", "harness").
        schema: The schema as a dict (JSON Schema, protobuf descriptor, etc.).
        description: Human-readable description for LLM context.
        version: Schema version.
    """

    name: str
    entity_type: str = ""
    schema: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    version: str = "1.0"


@dataclass
class GrammarDefinition:
    """A loaded query grammar.

    Attributes:
        name: Grammar identifier (e.g. "hql", "sql", "graphql").
        syntax_rules: Formal grammar rules as text or structured data.
        examples: Example queries for few-shot prompting.
        description: Human-readable description for LLM context.
    """

    name: str
    syntax_rules: str = ""
    examples: list[str] = field(default_factory=list)
    description: str = ""


@dataclass
class ValidationResult:
    """Result of query validation against a grammar or schema."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    corrected_query: Optional[str] = None


class SemanticLayer(ABC):
    """Abstract interface for schema and grammar-driven structured output.

    Implement this to enable agents to generate structured queries,
    configurations, or API calls based on domain-specific schemas.
    """

    @abstractmethod
    async def load_schema(self, name: str, **kwargs) -> Optional[SchemaDefinition]:
        """Load an entity schema by name.

        Args:
            name: Schema identifier.

        Returns:
            SchemaDefinition or None if not found.
        """
        ...

    @abstractmethod
    async def load_grammar(self, name: str, **kwargs) -> Optional[GrammarDefinition]:
        """Load a query grammar by name.

        Args:
            name: Grammar identifier.

        Returns:
            GrammarDefinition or None if not found.
        """
        ...

    @abstractmethod
    async def validate_query(
        self, query: str, grammar_name: str, **kwargs
    ) -> ValidationResult:
        """Validate a generated query against a grammar.

        Args:
            query: The generated query string.
            grammar_name: Name of the grammar to validate against.

        Returns:
            ValidationResult indicating whether the query is valid.
        """
        ...

    @abstractmethod
    async def list_schemas(self) -> list[str]:
        """List available schema names."""
        ...

    @abstractmethod
    async def list_grammars(self) -> list[str]:
        """List available grammar names."""
        ...


class InMemorySemanticLayer(SemanticLayer):
    """In-memory semantic layer for development and testing.

    Schemas and grammars are registered programmatically.
    For production, subclass ``SemanticLayer`` to load from
    gRPC services or HTTP APIs.
    """

    def __init__(self) -> None:
        self._schemas: dict[str, SchemaDefinition] = {}
        self._grammars: dict[str, GrammarDefinition] = {}

    def register_schema(self, schema: SchemaDefinition) -> "InMemorySemanticLayer":
        self._schemas[schema.name] = schema
        return self

    def register_grammar(self, grammar: GrammarDefinition) -> "InMemorySemanticLayer":
        self._grammars[grammar.name] = grammar
        return self

    async def load_schema(self, name: str, **kwargs) -> Optional[SchemaDefinition]:
        return self._schemas.get(name)

    async def load_grammar(self, name: str, **kwargs) -> Optional[GrammarDefinition]:
        return self._grammars.get(name)

    async def validate_query(
        self, query: str, grammar_name: str, **kwargs
    ) -> ValidationResult:
        grammar = self._grammars.get(grammar_name)
        if not grammar:
            return ValidationResult(
                valid=False,
                errors=[f"Grammar '{grammar_name}' not found"],
            )
        # Basic validation: check query is non-empty
        if not query.strip():
            return ValidationResult(valid=False, errors=["Query is empty"])
        return ValidationResult(valid=True)

    async def list_schemas(self) -> list[str]:
        return list(self._schemas.keys())

    async def list_grammars(self) -> list[str]:
        return list(self._grammars.keys())
