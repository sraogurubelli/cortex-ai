"""
LLM-based entity extraction for GraphRAG.

Uses Agent core to extract concepts and relationships from documents.
"""

import json
import logging
from typing import Any

from cortex.orchestration import Agent, ModelConfig
from cortex.rag.graph.schema import EntityExtractionResult

logger = logging.getLogger(__name__)


EXTRACTION_PROMPT = """You are an entity extraction specialist. Your task is to extract structured information from documents.

Extract the following from the given text:

1. **CONCEPTS**: Technical terms, topics, themes, technologies, methodologies, or important entities
   - Be specific and precise (e.g., "GraphRAG", "Neo4j", "Python", "LangGraph")
   - Avoid generic terms like "system", "data", "information"
   - Categorize each concept (e.g., "technology", "methodology", "language", "framework")

2. **RELATIONSHIPS**: How concepts relate to each other
   - Use clear relationship types (e.g., "USES", "IMPLEMENTS", "DEPENDS_ON", "ENABLES")
   - Provide a strength score (0.0 to 1.0) indicating confidence

Return your response as valid JSON only, with no additional text:
{
  "concepts": [
    {"name": "GraphRAG", "category": "methodology"},
    {"name": "Neo4j", "category": "technology"},
    {"name": "Python", "category": "language"}
  ],
  "relationships": [
    {"source": "GraphRAG", "target": "Neo4j", "type": "USES", "strength": 0.9},
    {"source": "GraphRAG", "target": "Python", "type": "IMPLEMENTS", "strength": 0.85}
  ]
}

Focus on domain-specific concepts. Be concise - extract only the most important entities (5-15 concepts typically)."""


class EntityExtractor:
    """
    LLM-based entity extractor using Agent core.

    Extracts concepts and relationships from text for knowledge graph building.
    """

    def __init__(
        self,
        model: ModelConfig | None = None,
    ):
        """
        Initialize entity extractor.

        Args:
            model: Model configuration. Defaults to gpt-4o-mini for cost efficiency.

        Example:
            >>> extractor = EntityExtractor(ModelConfig(model="gpt-4o-mini"))
            >>> result = await extractor.extract("GraphRAG uses Neo4j for graphs")
        """
        # Default to fast, cheap model for extraction
        if model is None:
            model = ModelConfig(model="gpt-4o-mini", temperature=0.0)

        self.agent = Agent(
            name="entity_extractor",
            system_prompt=EXTRACTION_PROMPT,
            model=model,
        )

        logger.info(f"EntityExtractor initialized with model: {model.model}")

    async def extract(self, text: str) -> EntityExtractionResult:
        """
        Extract entities and relationships from text.

        Uses LLM to identify:
        - Concepts (technical terms, topics, themes)
        - Relationships between concepts

        Args:
            text: Text to extract entities from

        Returns:
            EntityExtractionResult: Extracted concepts and relationships

        Raises:
            ValueError: If text is empty or extraction fails
            json.JSONDecodeError: If LLM returns invalid JSON

        Example:
            >>> result = await extractor.extract("GraphRAG uses Neo4j")
            >>> print(result.concepts)
            [{"name": "GraphRAG", "category": "methodology"}, ...]
            >>> print(result.relationships)
            [{"source": "GraphRAG", "target": "Neo4j", "type": "USES", "strength": 0.9}]
        """
        if not text.strip():
            raise ValueError("Text cannot be empty")

        # Truncate very long documents to avoid token limits
        max_chars = 15000  # ~4000 tokens
        if len(text) > max_chars:
            logger.warning(
                f"Text truncated from {len(text)} to {max_chars} chars for extraction"
            )
            text = text[:max_chars] + "\n\n[Text truncated...]"

        logger.debug(f"Extracting entities from {len(text)} chars of text")

        try:
            # Run extraction
            result = await self.agent.run(
                f"Extract entities from this text:\n\n{text}"
            )

            # Parse JSON response
            response_text = result.response.strip()

            # Handle markdown code blocks
            if response_text.startswith("```json"):
                response_text = response_text[7:]  # Remove ```json
            if response_text.startswith("```"):
                response_text = response_text[3:]  # Remove ```
            if response_text.endswith("```"):
                response_text = response_text[:-3]  # Remove ```

            response_text = response_text.strip()

            # Parse JSON
            data = json.loads(response_text)

            # Validate structure
            if "concepts" not in data or "relationships" not in data:
                raise ValueError(
                    "LLM response missing 'concepts' or 'relationships' fields"
                )

            # Create result
            extraction_result = EntityExtractionResult(
                concepts=data["concepts"],
                relationships=data["relationships"],
            )

            logger.info(
                f"Extracted {len(extraction_result.concepts)} concepts and "
                f"{len(extraction_result.relationships)} relationships"
            )

            return extraction_result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.error(f"Response: {result.response[:500]}")
            raise ValueError(
                f"LLM returned invalid JSON. Response: {result.response[:200]}"
            ) from e

        except Exception as e:
            logger.error(f"Entity extraction failed: {e}")
            raise

    async def extract_with_fallback(
        self,
        text: str,
        fallback_to_empty: bool = True,
    ) -> EntityExtractionResult:
        """
        Extract entities with graceful fallback on errors.

        Args:
            text: Text to extract entities from
            fallback_to_empty: Return empty result on error instead of raising

        Returns:
            EntityExtractionResult: Extracted entities or empty result

        Example:
            >>> result = await extractor.extract_with_fallback(text, fallback_to_empty=True)
            >>> # Will return empty result instead of raising on errors
        """
        try:
            return await self.extract(text)
        except Exception as e:
            if fallback_to_empty:
                logger.warning(
                    f"Entity extraction failed, returning empty result: {e}"
                )
                return EntityExtractionResult(concepts=[], relationships=[])
            else:
                raise
