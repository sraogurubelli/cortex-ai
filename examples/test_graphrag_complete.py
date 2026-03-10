"""
GraphRAG Complete Demo - All Phases (3, 4, 5)

Demonstrates the full GraphRAG system:
- Phase 3: Graph search (concept-based retrieval)
- Phase 4: Hybrid retrieval (vector + graph with RRF fusion)
- Phase 5: Production features (comparison, performance)

Requirements:
- Docker running with Neo4j, Qdrant, Redis
- OpenAI API key

Setup:
    docker-compose up -d neo4j qdrant redis

Run:
    OPENAI_API_KEY=sk-... python examples/test_graphrag_complete.py
"""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cortex.rag import (
    EmbeddingService,
    VectorStore,
    DocumentManager,
    Retriever,
    GraphStore,
    EntityExtractor,
)
from cortex.orchestration import ModelConfig


async def demo_graphrag_complete():
    """Demonstrate complete GraphRAG system."""

    print("=" * 80)
    print("GraphRAG Complete Demo - All Phases")
    print("=" * 80)
    print()

    # Initialize components
    print("📦 Initializing components...")

    embeddings = EmbeddingService(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        redis_url=os.getenv("CORTEX_REDIS_URL", "redis://localhost:6379"),
    )
    await embeddings.connect()
    print("✅ Embeddings ready")

    vector_store = VectorStore(
        url=os.getenv("CORTEX_QDRANT_URL", "http://localhost:6333"),
        collection_name="graphrag_complete_demo",
    )
    await vector_store.connect()
    await vector_store.create_collection()
    print("✅ Vector store ready")

    graph_store = GraphStore(
        url=os.getenv("CORTEX_NEO4J_URL", "bolt://localhost:7687"),
        password=os.getenv("CORTEX_NEO4J_PASSWORD", "cortex_neo4j_password"),
    )
    await graph_store.connect()
    await graph_store.create_constraints()
    print("✅ Graph store ready")

    extractor = EntityExtractor(ModelConfig(model="gpt-4o-mini", temperature=0.0))
    print("✅ Entity extractor ready")

    doc_manager = DocumentManager(
        embeddings=embeddings,
        vector_store=vector_store,
        graph_store=graph_store,
        entity_extractor=extractor,
    )

    # Retriever with GraphRAG support
    retriever = Retriever(
        embeddings=embeddings,
        vector_store=vector_store,
        graph_store=graph_store,
    )
    print("✅ Retriever ready (with GraphRAG)")
    print()

    # =========================================================================
    # Ingest Documents
    # =========================================================================
    print("=" * 80)
    print("📄 Ingesting Documents with Entity Extraction")
    print("=" * 80)
    print()

    documents = [
        {
            "doc_id": "langraph-intro",
            "content": """LangGraph is a framework for building stateful, multi-actor
            applications with LLMs. It extends LangChain with graph-based orchestration.
            LangGraph uses Python and supports complex agent workflows with cycles and
            conditional logic. Many developers use LangGraph with Claude or GPT-4 for
            production AI applications.""",
            "metadata": {"source": "docs", "category": "framework"},
        },
        {
            "doc_id": "langgraph-features",
            "content": """LangGraph provides state management for multi-turn conversations,
            allowing agents to maintain context across interactions. It integrates with
            LangChain tools and supports both synchronous and asynchronous execution.
            LangGraph is ideal for building chatbots, autonomous agents, and RAG systems.""",
            "metadata": {"source": "docs", "category": "features"},
        },
        {
            "doc_id": "python-ml",
            "content": """Python is the dominant language for machine learning and AI
            development. Popular frameworks include PyTorch for deep learning, TensorFlow
            for production ML, and scikit-learn for traditional ML. Python's ecosystem
            includes tools like Pandas for data manipulation and NumPy for numerical computing.""",
            "metadata": {"source": "docs", "category": "language"},
        },
        {
            "doc_id": "claude-api",
            "content": """Claude is Anthropic's family of large language models known for
            their helpfulness, harmlessness, and honesty. Claude offers models like
            Claude 4 (Opus, Sonnet, Haiku) with different capability-cost tradeoffs.
            Developers integrate Claude via the Anthropic API using Python or JavaScript SDKs.""",
            "metadata": {"source": "docs", "category": "llm"},
        },
        {
            "doc_id": "gpt4-overview",
            "content": """GPT-4 is OpenAI's most capable language model, excelling at
            complex reasoning, code generation, and creative writing. GPT-4 powers
            applications like ChatGPT and GitHub Copilot. Developers access GPT-4 through
            the OpenAI API with support for function calling and vision capabilities.""",
            "metadata": {"source": "docs", "category": "llm"},
        },
    ]

    for i, doc in enumerate(documents, 1):
        print(f"📝 Ingesting document {i}/{len(documents)}: {doc['doc_id']}")
        start = time.time()
        await doc_manager.ingest_document(
            doc_id=doc["doc_id"],
            content=doc["content"],
            metadata=doc["metadata"],
            tenant_id="demo",
            extract_entities=True,
        )
        elapsed = time.time() - start
        print(f"   ✅ Completed in {elapsed:.2f}s")
        print()

    print("=" * 80)
    print()

    # =========================================================================
    # Phase 3: Graph Search
    # =========================================================================
    print("=" * 80)
    print("🔍 Phase 3: Graph Search (Concept-Based Retrieval)")
    print("=" * 80)
    print()

    test_concepts = ["LangGraph", "Python", "Claude"]

    for concept in test_concepts:
        print(f"Searching for concept: '{concept}'")
        print("-" * 60)

        start = time.time()
        results = await retriever.graph_search(
            concept_name=concept,
            max_hops=2,
            tenant_id="demo",
        )
        elapsed = time.time() - start

        print(f"Found {len(results)} documents in {elapsed:.3f}s")
        for i, result in enumerate(results[:3], 1):
            print(f"\n  {i}. {result.id} (score: {result.score:.3f})")
            print(f"     {result.content[:100]}...")
            if "concept_count" in result.metadata:
                print(f"     Related concepts: {result.metadata['concept_count']}")
        print()

    # =========================================================================
    # Phase 4: Hybrid GraphRAG Search (Vector + Graph)
    # =========================================================================
    print("=" * 80)
    print("🔀 Phase 4: Hybrid GraphRAG Search (Vector + Graph with RRF)")
    print("=" * 80)
    print()

    test_queries = [
        "What frameworks are used for building AI agents?",
        "Which programming languages are best for machine learning?",
        "Compare Claude and GPT-4 for production applications",
    ]

    for query in test_queries:
        print(f"Query: '{query}'")
        print("-" * 60)

        # Compare three approaches
        print("\n1️⃣  Vector Search Only:")
        start = time.time()
        vector_results = await retriever.search(query, top_k=3, tenant_id="demo")
        vector_time = time.time() - start
        print(f"   Results: {len(vector_results)} in {vector_time:.3f}s")
        for i, r in enumerate(vector_results, 1):
            print(f"   {i}. {r.id} (score: {r.score:.3f})")

        print("\n2️⃣  GraphRAG Search (Vector + Graph):")
        start = time.time()
        graphrag_results = await retriever.graphrag_search(
            query=query,
            top_k=3,
            vector_weight=0.7,
            graph_weight=0.3,
            tenant_id="demo",
        )
        graphrag_time = time.time() - start
        print(f"   Results: {len(graphrag_results)} in {graphrag_time:.3f}s")
        for i, r in enumerate(graphrag_results, 1):
            meta = f" (V:{r.metadata.get('vector_rank', '-')} G:{r.metadata.get('graph_rank', '-')})" if 'rrf_score' in r.metadata else ""
            print(f"   {i}. {r.id} (rrf: {r.score:.3f}){meta}")

        print("\n3️⃣  Comparison:")
        vector_ids = {r.id for r in vector_results}
        graphrag_ids = {r.id for r in graphrag_results}

        only_vector = vector_ids - graphrag_ids
        only_graphrag = graphrag_ids - vector_ids
        both = vector_ids & graphrag_ids

        print(f"   - Same in both: {len(both)}")
        print(f"   - Only in vector: {len(only_vector)} {list(only_vector)}")
        print(f"   - Only in GraphRAG: {len(only_graphrag)} {list(only_graphrag)}")
        print(f"   - Speed comparison: Vector {vector_time:.3f}s vs GraphRAG {graphrag_time:.3f}s")
        print()

    # =========================================================================
    # Phase 5: Production Features
    # =========================================================================
    print("=" * 80)
    print("🚀 Phase 5: Production Features & Analysis")
    print("=" * 80)
    print()

    print("📊 Knowledge Graph Statistics:")
    print("-" * 60)

    # Get graph stats
    query_stats = """
    MATCH (d:Document {tenant_id: $tenant_id})
    WITH COUNT(d) as doc_count
    MATCH (c:Concept {tenant_id: $tenant_id})
    WITH doc_count, COUNT(c) as concept_count
    MATCH (d:Document {tenant_id: $tenant_id})-[m:MENTIONS]->(c:Concept)
    WITH doc_count, concept_count, COUNT(m) as mentions_count
    MATCH (c1:Concept {tenant_id: $tenant_id})-[r:RELATES_TO]->(c2:Concept)
    RETURN doc_count, concept_count, mentions_count, COUNT(r) as relationships_count
    """

    if graph_store.driver:
        async with graph_store.driver.session() as session:
            result = await session.run(query_stats, tenant_id="demo")
            record = await result.single()
            if record:
                print(f"Documents:      {record['doc_count']}")
                print(f"Concepts:       {record['concept_count']}")
                print(f"MENTIONS:       {record['mentions_count']}")
                print(f"RELATES_TO:     {record['relationships_count']}")
    print()

    print("🔗 Most Connected Concepts:")
    print("-" * 60)

    query_top_concepts = """
    MATCH (c:Concept {tenant_id: $tenant_id})<-[m:MENTIONS]-(d:Document)
    WITH c, COUNT(DISTINCT d) as doc_count
    MATCH (c)-[r:RELATES_TO]-()
    WITH c, doc_count, COUNT(r) as rel_count
    RETURN c.name as concept,
           c.category as category,
           doc_count,
           rel_count,
           doc_count + rel_count as total_connections
    ORDER BY total_connections DESC
    LIMIT 5
    """

    if graph_store.driver:
        async with graph_store.driver.session() as session:
            result = await session.run(query_top_concepts, tenant_id="demo")
            records = await result.values()
            for concept, category, doc_count, rel_count, total in records:
                print(f"  - {concept:15} ({category:10}): {doc_count} docs, {rel_count} relationships")
    print()

    print("⚡ Performance Analysis:")
    print("-" * 60)

    # Run performance comparison
    test_query = "What is LangGraph used for?"

    # Vector only
    start = time.time()
    v_results = await retriever.search(test_query, top_k=5, tenant_id="demo")
    vector_only_time = time.time() - start

    # GraphRAG
    start = time.time()
    gr_results = await retriever.graphrag_search(test_query, top_k=5, tenant_id="demo")
    graphrag_time = time.time() - start

    print(f"Query: '{test_query}'")
    print(f"  Vector only:  {vector_only_time:.3f}s ({len(v_results)} results)")
    print(f"  GraphRAG:     {graphrag_time:.3f}s ({len(gr_results)} results)")
    print(f"  Overhead:     {(graphrag_time - vector_only_time):.3f}s ({(graphrag_time/vector_only_time - 1)*100:.1f}% slower)")
    print()

    print("=" * 80)
    print("🎉 GraphRAG Complete Demo Finished!")
    print("=" * 80)
    print()

    print("✨ What's been demonstrated:")
    print("  ✅ Phase 1-2: Entity extraction and graph building")
    print("  ✅ Phase 3: Graph search (concept-based retrieval)")
    print("  ✅ Phase 4: Hybrid GraphRAG (vector + graph with RRF)")
    print("  ✅ Phase 5: Production features (stats, performance)")
    print()

    print("🌐 Explore the graph in Neo4j Browser:")
    print("  URL: http://localhost:7474")
    print("  User: neo4j / Password: cortex_neo4j_password")
    print()
    print("  Try these Cypher queries:")
    print("  1. MATCH (n) RETURN n LIMIT 25")
    print("  2. MATCH (d:Document)-[:MENTIONS]->(c:Concept) RETURN d, c")
    print("  3. MATCH (c1:Concept)-[:RELATES_TO]->(c2:Concept) RETURN c1, c2")
    print()

    # Cleanup
    await embeddings.disconnect()
    await vector_store.disconnect()
    await graph_store.disconnect()


if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY environment variable not set")
        print("Set it with: export OPENAI_API_KEY=sk-...")
        sys.exit(1)

    asyncio.run(demo_graphrag_complete())
