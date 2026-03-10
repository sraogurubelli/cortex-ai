"""
Neo4j graph store for GraphRAG.

Provides CRUD operations for knowledge graph nodes and relationships.
"""

import logging
import os
import uuid
from datetime import datetime
from typing import Any

from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession
from neo4j.exceptions import ServiceUnavailable, AuthError

from cortex.rag.graph.schema import Document, Concept

logger = logging.getLogger(__name__)


class GraphStore:
    """
    Neo4j graph store for knowledge graphs.

    Manages document and concept nodes with relationships.
    Provides async CRUD operations following VectorStore patterns.
    """

    def __init__(
        self,
        url: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ):
        """
        Initialize graph store.

        Args:
            url: Neo4j connection URL (bolt://host:port). Defaults to CORTEX_NEO4J_URL env var.
            user: Neo4j username. Defaults to CORTEX_NEO4J_USER env var or 'neo4j'.
            password: Neo4j password. Defaults to CORTEX_NEO4J_PASSWORD env var.

        Example:
            >>> graph = GraphStore(url="bolt://localhost:7687", user="neo4j", password="password")
            >>> await graph.connect()
        """
        self.url = url or os.getenv("CORTEX_NEO4J_URL", "bolt://localhost:7687")
        self.user = user or os.getenv("CORTEX_NEO4J_USER", "neo4j")
        self.password = password or os.getenv("CORTEX_NEO4J_PASSWORD")

        if not self.password:
            raise ValueError(
                "Neo4j password must be provided via 'password' parameter or "
                "CORTEX_NEO4J_PASSWORD environment variable"
            )

        self.driver: AsyncDriver | None = None
        self._connected = False

        logger.info(f"GraphStore initialized with URL: {self.url}")

    async def connect(self) -> None:
        """
        Connect to Neo4j database.

        Idempotent - safe to call multiple times.

        Raises:
            ServiceUnavailable: If Neo4j is not reachable
            AuthError: If credentials are invalid
        """
        if self._connected:
            logger.debug("GraphStore already connected")
            return

        try:
            self.driver = AsyncGraphDatabase.driver(
                self.url,
                auth=(self.user, self.password),
            )

            # Verify connection
            await self.driver.verify_connectivity()
            self._connected = True

            logger.info("GraphStore connected to Neo4j")

        except ServiceUnavailable as e:
            logger.error(f"Failed to connect to Neo4j at {self.url}: {e}")
            raise
        except AuthError as e:
            logger.error(f"Neo4j authentication failed for user {self.user}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error connecting to Neo4j: {e}")
            raise

    async def disconnect(self) -> None:
        """
        Close Neo4j connection.

        Safe to call even if not connected.
        """
        if not self._connected or self.driver is None:
            logger.debug("GraphStore not connected, nothing to disconnect")
            return

        try:
            await self.driver.close()
            self._connected = False
            self.driver = None
            logger.info("GraphStore disconnected from Neo4j")

        except Exception as e:
            logger.error(f"Error disconnecting from Neo4j: {e}")
            raise

    async def create_constraints(self) -> None:
        """
        Create unique constraints and indexes.

        Creates:
        - Unique constraint on Document.id
        - Unique constraint on Concept.id
        - Index on Document.tenant_id
        - Index on Concept.tenant_id
        - Index on Concept.name

        Idempotent - safe to call multiple times.
        """
        if not self._connected or self.driver is None:
            raise RuntimeError("GraphStore not connected. Call connect() first.")

        constraints = [
            # Unique constraints
            "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE",
            "CREATE CONSTRAINT concept_id IF NOT EXISTS FOR (c:Concept) REQUIRE c.id IS UNIQUE",
        ]

        indexes = [
            # Performance indexes
            "CREATE INDEX document_tenant IF NOT EXISTS FOR (d:Document) ON (d.tenant_id)",
            "CREATE INDEX concept_tenant IF NOT EXISTS FOR (c:Concept) ON (c.tenant_id)",
            "CREATE INDEX concept_name IF NOT EXISTS FOR (c:Concept) ON (c.name)",
        ]

        async with self.driver.session() as session:
            for constraint in constraints:
                try:
                    await session.run(constraint)
                    logger.debug(f"Created constraint: {constraint}")
                except Exception as e:
                    logger.warning(f"Constraint creation failed (may already exist): {e}")

            for index in indexes:
                try:
                    await session.run(index)
                    logger.debug(f"Created index: {index}")
                except Exception as e:
                    logger.warning(f"Index creation failed (may already exist): {e}")

        logger.info("Graph constraints and indexes created")

    async def add_document(
        self,
        doc_id: str,
        content: str,
        tenant_id: str,
    ) -> str:
        """
        Add document node to graph.

        Args:
            doc_id: Document ID (same as Qdrant doc_id)
            content: Full document text
            tenant_id: Tenant ID for multi-tenancy

        Returns:
            str: Document ID

        Example:
            >>> await graph.add_document("doc-123", "GraphRAG uses Neo4j", "tenant-1")
            'doc-123'
        """
        if not self._connected or self.driver is None:
            raise RuntimeError("GraphStore not connected. Call connect() first.")

        query = """
        MERGE (d:Document {id: $doc_id})
        SET d.content = $content,
            d.tenant_id = $tenant_id,
            d.created_at = datetime($created_at)
        RETURN d.id as id
        """

        async with self.driver.session() as session:
            result = await session.run(
                query,
                doc_id=doc_id,
                content=content,
                tenant_id=tenant_id,
                created_at=datetime.utcnow().isoformat(),
            )
            record = await result.single()

            if record:
                logger.debug(f"Added document {doc_id} to graph")
                return record["id"]
            else:
                raise RuntimeError(f"Failed to add document {doc_id}")

    async def add_concept(
        self,
        name: str,
        category: str,
        tenant_id: str,
    ) -> str:
        """
        Add concept node to graph.

        Uses MERGE to avoid duplicates - returns existing concept if name matches.

        Args:
            name: Concept name (e.g., "GraphRAG", "Neo4j")
            category: Concept category (e.g., "technology", "methodology")
            tenant_id: Tenant ID for multi-tenancy

        Returns:
            str: Concept ID (UUID)

        Example:
            >>> concept_id = await graph.add_concept("GraphRAG", "methodology", "tenant-1")
        """
        if not self._connected or self.driver is None:
            raise RuntimeError("GraphStore not connected. Call connect() first.")

        # MERGE on name + tenant_id to avoid duplicates
        query = """
        MERGE (c:Concept {name: $name, tenant_id: $tenant_id})
        ON CREATE SET c.id = $concept_id,
                      c.category = $category,
                      c.created_at = datetime($created_at)
        RETURN c.id as id
        """

        concept_id = str(uuid.uuid4())

        async with self.driver.session() as session:
            result = await session.run(
                query,
                concept_id=concept_id,
                name=name,
                category=category,
                tenant_id=tenant_id,
                created_at=datetime.utcnow().isoformat(),
            )
            record = await result.single()

            if record:
                logger.debug(f"Added/found concept '{name}' with ID {record['id']}")
                return record["id"]
            else:
                raise RuntimeError(f"Failed to add concept '{name}'")

    async def add_relationship(
        self,
        source_id: str,
        target_id: str,
        rel_type: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """
        Add relationship between nodes.

        Args:
            source_id: Source node ID
            target_id: Target node ID
            rel_type: Relationship type (e.g., "MENTIONS", "RELATES_TO")
            properties: Additional relationship properties

        Example:
            >>> await graph.add_relationship(
            ...     "doc-123",
            ...     concept_id,
            ...     "MENTIONS",
            ...     {"count": 3, "confidence": 0.95}
            ... )
        """
        if not self._connected or self.driver is None:
            raise RuntimeError("GraphStore not connected. Call connect() first.")

        properties = properties or {}

        # Use MERGE to avoid duplicate relationships
        query = f"""
        MATCH (source {{id: $source_id}})
        MATCH (target {{id: $target_id}})
        MERGE (source)-[r:{rel_type}]->(target)
        SET r += $properties
        RETURN type(r) as rel_type
        """

        async with self.driver.session() as session:
            result = await session.run(
                query,
                source_id=source_id,
                target_id=target_id,
                properties=properties,
            )
            record = await result.single()

            if record:
                logger.debug(
                    f"Added relationship {source_id} -[{rel_type}]-> {target_id}"
                )
            else:
                logger.warning(
                    f"Failed to create relationship (nodes may not exist): "
                    f"{source_id} -[{rel_type}]-> {target_id}"
                )

    async def get_document(self, doc_id: str) -> Document | None:
        """
        Get document by ID.

        Args:
            doc_id: Document ID

        Returns:
            Document | None: Document if found, None otherwise

        Example:
            >>> doc = await graph.get_document("doc-123")
            >>> if doc:
            ...     print(doc.content)
        """
        if not self._connected or self.driver is None:
            raise RuntimeError("GraphStore not connected. Call connect() first.")

        query = """
        MATCH (d:Document {id: $doc_id})
        RETURN d.id as id, d.content as content,
               d.tenant_id as tenant_id, d.created_at as created_at
        """

        async with self.driver.session() as session:
            result = await session.run(query, doc_id=doc_id)
            record = await result.single()

            if record:
                return Document(
                    id=record["id"],
                    content=record["content"],
                    tenant_id=record["tenant_id"],
                    created_at=record["created_at"],
                )
            else:
                return None

    async def get_document_concepts(
        self,
        doc_id: str,
        tenant_id: str | None = None,
    ) -> list[Concept]:
        """
        Get all concepts mentioned by a document.

        Args:
            doc_id: Document ID
            tenant_id: Optional tenant ID for filtering

        Returns:
            list[Concept]: List of concepts mentioned by the document

        Example:
            >>> concepts = await graph.get_document_concepts("doc-123")
            >>> for concept in concepts:
            ...     print(f"{concept.name} ({concept.category})")
        """
        if not self._connected or self.driver is None:
            raise RuntimeError("GraphStore not connected. Call connect() first.")

        # Build query with optional tenant filter
        if tenant_id:
            query = """
            MATCH (d:Document {id: $doc_id})-[:MENTIONS]->(c:Concept {tenant_id: $tenant_id})
            RETURN c.id as id, c.name as name, c.category as category,
                   c.tenant_id as tenant_id, c.created_at as created_at
            ORDER BY c.name
            """
            params = {"doc_id": doc_id, "tenant_id": tenant_id}
        else:
            query = """
            MATCH (d:Document {id: $doc_id})-[:MENTIONS]->(c:Concept)
            RETURN c.id as id, c.name as name, c.category as category,
                   c.tenant_id as tenant_id, c.created_at as created_at
            ORDER BY c.name
            """
            params = {"doc_id": doc_id}

        async with self.driver.session() as session:
            result = await session.run(query, **params)
            records = await result.values()

            concepts = [
                Concept(
                    id=record[0],
                    name=record[1],
                    category=record[2],
                    tenant_id=record[3],
                    created_at=record[4],
                )
                for record in records
            ]

            logger.debug(f"Found {len(concepts)} concepts for document {doc_id}")
            return concepts

    async def delete_document(self, doc_id: str) -> bool:
        """
        Delete document and all its relationships.

        Args:
            doc_id: Document ID

        Returns:
            bool: True if deleted, False if not found

        Example:
            >>> deleted = await graph.delete_document("doc-123")
        """
        if not self._connected or self.driver is None:
            raise RuntimeError("GraphStore not connected. Call connect() first.")

        query = """
        MATCH (d:Document {id: $doc_id})
        DETACH DELETE d
        RETURN count(d) as deleted_count
        """

        async with self.driver.session() as session:
            result = await session.run(query, doc_id=doc_id)
            record = await result.single()

            if record and record["deleted_count"] > 0:
                logger.info(f"Deleted document {doc_id} from graph")
                return True
            else:
                logger.debug(f"Document {doc_id} not found in graph")
                return False

    async def health_check(self) -> bool:
        """
        Check if Neo4j is healthy and connected.

        Returns:
            bool: True if healthy, False otherwise
        """
        if not self._connected or self.driver is None:
            return False

        try:
            async with self.driver.session() as session:
                result = await session.run("RETURN 1 as health")
                record = await result.single()
                return record is not None and record["health"] == 1
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
