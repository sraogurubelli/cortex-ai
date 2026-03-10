"""
Test script for RAG (Retrieval-Augmented Generation) module.

Demonstrates:
1. Embedding service with Redis caching
2. Vector store with Qdrant
3. Document ingestion and management
4. Semantic search
5. Hybrid search (vector + keyword)
6. Integration with Agent for RAG
7. Multi-tenancy support

Prerequisites:
    # Install dependencies
    pip install openai qdrant-client redis

    # Start Qdrant
    docker run -d --name qdrant -p 6333:6333 qdrant/qdrant

    # Start Redis (optional, for caching)
    docker run -d --name redis -p 6379:6379 redis:7

Run with:
    # With Redis caching
    CORTEX_OPENAI_API_KEY=sk-... python examples/test_rag.py

    # Without Redis (caching disabled)
    CORTEX_OPENAI_API_KEY=sk-... CORTEX_REDIS_URL="" python examples/test_rag.py

    # With Agent integration
    CORTEX_OPENAI_API_KEY=sk-... python examples/test_rag.py
"""

import asyncio
import os

# Check for required environment variables
OPENAI_API_KEY = os.getenv("CORTEX_OPENAI_API_KEY", "")
if not OPENAI_API_KEY:
    print("⚠️  CORTEX_OPENAI_API_KEY not set")
    print("Set with: export CORTEX_OPENAI_API_KEY=sk-...")
    exit(1)

# Import RAG components
try:
    from cortex.rag import DocumentManager, EmbeddingService, Retriever, VectorStore

    RAG_AVAILABLE = True
except ImportError as e:
    RAG_AVAILABLE = False
    print(f"⚠️  RAG module not available: {e}")
    print("Install dependencies: pip install openai qdrant-client redis")

# Import Agent for integration demo
try:
    from cortex.orchestration import Agent, ModelConfig

    AGENT_AVAILABLE = True
except ImportError:
    AGENT_AVAILABLE = False
    print("⚠️  Agent not available - skipping integration demo")


async def demo_embedding_service():
    """Demonstrate embedding service with caching."""
    if not RAG_AVAILABLE:
        return

    print("=" * 70)
    print("Demo 1: Embedding Service with Caching")
    print("=" * 70)

    # Initialize embedding service
    print("\n📊 Initializing embedding service...")
    embeddings = EmbeddingService(
        openai_api_key=OPENAI_API_KEY,
        redis_url=os.getenv("CORTEX_REDIS_URL", "redis://localhost:6379"),
    )
    await embeddings.connect()

    # Generate single embedding
    print("\n📝 Generating embedding for 'Python is a programming language'...")
    embedding1 = await embeddings.generate_embedding("Python is a programming language")
    print(f"  Embedding dimension: {len(embedding1)}")
    print(f"  First 5 values: {embedding1[:5]}")

    # Generate again (should hit cache)
    print("\n📝 Generating same embedding again (cache hit)...")
    embedding2 = await embeddings.generate_embedding("Python is a programming language")
    print(f"  Embeddings match: {embedding1 == embedding2}")

    # Batch generation
    print("\n📝 Batch embedding generation...")
    texts = [
        "Python is great for data science",
        "JavaScript is used for web development",
        "Rust is a systems programming language",
    ]
    embeddings_list = await embeddings.generate_embeddings(texts)
    print(f"  Generated {len(embeddings_list)} embeddings")

    # Cache stats
    print("\n📊 Cache statistics:")
    stats = await embeddings.get_cache_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    await embeddings.disconnect()
    print("\n✓ Embedding service demo complete!")


async def demo_vector_store():
    """Demonstrate vector store operations."""
    if not RAG_AVAILABLE:
        return

    print("\n" + "=" * 70)
    print("Demo 2: Vector Store Operations")
    print("=" * 70)

    # Initialize
    print("\n📊 Initializing vector store...")
    vector_store = VectorStore(
        url=os.getenv("CORTEX_QDRANT_URL", "http://localhost:6333"),
        collection_name="test_documents",
        vector_size=1536,
    )
    await vector_store.connect()

    # Create collection
    print("\n📦 Creating collection...")
    if await vector_store.collection_exists():
        print("  Collection already exists - deleting...")
        await vector_store.delete_collection()
    await vector_store.create_collection()

    # Get embeddings
    embeddings = EmbeddingService(openai_api_key=OPENAI_API_KEY)
    await embeddings.connect()

    # Ingest documents
    print("\n📝 Ingesting documents...")
    docs = [
        {"id": "doc-1", "text": "Python is a high-level programming language"},
        {"id": "doc-2", "text": "JavaScript is used for web development"},
        {"id": "doc-3", "text": "Machine learning uses Python extensively"},
    ]

    for doc in docs:
        embedding = await embeddings.generate_embedding(doc["text"])
        await vector_store.ingest(
            doc_id=doc["id"],
            vector=embedding,
            payload={"content": doc["text"], "source": "demo"},
        )
    print(f"  Ingested {len(docs)} documents")

    # Search
    print("\n🔍 Searching for 'Python programming'...")
    query_embedding = await embeddings.generate_embedding("Python programming")
    results = await vector_store.search(
        query_vector=query_embedding,
        top_k=2,
    )
    print(f"  Found {len(results)} results:")
    for result in results:
        print(f"    {result['id']}: {result['score']:.3f} - {result['payload']['content']}")

    # Count
    count = await vector_store.count()
    print(f"\n📊 Total documents: {count}")

    # Cleanup
    await embeddings.disconnect()
    await vector_store.disconnect()
    print("\n✓ Vector store demo complete!")


async def demo_document_manager():
    """Demonstrate document management."""
    if not RAG_AVAILABLE:
        return

    print("\n" + "=" * 70)
    print("Demo 3: Document Manager")
    print("=" * 70)

    # Initialize
    print("\n📊 Initializing components...")
    embeddings = EmbeddingService(openai_api_key=OPENAI_API_KEY)
    await embeddings.connect()

    vector_store = VectorStore(
        url=os.getenv("CORTEX_QDRANT_URL", "http://localhost:6333"),
        collection_name="test_documents",
    )
    await vector_store.connect()

    if not await vector_store.collection_exists():
        await vector_store.create_collection()

    doc_manager = DocumentManager(
        embeddings=embeddings,
        vector_store=vector_store,
        chunk_size=500,  # Small chunks for testing
    )

    # Ingest single document
    print("\n📝 Ingesting single document...")
    chunks = await doc_manager.ingest_document(
        doc_id="python-intro",
        content=(
            "Python is a high-level, interpreted programming language. "
            "It was created by Guido van Rossum and first released in 1991. "
            "Python's design philosophy emphasizes code readability with its "
            "use of significant indentation. It supports multiple programming "
            "paradigms including structured, object-oriented, and functional programming."
        ),
        metadata={"source": "wikipedia", "category": "programming"},
    )
    print(f"  Ingested {chunks} chunks")

    # Batch ingest
    print("\n📝 Batch ingesting documents...")
    batch_docs = [
        {
            "doc_id": "javascript-intro",
            "content": "JavaScript is a programming language used primarily for web development.",
            "metadata": {"source": "wikipedia", "category": "programming"},
        },
        {
            "doc_id": "rust-intro",
            "content": "Rust is a systems programming language focused on safety and performance.",
            "metadata": {"source": "wikipedia", "category": "programming"},
        },
    ]
    total_chunks = await doc_manager.ingest_batch(batch_docs)
    print(f"  Ingested {total_chunks} total chunks from {len(batch_docs)} documents")

    # List documents
    print("\n📋 Listing documents...")
    docs, next_offset = await doc_manager.list_documents(limit=10)
    print(f"  Found {len(docs)} documents:")
    for doc in docs:
        content_preview = doc["content"][:80] + "..." if len(doc["content"]) > 80 else doc["content"]
        print(f"    {doc['id']}: {content_preview}")

    # Count
    count = await doc_manager.count_documents()
    print(f"\n📊 Total documents: {count}")

    # Update document
    print("\n✏️  Updating document...")
    await doc_manager.update_document(
        doc_id="python-intro",
        metadata={"updated": True, "source": "wikipedia"},
    )
    print("  Document updated")

    # Cleanup
    await embeddings.disconnect()
    await vector_store.disconnect()
    print("\n✓ Document manager demo complete!")


async def demo_retriever():
    """Demonstrate semantic search and retrieval."""
    if not RAG_AVAILABLE:
        return

    print("\n" + "=" * 70)
    print("Demo 4: Retriever - Semantic Search")
    print("=" * 70)

    # Initialize
    print("\n📊 Initializing components...")
    embeddings = EmbeddingService(openai_api_key=OPENAI_API_KEY)
    await embeddings.connect()

    vector_store = VectorStore(
        url=os.getenv("CORTEX_QDRANT_URL", "http://localhost:6333"),
        collection_name="test_documents",
    )
    await vector_store.connect()

    retriever = Retriever(
        embeddings=embeddings,
        vector_store=vector_store,
    )

    # Semantic search
    print("\n🔍 Semantic search for 'programming languages'...")
    results = await retriever.search(
        query="programming languages",
        top_k=3,
    )
    print(f"  Found {len(results)} results:")
    for result in results:
        print(f"    {result.id}: {result.score:.3f}")
        print(f"      {result.content[:100]}...")

    # Search with filtering
    print("\n🔍 Search with metadata filter (source=wikipedia)...")
    results = await retriever.search(
        query="programming",
        top_k=3,
        filter={"source": "wikipedia"},
    )
    print(f"  Found {len(results)} results")

    # Format results
    print("\n📄 Formatted results:")
    formatted = retriever.format_results(results, include_scores=True)
    print(formatted)

    # Format as context
    print("\n📄 Formatted as LLM context:")
    context = retriever.format_context(results, max_tokens=200)
    print(context)

    # Cleanup
    await embeddings.disconnect()
    await vector_store.disconnect()
    print("\n✓ Retriever demo complete!")


async def demo_hybrid_search():
    """Demonstrate hybrid search (vector + keyword)."""
    if not RAG_AVAILABLE:
        return

    print("\n" + "=" * 70)
    print("Demo 5: Hybrid Search (Vector + Keyword)")
    print("=" * 70)

    # Initialize
    print("\n📊 Initializing components...")
    embeddings = EmbeddingService(openai_api_key=OPENAI_API_KEY)
    await embeddings.connect()

    vector_store = VectorStore(
        url=os.getenv("CORTEX_QDRANT_URL", "http://localhost:6333"),
        collection_name="test_documents",
    )
    await vector_store.connect()

    retriever = Retriever(
        embeddings=embeddings,
        vector_store=vector_store,
    )

    # Hybrid search with different alpha values
    query = "Python machine learning"

    for alpha in [0.0, 0.5, 1.0]:
        print(f"\n🔍 Hybrid search (alpha={alpha})...")
        results = await retriever.hybrid_search(
            query=query,
            top_k=3,
            alpha=alpha,
        )
        print(f"  Found {len(results)} results:")
        for result in results:
            print(f"    {result.id}: {result.score:.3f} - {result.content[:60]}...")

    # Cleanup
    await embeddings.disconnect()
    await vector_store.disconnect()
    print("\n✓ Hybrid search demo complete!")


async def demo_rag_with_agent():
    """Demonstrate RAG integration with Agent."""
    if not RAG_AVAILABLE or not AGENT_AVAILABLE:
        print("\n⚠️  Skipping Agent integration demo (dependencies not available)")
        return

    print("\n" + "=" * 70)
    print("Demo 6: RAG with Agent Integration")
    print("=" * 70)

    # Initialize RAG components
    print("\n📊 Initializing RAG components...")
    embeddings = EmbeddingService(openai_api_key=OPENAI_API_KEY)
    await embeddings.connect()

    vector_store = VectorStore(
        url=os.getenv("CORTEX_QDRANT_URL", "http://localhost:6333"),
        collection_name="test_documents",
    )
    await vector_store.connect()

    retriever = Retriever(
        embeddings=embeddings,
        vector_store=vector_store,
    )

    # Create search tool for agent
    async def search_knowledge_base(query: str, top_k: int = 3) -> str:
        """Search the knowledge base for relevant information."""
        results = await retriever.search(query, top_k=top_k)
        if not results:
            return "No relevant information found."
        return retriever.format_context(results, max_tokens=1000)

    # Create agent with RAG tool
    print("\n🤖 Creating agent with RAG capability...")
    agent = Agent(
        name="rag-assistant",
        system_prompt=(
            "You are a helpful assistant with access to a knowledge base. "
            "Use the search_knowledge_base tool to find relevant information "
            "before answering questions."
        ),
        model=ModelConfig(model="gpt-4o", use_gateway=False),
        tools=[search_knowledge_base],
    )

    # Ask questions
    questions = [
        "What programming languages are mentioned in the knowledge base?",
        "Tell me about Python's design philosophy",
    ]

    for question in questions:
        print(f"\n❓ Question: {question}")
        result = await agent.run(question)
        print(f"🤖 Answer: {result.response}")

    # Cleanup
    await embeddings.disconnect()
    await vector_store.disconnect()
    print("\n✓ RAG with Agent demo complete!")


async def demo_multi_tenancy():
    """Demonstrate multi-tenancy support."""
    if not RAG_AVAILABLE:
        return

    print("\n" + "=" * 70)
    print("Demo 7: Multi-Tenancy Support")
    print("=" * 70)

    # Initialize
    print("\n📊 Initializing components...")
    embeddings = EmbeddingService(openai_api_key=OPENAI_API_KEY)
    await embeddings.connect()

    vector_store = VectorStore(
        url=os.getenv("CORTEX_QDRANT_URL", "http://localhost:6333"),
        collection_name="multi_tenant_docs",
    )
    await vector_store.connect()

    # Create collection
    if await vector_store.collection_exists():
        await vector_store.delete_collection()
    await vector_store.create_collection()

    doc_manager = DocumentManager(
        embeddings=embeddings,
        vector_store=vector_store,
    )

    # Ingest documents for different tenants
    print("\n📝 Ingesting documents for tenant-1...")
    await doc_manager.ingest_document(
        doc_id="tenant1-doc1",
        content="Tenant 1 document about Python",
        metadata={"tenant_id": "tenant-1", "source": "tenant1"},
    )

    print("📝 Ingesting documents for tenant-2...")
    await doc_manager.ingest_document(
        doc_id="tenant2-doc1",
        content="Tenant 2 document about JavaScript",
        metadata={"tenant_id": "tenant-2", "source": "tenant2"},
    )

    # Search with tenant isolation
    retriever = Retriever(
        embeddings=embeddings,
        vector_store=vector_store,
    )

    print("\n🔍 Search for tenant-1 only...")
    results = await retriever.search(
        query="programming",
        top_k=5,
        tenant_id="tenant-1",
    )
    print(f"  Found {len(results)} results for tenant-1:")
    for result in results:
        print(f"    {result.id}: {result.metadata.get('tenant_id')}")

    print("\n🔍 Search for tenant-2 only...")
    results = await retriever.search(
        query="programming",
        top_k=5,
        tenant_id="tenant-2",
    )
    print(f"  Found {len(results)} results for tenant-2:")
    for result in results:
        print(f"    {result.id}: {result.metadata.get('tenant_id')}")

    # Cleanup
    await embeddings.disconnect()
    await vector_store.disconnect()
    print("\n✓ Multi-tenancy demo complete!")


async def main():
    """Run all RAG demos."""
    print("\n" + "=" * 70)
    print("Cortex-AI RAG Module - Comprehensive Demo")
    print("=" * 70)

    if not RAG_AVAILABLE:
        print("\n⚠️  RAG module not available")
        print("Install dependencies: pip install openai qdrant-client redis")
        return

    # Check configuration
    print("\nCurrent configuration:")
    print(f"  CORTEX_OPENAI_API_KEY: {'✓ Set' if OPENAI_API_KEY else '✗ Not set'}")
    print(f"  CORTEX_QDRANT_URL: {os.getenv('CORTEX_QDRANT_URL', 'http://localhost:6333')}")
    print(f"  CORTEX_REDIS_URL: {os.getenv('CORTEX_REDIS_URL', 'redis://localhost:6379')}")

    # Run demos
    await demo_embedding_service()
    await demo_vector_store()
    await demo_document_manager()
    await demo_retriever()
    await demo_hybrid_search()
    await demo_rag_with_agent()
    await demo_multi_tenancy()

    print("\n" + "=" * 70)
    print("All RAG Demos Complete!")
    print("=" * 70)

    print("\n✨ Key Features Demonstrated:")
    print("  1. Embedding service with Redis caching")
    print("  2. Vector store with Qdrant")
    print("  3. Document ingestion and management")
    print("  4. Semantic search")
    print("  5. Hybrid search (vector + keyword)")
    print("  6. Agent integration for RAG")
    print("  7. Multi-tenancy support")

    print("\n🎯 Use Cases:")
    print("  - Question answering over documents")
    print("  - Semantic search in knowledge bases")
    print("  - Document similarity and recommendations")
    print("  - Multi-tenant document systems")
    print("  - LLM-powered chatbots with knowledge retrieval")

    print("\n💡 Best Practices:")
    print("  1. Use Redis caching for cost optimization")
    print("  2. Chunk long documents for better retrieval")
    print("  3. Add metadata for filtering and organization")
    print("  4. Use hybrid search for better recall")
    print("  5. Implement proper tenant isolation in multi-tenant systems")
    print("  6. Monitor embedding API costs and cache hit rates")

    print("\n🔧 Production Setup:")
    print("  1. Deploy Qdrant cluster for scalability")
    print("  2. Setup Redis cluster for high availability")
    print("  3. Implement proper error handling and retries")
    print("  4. Add observability (metrics, logging, tracing)")
    print("  5. Use connection pooling for database access")
    print("  6. Implement rate limiting for embedding API")


if __name__ == "__main__":
    asyncio.run(main())
