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

# Optional import for embeddings
try:
    from cortex.rag.embeddings import EmbeddingService
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    logger.debug("EmbeddingService not available for entity embeddings")


EXTRACTION_PROMPT = """You are a knowledge extraction expert. Your task is to extract structured information from documents.

Extract the following from the given text:

1. **CONCEPTS** (abstract ideas): Technical terms, topics, themes, technologies, methodologies
   - Examples: "GraphRAG", "Machine Learning", "Microservices", "Agile Development"
   - Be specific and precise - avoid generic terms like "system", "data", "information"
   - Categorize each concept (e.g., "technology", "methodology", "framework")

2. **ENTITIES** (concrete things): People, companies, products, locations, events
   - **Person**: "Alice Johnson", "John Smith"
   - **Company**: "Acme Corp", "Google", "Microsoft"
   - **Product**: "Widget A", "iPhone", "Neo4j Database"
   - **Location**: "San Francisco", "New York", "Paris"
   - **Event**: "2024 Summit", "Launch Event"
   - Include properties like title, role, industry, etc. when available

3. **RELATIONSHIPS**: How concepts and entities relate to each other
   - Between entities: "WORKS_AT", "PRODUCES", "LOCATED_IN", "FOUNDED_BY", "OWNS", "MANAGES"
   - Between concepts: "USES", "IMPLEMENTS", "DEPENDS_ON", "ENABLES", "RELATES_TO"
   - Concept to entity: "APPLIES_TO", "USED_BY"

Return your response as valid JSON only, with no additional text:
{
  "concepts": [
    {"name": "GraphRAG", "category": "methodology"},
    {"name": "Machine Learning", "category": "technology"}
  ],
  "entities": [
    {"name": "Alice Johnson", "type": "person", "properties": {"title": "CEO", "department": "Engineering"}},
    {"name": "Acme Corp", "type": "company", "properties": {"industry": "Technology"}},
    {"name": "Neo4j", "type": "product", "properties": {"category": "Database"}}
  ],
  "relationships": [
    {"source": "Alice Johnson", "target": "Acme Corp", "type": "WORKS_AT", "properties": {"since": "2020"}},
    {"source": "Acme Corp", "target": "Neo4j", "type": "USES", "properties": {}},
    {"source": "GraphRAG", "target": "Neo4j", "type": "APPLIES_TO", "properties": {"strength": 0.9}}
  ]
}

Be thorough but concise. Extract 5-20 concepts and 5-15 entities typically."""


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
        Extract concepts, entities, and relationships from text.

        Uses LLM to identify:
        - Concepts (abstract ideas: technical terms, methodologies)
        - Entities (concrete things: people, companies, products)
        - Relationships between concepts and entities

        Args:
            text: Text to extract knowledge from

        Returns:
            EntityExtractionResult: Extracted concepts, entities, and relationships

        Raises:
            ValueError: If text is empty or extraction fails
            json.JSONDecodeError: If LLM returns invalid JSON

        Example:
            >>> result = await extractor.extract("Alice Johnson works at Acme Corp using GraphRAG")
            >>> print(result.concepts)
            [{"name": "GraphRAG", "category": "methodology"}, ...]
            >>> print(result.entities)
            [{"name": "Alice Johnson", "type": "person", "properties": {...}}, ...]
            >>> print(result.relationships)
            [{"source": "Alice Johnson", "target": "Acme Corp", "type": "WORKS_AT", "properties": {}}]
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

        logger.debug(f"Extracting knowledge from {len(text)} chars of text")

        try:
            # Run extraction
            result = await self.agent.run(
                f"Extract knowledge from this text:\n\n{text}"
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

            # Validate structure (concepts and entities are required, relationships optional)
            if "concepts" not in data:
                logger.warning("LLM response missing 'concepts' field, using empty list")
                data["concepts"] = []

            if "entities" not in data:
                logger.warning("LLM response missing 'entities' field, using empty list")
                data["entities"] = []

            if "relationships" not in data:
                logger.warning("LLM response missing 'relationships' field, using empty list")
                data["relationships"] = []

            # Create result
            extraction_result = EntityExtractionResult(
                concepts=data["concepts"],
                entities=data["entities"],
                relationships=data["relationships"],
            )

            logger.info(
                f"Extracted {len(extraction_result.concepts)} concepts, "
                f"{len(extraction_result.entities)} entities, and "
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
        Extract knowledge with graceful fallback on errors.

        Args:
            text: Text to extract knowledge from
            fallback_to_empty: Return empty result on error instead of raising

        Returns:
            EntityExtractionResult: Extracted knowledge or empty result

        Example:
            >>> result = await extractor.extract_with_fallback(text, fallback_to_empty=True)
            >>> # Will return empty result instead of raising on errors
        """
        try:
            return await self.extract(text)
        except Exception as e:
            if fallback_to_empty:
                logger.warning(
                    f"Knowledge extraction failed, returning empty result: {e}"
                )
                return EntityExtractionResult(concepts=[], entities=[], relationships=[])
            else:
                raise

    async def extract_with_embeddings(
        self,
        text: str,
        embedding_service: Any = None,
    ) -> EntityExtractionResult:
        """
        Extract knowledge and generate embeddings for GNN readiness.

        Extracts concepts and entities, then generates vector embeddings
        for each using the provided EmbeddingService.

        Args:
            text: Text to extract knowledge from
            embedding_service: EmbeddingService instance for generating embeddings.
                             If None, embeddings will not be generated.

        Returns:
            EntityExtractionResult: Extracted knowledge with embeddings

        Example:
            >>> from cortex.rag.embeddings import EmbeddingService
            >>> embeddings = EmbeddingService()
            >>> await embeddings.connect()
            >>> result = await extractor.extract_with_embeddings(text, embeddings)
            >>> # result.concepts[0]["embedding"] contains 1536-dim vector
            >>> # result.entities[0]["embedding"] contains 1536-dim vector
        """
        # First extract without embeddings
        result = await self.extract(text)

        # If no embedding service, return as-is
        if embedding_service is None:
            logger.debug("No embedding service provided, skipping embedding generation")
            return result

        # Generate embeddings for concepts
        if result.concepts:
            concept_texts = [concept["name"] for concept in result.concepts]
            try:
                concept_embeddings = await embedding_service.generate_embeddings(concept_texts)
                for i, concept in enumerate(result.concepts):
                    concept["embedding"] = concept_embeddings[i]
                logger.debug(f"Generated embeddings for {len(result.concepts)} concepts")
            except Exception as e:
                logger.error(f"Failed to generate concept embeddings: {e}")
                # Continue without embeddings

        # Generate embeddings for entities
        if result.entities:
            entity_texts = [entity["name"] for entity in result.entities]
            try:
                entity_embeddings = await embedding_service.generate_embeddings(entity_texts)
                for i, entity in enumerate(result.entities):
                    entity["embedding"] = entity_embeddings[i]
                logger.debug(f"Generated embeddings for {len(result.entities)} entities")
            except Exception as e:
                logger.error(f"Failed to generate entity embeddings: {e}")
                # Continue without embeddings

        return result
