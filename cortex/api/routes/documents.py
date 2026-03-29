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
from cortex.rag.parsers import parse_file, UnsupportedFileTypeError, FileParsingError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["documents"])


# ---------------------------------------------------------------------------
# Singleton RAG service holder – lazily initialized on first request
# ---------------------------------------------------------------------------

_rag_services: dict[str, Any] = {}


def _get_storage():
    """
    Get storage backend based on STORAGE_TYPE env var.

    Returns:
        BaseStorage instance (FilesystemStorage or S3Storage)
    """
    from cortex.platform.storage import FilesystemStorage

    storage_type = os.getenv("STORAGE_TYPE", "filesystem")

    if storage_type == "s3":
        from cortex.platform.storage import S3Storage
        return S3Storage(
            bucket_name=os.getenv("AWS_S3_BUCKET", "cortex-documents"),
            region=os.getenv("AWS_REGION", "us-east-1"),
        )
    else:
        return FilesystemStorage(base_path=os.getenv("STORAGE_BASE_PATH", "./uploads"))


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


class DocumentDetailResponse(BaseModel):
    uid: str
    filename: str
    file_url: str
    file_size: int
    file_hash: str
    mime_type: Optional[str]
    status: str
    chunk_count: int
    entity_count: int
    concept_count: int
    relationship_count: int
    embedding_status: Optional[str]
    graph_status: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime


class BatchIngestItem(BaseModel):
    doc_id: str
    filename: str
    chunk_count: int


class BatchIngestError(BaseModel):
    filename: str
    error: str


class BatchIngestResponse(BaseModel):
    success_count: int
    error_count: int
    results: list[BatchIngestItem]
    errors: Optional[list[BatchIngestError]] = None


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
        require_permission(Permission.CREATE, "project", "project_uid")
    ),
    session: AsyncSession = Depends(get_db),
):
    """
    Upload and ingest a document with unified RAG + GraphRAG processing.

    Flow:
    1. Store file (filesystem or S3)
    2. Create Document metadata record in PostgreSQL
    3. Extract text
    4. Process RAG: chunk → embed → Qdrant
    5. Process GraphRAG: extract entities/concepts → Neo4j
    6. Update Document record with processing status
    """
    from cortex.platform.database.models import Document
    from cortex.platform.database.repositories import OrganizationRepository
    from cortex.platform.storage import FilesystemStorage

    project_repo = ProjectRepository(session)
    project = await project_repo.find_by_uid(project_uid)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # Get organization for document record
    org_repo = OrganizationRepository(session)
    organization = await org_repo.find_by_id(project.organization_id)
    if not organization:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    max_size_mb = int(os.getenv("MAX_DOCUMENT_SIZE_MB", "10"))
    content_bytes = await file.read()
    if len(content_bytes) > max_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {max_size_mb}MB limit",
        )

    doc_id = f"doc_{uuid.uuid4().hex[:12]}"

    # 1. Store file using storage abstraction
    storage = _get_storage()
    storage_result = await storage.store_file(
        file_content=content_bytes,
        filename=file.filename or "unknown",
        organization_id=organization.id,
    )

    # 2. Create Document record in PostgreSQL
    document = Document(
        uid=doc_id,
        organization_id=organization.id,
        filename=file.filename or "unknown",
        file_url=storage_result.file_url,
        file_size=storage_result.file_size,
        file_hash=storage_result.file_hash,
        mime_type=file.content_type,
        status="processing",
    )
    session.add(document)
    await session.flush()

    # 3. Extract text from file
    try:
        content = await parse_file(
            content_bytes=content_bytes,
            filename=file.filename or "unknown",
            content_type=file.content_type,
        )
    except UnsupportedFileTypeError as e:
        document.status = "failed"
        document.error_message = str(e)
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(e),
        )
    except FileParsingError as e:
        document.status = "failed"
        document.error_message = f"Failed to parse file: {str(e)}"
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse file: {str(e)}",
        )

    # 4. Process RAG (Qdrant vector store)
    try:
        doc_manager, _ = await _get_rag_services()
        num_chunks = await doc_manager.ingest_document(
            doc_id=doc_id,
            content=content,
            metadata={
                "project_uid": project_uid,
                "organization_id": organization.id,
                "filename": file.filename,
                "content_type": file.content_type,
                "uploaded_by": principal.uid,
            },
            tenant_id=f"org_{organization.id}",
        )
        document.qdrant_doc_id = doc_id
        document.chunk_count = num_chunks
        document.embedding_status = "completed"
        logger.info(f"RAG processing completed: {num_chunks} chunks for {doc_id}")
    except Exception as e:
        document.embedding_status = "failed"
        document.error_message = f"RAG processing failed: {str(e)}"
        logger.error(f"RAG processing failed for {doc_id}: {e}", exc_info=True)

    # 5. Process GraphRAG (Neo4j knowledge graph)
    entity_count = 0
    concept_count = 0
    relationship_count = 0

    if _rag_services.get("graphrag_enabled"):
        try:
            entity_extractor = _rag_services["entity_extractor"]
            from cortex.rag.graph import GraphStore
            from cortex.rag.graph.schema import Document as Neo4jDocument, Concept, Entity

            graph_store: GraphStore = _rag_services["retriever"].graph_store
            embeddings = _rag_services["doc_manager"].embeddings
            tenant_id = f"org_{organization.id}"

            # Extract concepts AND entities with embeddings
            extraction = await entity_extractor.extract_with_embeddings(
                content[:15000],  # Limit for LLM context
                embedding_service=embeddings,
            )

            # Add document node to Neo4j
            await graph_store.add_document(
                doc_id=doc_id,
                content=content[:5000],  # Store preview in graph
                tenant_id=tenant_id,
            )
            document.neo4j_doc_id = doc_id

            # Add concepts to Neo4j and link to document
            for concept_data in extraction.concepts:
                concept_id = await graph_store.add_concept(
                    name=concept_data["name"],
                    category=concept_data.get("category", "general"),
                    tenant_id=tenant_id,
                )
                # Link document to concept
                await graph_store.add_relationship(
                    source_id=doc_id,
                    target_id=concept_id,
                    rel_type="MENTIONS",
                    properties={"confidence": 0.9},
                )
                concept_count += 1

            # Add entities to Neo4j and link to document
            entity_id_map = {}  # Map entity names to IDs for relationships
            for entity_data in extraction.entities:
                entity_id = await graph_store.add_entity(
                    name=entity_data["name"],
                    entity_type=entity_data.get("type", "concept"),
                    tenant_id=tenant_id,
                    properties=entity_data.get("properties", {}),
                    embedding=entity_data.get("embedding"),
                )
                entity_id_map[entity_data["name"]] = entity_id
                # Link document to entity
                await graph_store.link_document_to_entity(
                    doc_id=doc_id,
                    entity_id=entity_id,
                    tenant_id=tenant_id,
                )
                entity_count += 1

            # Add relationships between entities
            for rel_data in extraction.relationships:
                source_name = rel_data.get("source")
                target_name = rel_data.get("target")
                rel_type = rel_data.get("type", "RELATES_TO")

                # Find entity IDs (could be entity or concept)
                source_id = entity_id_map.get(source_name)
                target_id = entity_id_map.get(target_name)

                if source_id and target_id:
                    await graph_store.add_entity_relationship(
                        source_id=source_id,
                        target_id=target_id,
                        rel_type=rel_type,
                        properties=rel_data.get("properties", {}),
                    )
                    relationship_count += 1

            document.entity_count = entity_count
            document.concept_count = concept_count
            document.relationship_count = relationship_count
            document.graph_status = "completed"

            logger.info(
                f"GraphRAG processing completed: {concept_count} concepts, "
                f"{entity_count} entities, {relationship_count} relationships for {doc_id}"
            )

        except Exception as e:
            document.graph_status = "failed"
            if document.error_message:
                document.error_message += f"; GraphRAG failed: {str(e)}"
            else:
                document.error_message = f"GraphRAG processing failed: {str(e)}"
            logger.error(f"GraphRAG processing failed for {doc_id}: {e}", exc_info=True)

    # 6. Update final status
    if document.embedding_status == "completed" or document.graph_status == "completed":
        document.status = "completed"
    else:
        document.status = "failed"

    await session.commit()

    return IngestResponse(
        doc_id=doc_id,
        chunks=num_chunks,
        message=(
            f"Ingested '{file.filename}' as {num_chunks} chunk(s). "
            f"GraphRAG: {concept_count} concepts, {entity_count} entities, {relationship_count} relationships"
        ),
    )


@router.get(
    "/projects/{project_uid}/documents/{doc_id}/details",
    response_model=DocumentDetailResponse,
)
async def get_document_details(
    project_uid: str,
    doc_id: str,
    principal: Principal = Depends(
        require_permission(Permission.VIEW, "project", "project_uid")
    ),
    session: AsyncSession = Depends(get_db),
):
    """
    Get document details including processing status.

    Returns file metadata, RAG processing status, and GraphRAG statistics.
    """
    from cortex.platform.database.models import Document
    from sqlalchemy import select

    # Verify project exists
    project_repo = ProjectRepository(session)
    project = await project_repo.find_by_uid(project_uid)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # Get document
    result = await session.execute(
        select(Document)
        .where(Document.uid == doc_id)
        .where(Document.organization_id == project.organization_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    return DocumentDetailResponse(
        uid=document.uid,
        filename=document.filename,
        file_url=document.file_url,
        file_size=document.file_size,
        file_hash=document.file_hash,
        mime_type=document.mime_type,
        status=document.status,
        chunk_count=document.chunk_count,
        entity_count=document.entity_count,
        concept_count=document.concept_count,
        relationship_count=document.relationship_count,
        embedding_status=document.embedding_status,
        graph_status=document.graph_status,
        error_message=document.error_message,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


@router.post(
    "/projects/{project_uid}/documents/batch",
    response_model=BatchIngestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_documents_batch(
    project_uid: str,
    files: list[UploadFile] = File(...),
    principal: Principal = Depends(
        require_permission(Permission.CREATE, "project", "project_uid")
    ),
    session: AsyncSession = Depends(get_db),
):
    """Upload and ingest multiple documents at once (up to 10 files)."""
    project_repo = ProjectRepository(session)
    project = await project_repo.find_by_uid(project_uid)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # Validate batch size
    max_batch_size = int(os.getenv("MAX_BATCH_SIZE", "10"))
    if len(files) > max_batch_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {max_batch_size} files per batch",
        )

    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided",
        )

    max_size_mb = int(os.getenv("MAX_DOCUMENT_SIZE_MB", "10"))
    doc_manager, _ = await _get_rag_services()

    results: list[BatchIngestItem] = []
    errors: list[BatchIngestError] = []

    for file in files:
        try:
            # Validate size
            content_bytes = await file.read()
            if len(content_bytes) > max_size_mb * 1024 * 1024:
                errors.append(
                    BatchIngestError(
                        filename=file.filename or "unknown",
                        error=f"File exceeds {max_size_mb}MB limit",
                    )
                )
                continue

            # Parse file
            try:
                content = await parse_file(
                    content_bytes=content_bytes,
                    filename=file.filename or "unknown",
                    content_type=file.content_type,
                )
            except UnsupportedFileTypeError as e:
                errors.append(BatchIngestError(filename=file.filename or "unknown", error=str(e)))
                continue
            except FileParsingError as e:
                errors.append(
                    BatchIngestError(
                        filename=file.filename or "unknown",
                        error=f"Failed to parse: {str(e)}",
                    )
                )
                continue

            # Ingest document
            doc_id = f"doc_{uuid.uuid4().hex[:12]}"
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

            # Extract entities for GraphRAG if enabled
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
                    logger.info(
                        "GraphRAG: extracted %d entities from %s",
                        len(extraction.concepts),
                        doc_id,
                    )
                except Exception:
                    logger.warning(
                        "GraphRAG entity extraction failed for %s",
                        doc_id,
                        exc_info=True,
                    )

            # Success
            results.append(
                BatchIngestItem(
                    doc_id=doc_id,
                    filename=file.filename or "unknown",
                    chunk_count=num_chunks,
                )
            )

        except Exception as e:
            logger.error(f"Failed to ingest {file.filename}: {e}", exc_info=True)
            errors.append(
                BatchIngestError(
                    filename=file.filename or "unknown",
                    error=f"Unexpected error: {str(e)}",
                )
            )

    return BatchIngestResponse(
        success_count=len(results),
        error_count=len(errors),
        results=results,
        errors=errors if errors else None,
    )


@router.get("/projects/{project_uid}/documents", response_model=DocumentList)
async def list_documents(
    project_uid: str,
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(
        require_permission(Permission.VIEW, "project", "project_uid")
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
        require_permission(Permission.DELETE, "project", "project_uid")
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
        require_permission(Permission.VIEW, "project", "project_uid")
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
