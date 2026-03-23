"""
Evaluation metrics for cortex-ai benchmark results.

Provides pluggable metric functions that score a model response against
expected criteria.  Designed for both automated CI and interactive use.

Metrics:

- ``keyword_recall`` — fraction of expected keywords found in the response.
- ``semantic_similarity`` — cosine similarity between response and reference
  (requires an embedding model).
- ``answer_relevance`` — LLM-as-judge scoring of answer relevance.
- ``retrieval_recall`` — fraction of expected source chunks found in RAG
  retrieval results.
"""

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MetricResult:
    """Result of a single metric evaluation."""

    name: str
    score: float
    max_score: float = 1.0
    details: dict[str, Any] | None = None

    @property
    def normalized(self) -> float:
        """Score normalized to 0-1 range."""
        return self.score / self.max_score if self.max_score else 0.0


# ---------------------------------------------------------------------------
# Keyword-based metrics (no external dependencies)
# ---------------------------------------------------------------------------


def keyword_recall(
    response: str,
    expected_keywords: list[str],
) -> MetricResult:
    """Fraction of expected keywords found in the response.

    Args:
        response: Model response text.
        expected_keywords: Keywords that should appear in the response.

    Returns:
        MetricResult with score = fraction of keywords found.
    """
    if not expected_keywords:
        return MetricResult(name="keyword_recall", score=1.0)

    response_lower = response.lower()
    found = [kw for kw in expected_keywords if kw.lower() in response_lower]
    missing = [kw for kw in expected_keywords if kw.lower() not in response_lower]

    return MetricResult(
        name="keyword_recall",
        score=len(found) / len(expected_keywords),
        details={"found": found, "missing": missing},
    )


def negative_keyword_check(
    response: str,
    forbidden_keywords: list[str],
) -> MetricResult:
    """Check that none of the forbidden keywords appear in the response.

    Args:
        response: Model response text.
        forbidden_keywords: Keywords that should NOT appear.

    Returns:
        MetricResult with score=1.0 if none found, 0.0 if any found.
    """
    if not forbidden_keywords:
        return MetricResult(name="negative_keyword_check", score=1.0)

    response_lower = response.lower()
    violations = [
        kw for kw in forbidden_keywords if kw.lower() in response_lower
    ]

    return MetricResult(
        name="negative_keyword_check",
        score=0.0 if violations else 1.0,
        details={"violations": violations} if violations else None,
    )


def response_length_check(
    response: str,
    min_length: int = 10,
    max_length: int = 10_000,
) -> MetricResult:
    """Check that response length is within acceptable bounds.

    Args:
        response: Model response text.
        min_length: Minimum acceptable character count.
        max_length: Maximum acceptable character count.

    Returns:
        MetricResult with score=1.0 if within bounds.
    """
    length = len(response)
    in_bounds = min_length <= length <= max_length

    return MetricResult(
        name="response_length_check",
        score=1.0 if in_bounds else 0.0,
        details={
            "length": length,
            "min": min_length,
            "max": max_length,
        },
    )


# ---------------------------------------------------------------------------
# Semantic similarity (requires embeddings)
# ---------------------------------------------------------------------------


async def semantic_similarity(
    response: str,
    reference: str,
    embed_fn: Any = None,
) -> MetricResult:
    """Cosine similarity between response and reference embeddings.

    Args:
        response: Model response text.
        reference: Reference/expected response text.
        embed_fn: Async callable that takes a string and returns a list[float].
            If None, a simple word-overlap Jaccard score is used as fallback.

    Returns:
        MetricResult with cosine similarity score (0-1).
    """
    if embed_fn is None:
        return _jaccard_fallback(response, reference)

    try:
        resp_emb = await embed_fn(response)
        ref_emb = await embed_fn(reference)
        score = _cosine_similarity(resp_emb, ref_emb)
        return MetricResult(name="semantic_similarity", score=score)
    except Exception:
        logger.warning("Embedding failed, using Jaccard fallback", exc_info=True)
        return _jaccard_fallback(response, reference)


def _jaccard_fallback(a: str, b: str) -> MetricResult:
    """Word-level Jaccard similarity as a no-dependency fallback."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return MetricResult(name="semantic_similarity", score=0.0)
    intersection = words_a & words_b
    union = words_a | words_b
    return MetricResult(
        name="semantic_similarity",
        score=len(intersection) / len(union),
        details={"method": "jaccard_fallback"},
    )


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# Retrieval recall (for RAG evaluation)
# ---------------------------------------------------------------------------


def retrieval_recall(
    retrieved_chunks: list[str],
    expected_chunks: list[str],
) -> MetricResult:
    """Fraction of expected chunks that were retrieved by the RAG pipeline.

    Uses substring matching: an expected chunk is "found" if it appears
    as a substring of any retrieved chunk.

    Args:
        retrieved_chunks: Chunks returned by the RAG retrieval step.
        expected_chunks: Chunks that should have been retrieved.

    Returns:
        MetricResult with recall score.
    """
    if not expected_chunks:
        return MetricResult(name="retrieval_recall", score=1.0)

    retrieved_text = " ".join(retrieved_chunks).lower()
    found = [c for c in expected_chunks if c.lower() in retrieved_text]
    missing = [c for c in expected_chunks if c.lower() not in retrieved_text]

    return MetricResult(
        name="retrieval_recall",
        score=len(found) / len(expected_chunks),
        details={"found": len(found), "missing": missing},
    )
