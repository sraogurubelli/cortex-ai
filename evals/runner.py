"""
Benchmark Runner — calls the cortex-ai chat API with test inputs and evaluates outputs.

Usage::

    # From the command line
    python -m evals.runner --base-url http://localhost:8000 --suite evals/suites/basic_chat.json

    # Programmatically
    from evals.runner import BenchmarkRunner, TestCase

    runner = BenchmarkRunner(base_url="http://localhost:8000")
    results = await runner.run_suite([
        TestCase(
            id="greeting",
            message="Hello, who are you?",
            project_uid="proj-123",
            expected_contains=["assistant", "help"],
        ),
    ])
    runner.print_report(results)

Test Suite JSON format::

    {
      "name": "Basic Chat Tests",
      "project_uid": "default-project",
      "cases": [
        {
          "id": "greeting",
          "message": "Hello, who are you?",
          "expected_contains": ["assistant", "help"],
          "max_latency_ms": 5000
        },
        {
          "id": "rag_query",
          "message": "What does our refund policy say?",
          "expected_contains": ["refund", "30 days"],
          "eval_retrieval": true
        }
      ]
    }

Adapted from ml-infra evals/benchmark_evals.py (Harness YAML-specific
evaluation removed, replaced with generic chat + RAG quality metrics).
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class TestCase:
    """A single benchmark test case."""

    id: str
    message: str
    project_uid: str = "default"
    model: str | None = None
    conversation_id: str | None = None

    expected_contains: list[str] = field(default_factory=list)
    expected_not_contains: list[str] = field(default_factory=list)
    max_latency_ms: int | None = None

    eval_retrieval: bool = False

    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TestResult:
    """Result of running a single test case."""

    case_id: str
    passed: bool
    response: str
    latency_ms: float

    contains_pass: bool = True
    not_contains_pass: bool = True
    latency_pass: bool = True

    conversation_id: str | None = None
    error: str | None = None

    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class SuiteResult:
    """Aggregated results for a test suite."""

    name: str
    results: list[TestResult]
    total_time_ms: float

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
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def avg_latency_ms(self) -> float:
        latencies = [r.latency_ms for r in self.results if r.error is None]
        return sum(latencies) / len(latencies) if latencies else 0.0


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class BenchmarkRunner:
    """Runs evaluation test suites against the cortex-ai chat API.

    Args:
        base_url: Base URL of the cortex-ai server (e.g. ``http://localhost:8000``).
        auth_token: Optional Bearer token for authentication.
        concurrency: Max concurrent requests.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        auth_token: str | None = None,
        concurrency: int = 5,
        timeout: float = 60.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.concurrency = concurrency
        self.timeout = timeout

    async def run_suite(
        self,
        cases: list[TestCase],
        suite_name: str = "default",
    ) -> SuiteResult:
        """Run a list of test cases and return aggregated results."""
        semaphore = asyncio.Semaphore(self.concurrency)
        start = time.monotonic()

        async with aiohttp.ClientSession() as session:

            async def _run_one(case: TestCase) -> TestResult:
                async with semaphore:
                    return await self._execute_case(session, case)

            results = await asyncio.gather(
                *[_run_one(c) for c in cases], return_exceptions=True
            )

        processed: list[TestResult] = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                processed.append(
                    TestResult(
                        case_id=cases[i].id,
                        passed=False,
                        response="",
                        latency_ms=0,
                        error=str(r),
                    )
                )
            else:
                processed.append(r)

        total_time = (time.monotonic() - start) * 1000
        return SuiteResult(
            name=suite_name, results=processed, total_time_ms=total_time
        )

    async def run_suite_from_file(self, path: str | Path) -> SuiteResult:
        """Load a test suite from a JSON file and run it."""
        path = Path(path)
        with open(path, "r") as f:
            data = json.load(f)

        suite_name = data.get("name", path.stem)
        default_project = data.get("project_uid", "default")

        cases = []
        for entry in data.get("cases", []):
            cases.append(
                TestCase(
                    id=entry["id"],
                    message=entry["message"],
                    project_uid=entry.get("project_uid", default_project),
                    model=entry.get("model"),
                    expected_contains=entry.get("expected_contains", []),
                    expected_not_contains=entry.get("expected_not_contains", []),
                    max_latency_ms=entry.get("max_latency_ms"),
                    eval_retrieval=entry.get("eval_retrieval", False),
                    metadata=entry.get("metadata", {}),
                )
            )

        return await self.run_suite(cases, suite_name=suite_name)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _execute_case(
        self, session: aiohttp.ClientSession, case: TestCase
    ) -> TestResult:
        """Execute a single test case against the chat API."""
        url = f"{self.base_url}/api/v1/projects/{case.project_uid}/chat"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        payload: dict[str, Any] = {
            "message": case.message,
            "stream": False,
        }
        if case.model:
            payload["model"] = case.model
        if case.conversation_id:
            payload["conversation_id"] = case.conversation_id

        start = time.monotonic()
        try:
            async with session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as resp:
                latency = (time.monotonic() - start) * 1000
                body = await resp.json()

                if resp.status != 200:
                    return TestResult(
                        case_id=case.id,
                        passed=False,
                        response=str(body),
                        latency_ms=latency,
                        error=f"HTTP {resp.status}: {body}",
                    )

                response_text = body.get("response", body.get("message", ""))
                conversation_id = body.get("conversation_id")

        except Exception as exc:
            latency = (time.monotonic() - start) * 1000
            return TestResult(
                case_id=case.id,
                passed=False,
                response="",
                latency_ms=latency,
                error=str(exc),
            )

        return self._evaluate(case, response_text, latency, conversation_id)

    def _evaluate(
        self,
        case: TestCase,
        response: str,
        latency_ms: float,
        conversation_id: str | None,
    ) -> TestResult:
        """Evaluate a response against the test case criteria."""
        response_lower = response.lower()

        contains_pass = all(
            kw.lower() in response_lower for kw in case.expected_contains
        )
        not_contains_pass = all(
            kw.lower() not in response_lower
            for kw in case.expected_not_contains
        )
        latency_pass = (
            latency_ms <= case.max_latency_ms
            if case.max_latency_ms
            else True
        )

        passed = contains_pass and not_contains_pass and latency_pass

        details: dict[str, Any] = {}
        if not contains_pass:
            missing = [
                kw
                for kw in case.expected_contains
                if kw.lower() not in response_lower
            ]
            details["missing_keywords"] = missing
        if not not_contains_pass:
            unwanted = [
                kw
                for kw in case.expected_not_contains
                if kw.lower() in response_lower
            ]
            details["unwanted_keywords_found"] = unwanted
        if not latency_pass:
            details["latency_exceeded"] = {
                "actual_ms": latency_ms,
                "max_ms": case.max_latency_ms,
            }

        return TestResult(
            case_id=case.id,
            passed=passed,
            response=response,
            latency_ms=latency_ms,
            contains_pass=contains_pass,
            not_contains_pass=not_contains_pass,
            latency_pass=latency_pass,
            conversation_id=conversation_id,
            details=details,
        )

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    @staticmethod
    def print_report(suite: SuiteResult) -> None:
        """Print a human-readable evaluation report to stdout."""
        print(f"\n{'=' * 60}")
        print(f"  Eval Suite: {suite.name}")
        print(f"{'=' * 60}")
        print(
            f"  Total: {suite.total}  |  "
            f"Passed: {suite.passed}  |  "
            f"Failed: {suite.failed}  |  "
            f"Rate: {suite.pass_rate:.0%}"
        )
        print(f"  Avg latency: {suite.avg_latency_ms:.0f} ms")
        print(f"  Total time:  {suite.total_time_ms:.0f} ms")
        print(f"{'=' * 60}")

        for r in suite.results:
            status = "PASS" if r.passed else "FAIL"
            print(f"  [{status}] {r.case_id} ({r.latency_ms:.0f} ms)")
            if r.error:
                print(f"        error: {r.error}")
            if r.details:
                for k, v in r.details.items():
                    print(f"        {k}: {v}")

        print(f"{'=' * 60}\n")

    @staticmethod
    def save_results(suite: SuiteResult, path: str | Path) -> None:
        """Save evaluation results to a JSON file."""
        path = Path(path)
        data = {
            "name": suite.name,
            "total": suite.total,
            "passed": suite.passed,
            "failed": suite.failed,
            "pass_rate": suite.pass_rate,
            "avg_latency_ms": suite.avg_latency_ms,
            "total_time_ms": suite.total_time_ms,
            "results": [
                {
                    "case_id": r.case_id,
                    "passed": r.passed,
                    "latency_ms": r.latency_ms,
                    "response_preview": r.response[:500],
                    "conversation_id": r.conversation_id,
                    "error": r.error,
                    "details": r.details,
                }
                for r in suite.results
            ],
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("Results saved to %s", path)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Cortex-AI Benchmark Runner")
    parser.add_argument(
        "--suite",
        required=True,
        help="Path to test suite JSON file",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("CORTEX_BASE_URL", "http://localhost:8000"),
        help="Cortex-AI server base URL",
    )
    parser.add_argument(
        "--auth-token",
        default=os.getenv("CORTEX_AUTH_TOKEN", ""),
        help="Bearer auth token",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Max concurrent requests",
    )
    parser.add_argument(
        "--output",
        help="Path to save results JSON",
    )

    args = parser.parse_args()

    runner = BenchmarkRunner(
        base_url=args.base_url,
        auth_token=args.auth_token or None,
        concurrency=args.concurrency,
    )

    suite_result = asyncio.run(runner.run_suite_from_file(args.suite))
    runner.print_report(suite_result)

    if args.output:
        runner.save_results(suite_result, args.output)
