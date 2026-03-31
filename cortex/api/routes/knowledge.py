"""Knowledge graph API endpoints (Neo4j-based)."""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Literal, Optional

from cortex.api.middleware.auth import require_authentication
from cortex.platform.database import Principal, get_db
from cortex.platform.database.repositories import OrganizationRepository
from cortex.rag.graph import GraphStore

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])
logger = logging.getLogger(__name__)


# ============================================================================
# Request / Response Models
# ============================================================================


class Citation(BaseModel):
    """Citation from a source document."""

    document_id: str = Field(..., description="Document UID")
    document_name: str = Field(..., description="Document filename")
    chunk_id: str = Field(..., description="Chunk identifier")
    content: str = Field(..., description="Cited content snippet")
    score: float = Field(..., description="Relevance score")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata (page number, etc.)")


class AskQuestionRequest(BaseModel):
    """Request to ask a question against selected documents."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="User question",
        examples=["What are the main topics discussed in these documents?"],
    )
    document_ids: list[str] = Field(
        ...,
        min_length=1,
        description="List of document UIDs to query",
    )
    retrieval_mode: Literal["vector", "graph"] = Field(
        default="graph",
        description="Retrieval mode: 'vector' for semantic search, 'graph' for hybrid GraphRAG",
    )
    max_results: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of chunks to retrieve",
    )
    max_hops: int = Field(
        default=2,
        ge=1,
        le=3,
        description="Maximum graph traversal depth (for graph mode)",
    )
    vector_weight: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Weight for vector search results (for graph mode)",
    )
    graph_weight: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Weight for graph search results (for graph mode)",
    )


class AskQuestionResponse(BaseModel):
    """Response to a question with citations and metadata."""

    answer: str = Field(..., description="Generated answer from LLM")
    citations: list[Citation] = Field(default_factory=list, description="Source citations")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    retrieval_mode: str = Field(..., description="Retrieval mode used")
    retrieval_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Retrieval metadata (timing, chunk count, etc.)",
    )
    follow_up_questions: list[str] = Field(
        default_factory=list,
        description="Suggested follow-up questions",
    )


class GraphStatsResponse(BaseModel):
    """Graph statistics for a document."""

    entity_count: int = Field(..., description="Number of entities extracted")
    concept_count: int = Field(..., description="Number of concepts extracted")
    relationship_count: int = Field(..., description="Number of relationships extracted")
    entity_types: dict[str, int] = Field(
        default_factory=dict,
        description="Count by entity type",
    )


class ProcessGraphResponse(BaseModel):
    """Response after triggering graph processing."""

    document_id: str = Field(..., description="Document UID")
    status: str = Field(..., description="Processing status")
    message: str = Field(..., description="Status message")
    stats: Optional[GraphStatsResponse] = Field(None, description="Graph stats (if completed)")


# ============================================================================
# Helper Functions
# ============================================================================


async def get_user_organization_id(
    principal: Principal,
    session: AsyncSession,
) -> int:
    """
    Get organization ID for authenticated user.

    Args:
        principal: Authenticated user
        session: Database session

    Returns:
        Organization ID

    Raises:
        HTTPException: If user has no organization
    """
    org_repo = OrganizationRepository(session)
    orgs = await org_repo.list_by_principal(principal.id)

    if not orgs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No organization found for user",
        )

    return orgs[0].id


async def get_retriever() -> tuple:
    """
    Get or create RAG retriever singleton.

    Returns:
        Tuple of (Retriever, bool) where bool indicates if GraphRAG is enabled
    """
    from cortex.rag import EmbeddingService, Retriever, VectorStore
    from cortex.rag.graph import GraphStore
    import os

    # Initialize services
    openai_key = os.getenv("OPENAI_API_KEY", "")
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    redis_url = os.getenv("REDIS_URL")
    collection = os.getenv("QDRANT_COLLECTION_NAME", "cortex_documents")

    embeddings = EmbeddingService(
        openai_api_key=openai_key,
        redis_url=redis_url,
    )
    await embeddings.connect()

    vector_store = VectorStore(url=qdrant_url, collection_name=collection)
    await vector_store.connect()

    # Try to enable GraphRAG
    graph_store = None
    enable_graphrag = os.getenv("CORTEX_GRAPHRAG_ENABLED", "").lower() in ("true", "1", "yes")

    if enable_graphrag:
        try:
            graph_store = GraphStore()
            await graph_store.connect()
            logger.info("GraphRAG enabled for Q&A endpoint")
        except Exception:
            logger.warning(
                "GraphRAG enabled but connection failed; falling back to vector-only search",
                exc_info=True,
            )
            graph_store = None

    retriever = Retriever(
        embeddings=embeddings,
        vector_store=vector_store,
        graph_store=graph_store,
    )

    return retriever, graph_store is not None


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/entities")
async def list_entities(
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    search: Optional[str] = Query(None, description="Search by entity name"),
    limit: int = Query(100, ge=1, le=1000, description="Max entities to return"),
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    """
    List entities in user's organization (from Neo4j).

    Args:
        entity_type: Optional filter by entity type (person, company, etc.)
        search: Optional search query for entity name
        limit: Maximum entities to return (default: 100)
        principal: Authenticated user
        session: Database session

    Returns:
        List of entities with metadata
    """
    # Get organization ID
    organization_id = await get_user_organization_id(principal, session)
    tenant_id = f"org_{organization_id}"

    # Connect to Neo4j
    graph = GraphStore()
    await graph.connect()

    try:
        # Build Cypher query
        where_clauses = ["e.tenant_id = $tenant_id"]
        params = {"tenant_id": tenant_id, "limit": limit}

        if entity_type:
            where_clauses.append("e.type = $entity_type")
            params["entity_type"] = entity_type.lower()

        if search:
            where_clauses.append("e.name CONTAINS $search")
            params["search"] = search

        where_str = " AND ".join(where_clauses)

        query = f"""
        MATCH (e:Entity)
        WHERE {where_str}
        RETURN e.id as id, e.name as name, e.type as type,
               e.properties as properties, e.created_at as created_at
        ORDER BY e.name
        LIMIT $limit
        """

        # Execute query
        async with graph.driver.session() as neo4j_session:
            result = await neo4j_session.run(query, **params)
            records = await result.values()

            entities = [
                {
                    "id": record[0],
                    "name": record[1],
                    "type": record[2],
                    "properties": record[3] or {},
                    "created_at": record[4],
                }
                for record in records
            ]

            return {
                "entities": entities,
                "total": len(entities),
                "limit": limit,
            }

    finally:
        await graph.disconnect()


@router.get("/entities/{entity_id}")
async def get_entity(
    entity_id: str,
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    """
    Get entity with all relationships (from Neo4j).

    Args:
        entity_id: Entity ID
        principal: Authenticated user
        session: Database session

    Returns:
        Entity details with relationships
    """
    # Get organization ID
    organization_id = await get_user_organization_id(principal, session)
    tenant_id = f"org_{organization_id}"

    # Connect to Neo4j
    graph = GraphStore()
    await graph.connect()

    try:
        # Get entity
        async with graph.driver.session() as neo4j_session:
            entity_query = """
            MATCH (e:Entity {id: $entity_id, tenant_id: $tenant_id})
            RETURN e.id as id, e.name as name, e.type as type,
                   e.properties as properties, e.created_at as created_at
            """
            result = await neo4j_session.run(
                entity_query, entity_id=entity_id, tenant_id=tenant_id
            )
            record = await result.single()

            if not record:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Entity not found",
                )

            entity = {
                "id": record["id"],
                "name": record["name"],
                "type": record["type"],
                "properties": record["properties"] or {},
                "created_at": record["created_at"],
            }

            # Get outgoing relationships
            outgoing_query = """
            MATCH (source:Entity {id: $entity_id, tenant_id: $tenant_id})-[r]->(target)
            RETURN target.id as target_id, target.name as target_name,
                   target.type as target_type, type(r) as rel_type,
                   r.properties as properties
            """
            result = await neo4j_session.run(
                outgoing_query, entity_id=entity_id, tenant_id=tenant_id
            )
            outgoing_records = await result.values()

            outgoing = [
                {
                    "target_id": rec[0],
                    "target_name": rec[1],
                    "target_type": rec[2],
                    "relationship_type": rec[3],
                    "properties": rec[4] or {},
                }
                for rec in outgoing_records
            ]

            # Get incoming relationships
            incoming_query = """
            MATCH (source)-[r]->(target:Entity {id: $entity_id, tenant_id: $tenant_id})
            RETURN source.id as source_id, source.name as source_name,
                   source.type as source_type, type(r) as rel_type,
                   r.properties as properties
            """
            result = await neo4j_session.run(
                incoming_query, entity_id=entity_id, tenant_id=tenant_id
            )
            incoming_records = await result.values()

            incoming = [
                {
                    "source_id": rec[0],
                    "source_name": rec[1],
                    "source_type": rec[2],
                    "relationship_type": rec[3],
                    "properties": rec[4] or {},
                }
                for rec in incoming_records
            ]

            return {
                **entity,
                "relationships": {
                    "outgoing": outgoing,
                    "incoming": incoming,
                },
            }

    finally:
        await graph.disconnect()


@router.get("/graph")
async def get_graph(
    limit: int = Query(500, ge=1, le=2000, description="Max nodes to return"),
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    """
    Get full graph data for visualization (nodes + edges from Neo4j).

    Args:
        limit: Maximum number of nodes to return (default: 500)
        principal: Authenticated user
        session: Database session

    Returns:
        Graph data with nodes and edges
    """
    # Get organization ID
    organization_id = await get_user_organization_id(principal, session)
    tenant_id = f"org_{organization_id}"

    # Connect to Neo4j
    graph = GraphStore()
    await graph.connect()

    try:
        async with graph.driver.session() as neo4j_session:
            # Get nodes (entities + concepts)
            nodes_query = """
            MATCH (n)
            WHERE n.tenant_id = $tenant_id
              AND (n:Entity OR n:Concept)
            RETURN n.id as id, n.name as name,
                   CASE
                     WHEN n:Entity THEN n.type
                     WHEN n:Concept THEN n.category
                     ELSE 'unknown'
                   END as type,
                   labels(n) as labels
            ORDER BY n.name
            LIMIT $limit
            """
            result = await neo4j_session.run(nodes_query, tenant_id=tenant_id, limit=limit)
            node_records = await result.values()

            nodes = [
                {
                    "id": rec[0],
                    "label": rec[1],
                    "type": rec[2],
                    "node_type": "entity" if "Entity" in rec[3] else "concept",
                }
                for rec in node_records
            ]

            # Get edges (relationships)
            edges_query = """
            MATCH (source)-[r]->(target)
            WHERE source.tenant_id = $tenant_id
              AND target.tenant_id = $tenant_id
            RETURN source.id as source_id, target.id as target_id,
                   type(r) as rel_type
            LIMIT $limit
            """
            result = await neo4j_session.run(edges_query, tenant_id=tenant_id, limit=limit)
            edge_records = await result.values()

            edges = [
                {
                    "source": rec[0],
                    "target": rec[1],
                    "label": rec[2],
                }
                for rec in edge_records
            ]

            return {
                "nodes": nodes,
                "edges": edges,
                "stats": {
                    "total_nodes": len(nodes),
                    "total_edges": len(edges),
                    "limited": len(nodes) >= limit,
                },
            }

    finally:
        await graph.disconnect()


@router.get("/concepts")
async def list_concepts(
    category: Optional[str] = Query(None, description="Filter by concept category"),
    search: Optional[str] = Query(None, description="Search by concept name"),
    limit: int = Query(100, ge=1, le=1000, description="Max concepts to return"),
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    """
    List concepts in user's organization (from Neo4j).

    Args:
        category: Optional filter by concept category
        search: Optional search query for concept name
        limit: Maximum concepts to return (default: 100)
        principal: Authenticated user
        session: Database session

    Returns:
        List of concepts with metadata
    """
    # Get organization ID
    organization_id = await get_user_organization_id(principal, session)
    tenant_id = f"org_{organization_id}"

    # Connect to Neo4j
    graph = GraphStore()
    await graph.connect()

    try:
        # Build Cypher query
        where_clauses = ["c.tenant_id = $tenant_id"]
        params = {"tenant_id": tenant_id, "limit": limit}

        if category:
            where_clauses.append("c.category = $category")
            params["category"] = category.lower()

        if search:
            where_clauses.append("c.name CONTAINS $search")
            params["search"] = search

        where_str = " AND ".join(where_clauses)

        query = f"""
        MATCH (c:Concept)
        WHERE {where_str}
        RETURN c.id as id, c.name as name, c.category as category,
               c.created_at as created_at
        ORDER BY c.name
        LIMIT $limit
        """

        # Execute query
        async with graph.driver.session() as neo4j_session:
            result = await neo4j_session.run(query, **params)
            records = await result.values()

            concepts = [
                {
                    "id": record[0],
                    "name": record[1],
                    "category": record[2],
                    "created_at": record[3],
                }
                for record in records
            ]

            return {
                "concepts": concepts,
                "total": len(concepts),
                "limit": limit,
            }

    finally:
        await graph.disconnect()


@router.post("/ask", response_model=AskQuestionResponse)
async def ask_question(
    request: AskQuestionRequest,
    principal: Principal = Depends(require_authentication),
    session: AsyncSession = Depends(get_db),
):
    """
    Ask a question against selected documents using hybrid retrieval.

    Args:
        request: Question + document IDs + retrieval settings
        principal: Authenticated user
        session: Database session

    Returns:
        Answer with citations, sources, and retrieval metadata

    Raises:
        HTTPException: 400 for invalid input, 404 if documents not found, 500 for server errors
    """
    import os
    import time
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage

    # Get organization ID for tenant filtering
    organization_id = await get_user_organization_id(principal, session)
    tenant_id = f"org_{organization_id}"

    # Validate documents exist and belong to organization
    from cortex.platform.database.repositories import DocumentRepository
    doc_repo = DocumentRepository(session)

    documents = []
    for doc_id in request.document_ids:
        doc = await doc_repo.find_by_uid(doc_id)
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {doc_id} not found",
            )
        if doc.organization_id != organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Document {doc_id} does not belong to your organization",
            )
        documents.append(doc)

    try:
        # Get retriever
        retriever, graphrag_enabled = await get_retriever()

        start_time = time.time()

        # Perform retrieval based on mode
        if request.retrieval_mode == "graph" and graphrag_enabled:
            # Hybrid GraphRAG search
            results = await retriever.graphrag_search(
                query=request.question,
                top_k=request.max_results,
                vector_weight=request.vector_weight,
                graph_weight=request.graph_weight,
                max_hops=request.max_hops,
                tenant_id=tenant_id,
            )
            retrieval_mode_used = "graph"
        else:
            # Fall back to vector search
            results = await retriever.search(
                query=request.question,
                top_k=request.max_results,
                filter={"tenant_id": tenant_id},
            )
            retrieval_mode_used = "vector"

        retrieval_time = (time.time() - start_time) * 1000  # ms

        # Filter results to only include requested documents
        doc_ids_set = set(request.document_ids)
        filtered_results = [
            r for r in results
            if r.metadata.get("doc_id") in doc_ids_set or r.metadata.get("document_id") in doc_ids_set
        ]

        if not filtered_results:
            # No relevant chunks found
            return AskQuestionResponse(
                answer="I couldn't find relevant information in the selected documents to answer your question.",
                citations=[],
                confidence=0.0,
                retrieval_mode=retrieval_mode_used,
                retrieval_metadata={
                    "retrieval_time_ms": retrieval_time,
                    "chunks_retrieved": 0,
                    "chunks_filtered": 0,
                },
                follow_up_questions=[],
            )

        # Build context from retrieved chunks
        context_parts = []
        citations_list = []

        for idx, result in enumerate(filtered_results[:request.max_results], 1):
            # Add to context
            context_parts.append(f"[{idx}] {result.content}")

            # Create citation
            doc_id = result.metadata.get("doc_id") or result.metadata.get("document_id", "unknown")
            doc_name = result.metadata.get("filename", "unknown")
            chunk_id = result.id

            citations_list.append(
                Citation(
                    document_id=doc_id,
                    document_name=doc_name,
                    chunk_id=chunk_id,
                    content=result.content[:500],  # Truncate for citation display
                    score=result.score,
                    metadata={
                        "page": result.metadata.get("page"),
                        "section": result.metadata.get("section"),
                        "source": result.metadata.get("source", retrieval_mode_used),
                    },
                )
            )

        context_text = "\n\n".join(context_parts)

        # Create LLM prompt
        system_prompt = """You are a helpful AI assistant that answers questions based on the provided document context.

When answering:
1. Only use information from the provided context
2. If the answer is not in the context, say so clearly
3. Cite sources by referencing the [number] markers in the context
4. Be concise but complete
5. If multiple sources support your answer, mention them all

Respond in a clear, professional manner."""

        user_prompt = f"""Context from documents:

{context_text}

Question: {request.question}

Please provide a comprehensive answer based solely on the context above."""

        # Call LLM
        llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o"),
            temperature=0.3,  # Lower temperature for factual Q&A
            api_key=os.getenv("OPENAI_API_KEY"),
        )

        llm_start = time.time()
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        llm_time = (time.time() - llm_start) * 1000  # ms

        answer_text = response.content

        # Calculate confidence based on average retrieval scores
        avg_score = sum(r.score for r in filtered_results) / len(filtered_results)
        confidence = min(avg_score, 1.0)  # Cap at 1.0

        # Generate follow-up questions (simple approach)
        follow_ups = []
        if confidence > 0.5:
            # Only suggest follow-ups if we have decent confidence
            follow_ups = [
                "Can you provide more details about this?",
                "What are the key implications?",
                "How does this compare to other approaches?",
            ]

        return AskQuestionResponse(
            answer=answer_text,
            citations=citations_list,
            confidence=confidence,
            retrieval_mode=retrieval_mode_used,
            retrieval_metadata={
                "retrieval_time_ms": round(retrieval_time, 2),
                "llm_time_ms": round(llm_time, 2),
                "total_time_ms": round(retrieval_time + llm_time, 2),
                "chunks_retrieved": len(results),
                "chunks_used": len(filtered_results),
                "avg_retrieval_score": round(avg_score, 3),
            },
            follow_up_questions=follow_ups,
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(
            f"Knowledge Q&A failed: {e}",
            exc_info=True,
            extra={
                "question": request.question,
                "document_ids": request.document_ids,
                "retrieval_mode": request.retrieval_mode,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process question. Please try again later.",
        )
