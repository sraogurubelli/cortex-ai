"""
Document & RAG API Routes

Exposes document ingestion, listing, deletion, and semantic search
via the existing cortex.rag library components.
"""

import logging
import os
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from cortex.api.middleware.auth import require_authentication
from cortex.platform.auth import Permission, require_permission
from cortex.platform.database import Principal, get_db
from cortex.platform.database.repositories import ProjectRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["documents"])


# ---------------------------------------------------------------------------
# Singleton RAG service holder – lazily initialized on first request
# ---------------------------------------------------------------------------

_rag_services: dict[str, Any] = {}


async def _get_rag_services():
    """Return (DocumentManager, Retriever) singletons, created on first call.

    When ``CORTEX_GRAPHRAG_ENABLED=true``, the retriever is configured with
    a GraphStore (Neo4j) and an EntityExtractor for knowledge-graph-enhanced
    retrieval.  Entity extraction runs on document upload and ``graphrag_search``
    replaces plain vector search.
    """
    if "doc_manager" not in _rag_services:
        from cortex.rag import DocumentManager, EmbeddingService, Retriever, VectorStore

        openai_key = os.getenv("OPENAI_API_KEY", "")
        qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
        redis_url = os.getenv("REDIS_URL")
        collection = os.getenv("QDRANT_COLLECTION_NAME", "cortex_documents")
        chunk_size = int(os.getenv("CHUNK_SIZE", "1000"))
        chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "200"))

        embeddings = EmbeddingService(
            openai_api_key=openai_key,
            redis_url=redis_url,
        )
        vector_store = VectorStore(url=qdrant_url, collection_name=collection)
        await vector_store.connect()

        graph_store = None
        enable_graphrag = os.getenv("CORTEX_GRAPHRAG_ENABLED", "").lower() in ("true", "1", "yes")

        if enable_graphrag:
            try:
                from cortex.rag.graph import GraphStore
                from cortex.rag.graph.entity_extractor import EntityExtractor

                graph_store = GraphStore()
                await graph_store.connect()
                _rag_services["entity_extractor"] = EntityExtractor()
                logger.info("GraphRAG enabled — Neo4j graph store connected")
            except Exception:
                logger.warning(
                    "CORTEX_GRAPHRAG_ENABLED is set but GraphStore init failed; "
                    "falling back to vector-only search",
                    exc_info=True,
                )
                graph_store = None

        _rag_services["doc_manager"] = DocumentManager(
            embeddings=embeddings,
            vector_store=vector_store,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        _rag_services["retriever"] = Retriever(
            embeddings=embeddings,
            vector_store=vector_store,
            graph_store=graph_store,
        )
        _rag_services["graphrag_enabled"] = graph_store is not None

    return _rag_services["doc_manager"], _rag_services["retriever"]


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class DocumentInfo(BaseModel):
    id: str
    project_id: str
    filename: Optional[str] = None
    content_preview: str = ""
    metadata: dict[str, Any] = {}
    created_at: Optional[datetime] = None


class DocumentList(BaseModel):
    documents: list[DocumentInfo]
    total: int


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=5000)
    top_k: int = Field(default=5, ge=1, le=50)
    score_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class SearchHit(BaseModel):
    id: str
    content: str
    score: float
    metadata: dict[str, Any] = {}


class SearchResponse(BaseModel):
    results: list[SearchHit]
    query: str
    total: int


class IngestResponse(BaseModel):
    doc_id: str
    chunks: int
    message: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/projects/{project_uid}/documents",
    response_model=IngestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    project_uid: str,
    file: UploadFile = File(...),
    principal: Principal = Depends(
        require_permission(Permission.DOCUMENT_UPLOAD, "project", "project_uid")
    ),
    session: AsyncSession = Depends(get_db),
):
    """Upload and ingest a document into the project's vector store."""
    project_repo = ProjectRepository(session)
    project = await project_repo.find_by_uid(project_uid)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    max_size_mb = int(os.getenv("MAX_DOCUMENT_SIZE_MB", "10"))
    content_bytes = await file.read()
    if len(content_bytes) > max_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {max_size_mb}MB limit",
        )

    content = content_bytes.decode("utf-8", errors="replace")
    doc_id = f"doc_{uuid.uuid4().hex[:12]}"

    doc_manager, _ = await _get_rag_services()
    num_chunks = await doc_manager.ingest_document(
        doc_id=doc_id,
        content=content,
        metadata={
            "project_uid": project_uid,
            "filename": file.filename,
            "content_type": file.content_type,
            "uploaded_by": principal.uid,
        },
        tenant_id=project_uid,
    )

    # Extract entities and store in graph when GraphRAG is enabled
    if _rag_services.get("graphrag_enabled"):
        try:
            entity_extractor = _rag_services["entity_extractor"]
            from cortex.rag.graph import GraphStore
            from cortex.rag.graph.schema import Document as GraphDocument

            graph_store: GraphStore = _rag_services["retriever"].graph_store
            extraction = await entity_extractor.extract(content[:5000])

            await graph_store.store_document(
                GraphDocument(
                    id=doc_id,
                    title=file.filename or doc_id,
                    content=content[:2000],
                    metadata={
                        "project_uid": project_uid,
                        "filename": file.filename,
                    },
                ),
                concepts=extraction.concepts,
                relationships=extraction.relationships,
            )
            logger.info("GraphRAG: extracted %d entities from %s", len(extraction.concepts), doc_id)
        except Exception:
            logger.warning("GraphRAG entity extraction failed for %s", doc_id, exc_info=True)

    return IngestResponse(
        doc_id=doc_id,
        chunks=num_chunks,
        message=f"Ingested '{file.filename}' as {num_chunks} chunk(s)",
    )


@router.get("/projects/{project_uid}/documents", response_model=DocumentList)
async def list_documents(
    project_uid: str,
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(
        require_permission(Permission.DOCUMENT_VIEW, "project", "project_uid")
    ),
    session: AsyncSession = Depends(get_db),
):
    """List documents belonging to a project."""
    project_repo = ProjectRepository(session)
    project = await project_repo.find_by_uid(project_uid)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    doc_manager, _ = await _get_rag_services()
    docs, _ = await doc_manager.list_documents(
        limit=limit,
        filter={"tenant_id": project_uid},
    )

    items = [
        DocumentInfo(
            id=d["id"],
            project_id=project_uid,
            filename=d.get("metadata", {}).get("filename"),
            content_preview=d.get("content", "")[:200],
            metadata=d.get("metadata", {}),
        )
        for d in docs
    ]

    return DocumentList(documents=items, total=len(items))


@router.delete(
    "/projects/{project_uid}/documents/{doc_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_document(
    project_uid: str,
    doc_id: str,
    principal: Principal = Depends(
        require_permission(Permission.DOCUMENT_DELETE, "project", "project_uid")
    ),
    session: AsyncSession = Depends(get_db),
):
    """Delete a document from the project's vector store."""
    project_repo = ProjectRepository(session)
    project = await project_repo.find_by_uid(project_uid)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    doc_manager, _ = await _get_rag_services()
    await doc_manager.delete_document(doc_id)
    return None


@router.post("/projects/{project_uid}/search", response_model=SearchResponse)
async def search_documents(
    project_uid: str,
    request: SearchRequest,
    principal: Principal = Depends(
        require_permission(Permission.DOCUMENT_VIEW, "project", "project_uid")
    ),
    session: AsyncSession = Depends(get_db),
):
    """Semantic search over a project's documents."""
    project_repo = ProjectRepository(session)
    project = await project_repo.find_by_uid(project_uid)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    _, retriever = await _get_rag_services()

    if _rag_services.get("graphrag_enabled"):
        results = await retriever.graphrag_search(
            query=request.query,
            top_k=request.top_k,
            tenant_id=project_uid,
        )
    else:
        results = await retriever.search(
            query=request.query,
            top_k=request.top_k,
            score_threshold=request.score_threshold,
            tenant_id=project_uid,
        )

    hits = [
        SearchHit(
            id=r.id,
            content=r.content,
            score=r.score,
            metadata=r.metadata,
        )
        for r in results
    ]

    return SearchResponse(results=hits, query=request.query, total=len(hits))
