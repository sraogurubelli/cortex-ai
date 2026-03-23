"""
Cortex-AI Evaluation & Benchmark Framework.

Provides tools for evaluating chat quality, RAG retrieval accuracy,
and running regression tests via conversation replay.

Modules:

- ``runner`` — Generic benchmark runner that calls the cortex-ai chat API
  with test inputs and records outputs.
- ``metrics`` — Pluggable evaluation metrics (semantic similarity,
  retrieval recall, answer relevance, latency).
- ``replay`` — Record and replay full conversations for regression testing.
"""
