"""Knowledge graph API endpoints (Neo4j-based)."""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from cortex.api.middleware.auth import require_authentication
from cortex.platform.database import Principal, get_db
from cortex.platform.database.repositories import OrganizationRepository
from cortex.rag.graph import GraphStore

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])
logger = logging.getLogger(__name__)


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
