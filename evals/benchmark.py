"""
Generic benchmark runner for evaluating chat endpoints.

Sends a corpus of test prompts to a configurable endpoint and
collects metrics: latency, token usage, response quality, and errors.

Usage::

    from evals.benchmark import BenchmarkRunner, BenchmarkConfig, TestCase

    runner = BenchmarkRunner(BenchmarkConfig(
        base_url="http://localhost:8000",
        endpoint="/api/v1/projects/{project_uid}/chat",
        model="claude-sonnet-4-20250514",
    ))

    cases = [
        TestCase(prompt="What is Python?", expected_keywords=["programming", "language"]),
        TestCase(prompt="Write a hello world in Go", expected_keywords=["fmt", "Println"]),
    ]

    report = await runner.run(cases)
    report.to_csv("results.csv")
    print(report.summary())
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import time
from dataclasses import dataclass, field
from io import StringIO
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class TestCase:
    """A single evaluation test case.

    Attributes:
        prompt: User message to send.
        expected_keywords: Keywords expected in the response (case-insensitive).
        expected_not_keywords: Keywords that should NOT appear.
        system_prompt: Optional system prompt override.
        metadata: Arbitrary metadata for grouping/filtering.
        max_latency_ms: Maximum acceptable latency in milliseconds.
    """

    prompt: str
    expected_keywords: list[str] = field(default_factory=list)
    expected_not_keywords: list[str] = field(default_factory=list)
    system_prompt: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    max_latency_ms: int = 30000


@dataclass
class TestResult:
    """Result of a single test case evaluation."""

    test_case: TestCase
    response: str = ""
    latency_ms: int = 0
    tokens_used: dict[str, int] = field(default_factory=dict)
    passed: bool = False
    keyword_matches: list[str] = field(default_factory=list)
    keyword_misses: list[str] = field(default_factory=list)
    forbidden_matches: list[str] = field(default_factory=list)
    error: Optional[str] = None
    raw_response: dict = field(default_factory=dict)


@dataclass
class BenchmarkConfig:
    """Configuration for the benchmark runner."""

    base_url: str = "http://localhost:8000"
    endpoint: str = "/api/v1/projects/default/chat"
    model: str = "gpt-4o"
    temperature: float = 0.0
    auth_token: str = ""
    concurrency: int = 1
    timeout_seconds: int = 60
    headers: dict[str, str] = field(default_factory=dict)


class BenchmarkReport:
    """Collected results from a benchmark run."""

    def __init__(self, config: BenchmarkConfig, results: list[TestResult]) -> None:
        self.config = config
        self.results = results

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def error_count(self) -> int:
        return sum(1 for r in self.results if r.error)

    @property
    def avg_latency_ms(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.latency_ms for r in self.results) / len(self.results)

    @property
    def p95_latency_ms(self) -> float:
        if not self.results:
            return 0.0
        sorted_latencies = sorted(r.latency_ms for r in self.results)
        idx = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]

    def summary(self) -> str:
        return (
            f"Benchmark Report\n"
            f"  Model: {self.config.model}\n"
            f"  Total: {self.total} | Passed: {self.passed} | Failed: {self.failed}\n"
            f"  Errors: {self.error_count}\n"
            f"  Avg Latency: {self.avg_latency_ms:.0f}ms | P95: {self.p95_latency_ms:.0f}ms\n"
            f"  Pass Rate: {(self.passed / self.total * 100) if self.total else 0:.1f}%"
        )

    def to_csv(self, path: str) -> None:
        """Write results to a CSV file."""
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "prompt", "passed", "latency_ms", "keyword_matches",
                "keyword_misses", "forbidden_matches", "error",
                "response_preview",
            ])
            for r in self.results:
                writer.writerow([
                    r.test_case.prompt[:100],
                    r.passed,
                    r.latency_ms,
                    "|".join(r.keyword_matches),
                    "|".join(r.keyword_misses),
                    "|".join(r.forbidden_matches),
                    r.error or "",
                    r.response[:200],
                ])

    def to_json(self) -> str:
        """Return results as JSON string."""
        return json.dumps({
            "config": {
                "model": self.config.model,
                "endpoint": self.config.endpoint,
            },
            "summary": {
                "total": self.total,
                "passed": self.passed,
                "failed": self.failed,
                "avg_latency_ms": round(self.avg_latency_ms),
                "p95_latency_ms": round(self.p95_latency_ms),
            },
            "results": [
                {
                    "prompt": r.test_case.prompt[:100],
                    "passed": r.passed,
                    "latency_ms": r.latency_ms,
                    "error": r.error,
                }
                for r in self.results
            ],
        }, indent=2)


class BenchmarkRunner:
    """HTTP-based benchmark runner for chat endpoints."""

    def __init__(self, config: BenchmarkConfig) -> None:
        self.config = config

    async def run(self, cases: list[TestCase]) -> BenchmarkReport:
        """Run all test cases and return a report.

        Respects the ``concurrency`` setting for parallel execution.
        """
        semaphore = asyncio.Semaphore(self.config.concurrency)

        async def run_one(case: TestCase) -> TestResult:
            async with semaphore:
                return await self._run_single(case)

        results = await asyncio.gather(*[run_one(c) for c in cases])
        return BenchmarkReport(self.config, list(results))

    async def _run_single(self, case: TestCase) -> TestResult:
        """Execute a single test case against the endpoint."""
        try:
            import httpx
        except ImportError:
            return TestResult(
                test_case=case,
                error="httpx not installed (pip install httpx)",
            )

        url = f"{self.config.base_url.rstrip('/')}{self.config.endpoint}"
        headers = {"Content-Type": "application/json", **self.config.headers}
        if self.config.auth_token:
            headers["Authorization"] = f"Bearer {self.config.auth_token}"

        payload: dict[str, Any] = {
            "message": case.prompt,
            "model": self.config.model,
            "temperature": self.config.temperature,
        }
        if case.system_prompt:
            payload["system_prompt"] = case.system_prompt

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
                resp = await client.post(url, json=payload, headers=headers)
                latency_ms = int((time.monotonic() - start) * 1000)

                if resp.status_code != 200:
                    return TestResult(
                        test_case=case,
                        latency_ms=latency_ms,
                        error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                    )

                data = resp.json()
                response_text = data.get("response", data.get("content", ""))
                tokens = data.get("usage", {})

        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return TestResult(
                test_case=case,
                latency_ms=latency_ms,
                error=str(e),
            )

        # Evaluate keywords
        response_lower = response_text.lower()
        matches = [kw for kw in case.expected_keywords if kw.lower() in response_lower]
        misses = [kw for kw in case.expected_keywords if kw.lower() not in response_lower]
        forbidden = [kw for kw in case.expected_not_keywords if kw.lower() in response_lower]

        passed = (
            len(misses) == 0
            and len(forbidden) == 0
            and latency_ms <= case.max_latency_ms
            and not bool(data.get("error"))
        )

        return TestResult(
            test_case=case,
            response=response_text,
            latency_ms=latency_ms,
            tokens_used=tokens,
            passed=passed,
            keyword_matches=matches,
            keyword_misses=misses,
            forbidden_matches=forbidden,
            raw_response=data,
        )
