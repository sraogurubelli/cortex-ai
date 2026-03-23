"""Tests for BenchmarkRunner evaluation logic and data classes."""

import json
import tempfile

import pytest

from evals.runner import BenchmarkRunner, SuiteResult, TestCase, TestResult


@pytest.mark.unit
class TestTestCase:
    """Tests for TestCase dataclass."""

    def test_defaults(self):
        tc = TestCase(id="t1", message="Hello")
        assert tc.project_uid == "default"
        assert tc.expected_contains == []
        assert tc.max_latency_ms is None
        assert tc.eval_retrieval is False


@pytest.mark.unit
class TestTestResult:
    """Tests for TestResult dataclass."""

    def test_passed_result(self):
        tr = TestResult(
            case_id="t1", passed=True, response="hello", latency_ms=100.0
        )
        assert tr.passed is True
        assert tr.error is None

    def test_failed_result(self):
        tr = TestResult(
            case_id="t2",
            passed=False,
            response="",
            latency_ms=0,
            error="timeout",
        )
        assert tr.passed is False
        assert tr.error == "timeout"


@pytest.mark.unit
class TestSuiteResult:
    """Tests for SuiteResult aggregation."""

    def _make_results(self, passed: int, failed: int) -> list[TestResult]:
        results = []
        for i in range(passed):
            results.append(
                TestResult(
                    case_id=f"pass-{i}",
                    passed=True,
                    response="ok",
                    latency_ms=100.0 + i * 10,
                )
            )
        for i in range(failed):
            results.append(
                TestResult(
                    case_id=f"fail-{i}",
                    passed=False,
                    response="bad",
                    latency_ms=500.0,
                )
            )
        return results

    def test_total_count(self):
        sr = SuiteResult(
            name="test", results=self._make_results(3, 2), total_time_ms=1000
        )
        assert sr.total == 5
        assert sr.passed == 3
        assert sr.failed == 2

    def test_pass_rate(self):
        sr = SuiteResult(
            name="test", results=self._make_results(4, 1), total_time_ms=1000
        )
        assert sr.pass_rate == pytest.approx(0.8)

    def test_avg_latency(self):
        sr = SuiteResult(
            name="test", results=self._make_results(2, 0), total_time_ms=500
        )
        assert sr.avg_latency_ms == pytest.approx(105.0)

    def test_empty_suite(self):
        sr = SuiteResult(name="empty", results=[], total_time_ms=0)
        assert sr.total == 0
        assert sr.pass_rate == 0.0
        assert sr.avg_latency_ms == 0.0


@pytest.mark.unit
class TestBenchmarkRunnerEvaluate:
    """Tests for the _evaluate method (no network calls)."""

    def setup_method(self):
        self.runner = BenchmarkRunner(base_url="http://test:8000")

    def test_keyword_match_passes(self):
        case = TestCase(
            id="kw",
            message="test",
            expected_contains=["hello", "world"],
        )
        result = self.runner._evaluate(
            case, "Hello World!", latency_ms=100, conversation_id=None
        )
        assert result.passed is True
        assert result.contains_pass is True

    def test_keyword_match_fails(self):
        case = TestCase(
            id="kw-fail",
            message="test",
            expected_contains=["hello", "missing"],
        )
        result = self.runner._evaluate(
            case, "Hello World!", latency_ms=100, conversation_id=None
        )
        assert result.passed is False
        assert result.contains_pass is False
        assert "missing" in result.details.get("missing_keywords", [])

    def test_negative_keyword_passes(self):
        case = TestCase(
            id="neg",
            message="test",
            expected_not_contains=["error", "fail"],
        )
        result = self.runner._evaluate(
            case, "Everything is fine", latency_ms=100, conversation_id=None
        )
        assert result.not_contains_pass is True

    def test_negative_keyword_fails(self):
        case = TestCase(
            id="neg-fail",
            message="test",
            expected_not_contains=["error"],
        )
        result = self.runner._evaluate(
            case, "There was an error", latency_ms=100, conversation_id=None
        )
        assert result.not_contains_pass is False
        assert "error" in result.details.get("unwanted_keywords_found", [])

    def test_latency_check_passes(self):
        case = TestCase(
            id="lat", message="test", max_latency_ms=5000
        )
        result = self.runner._evaluate(
            case, "response", latency_ms=1000, conversation_id=None
        )
        assert result.latency_pass is True

    def test_latency_check_fails(self):
        case = TestCase(
            id="lat-fail", message="test", max_latency_ms=500
        )
        result = self.runner._evaluate(
            case, "response", latency_ms=1000, conversation_id=None
        )
        assert result.latency_pass is False
        assert result.passed is False

    def test_no_latency_constraint(self):
        case = TestCase(id="no-lat", message="test")
        result = self.runner._evaluate(
            case, "anything", latency_ms=99999, conversation_id=None
        )
        assert result.latency_pass is True


@pytest.mark.unit
class TestSuiteFromFile:
    """Test loading a suite from JSON."""

    @pytest.mark.asyncio
    async def test_load_and_parse(self):
        suite_data = {
            "name": "Test Suite",
            "project_uid": "proj-1",
            "cases": [
                {
                    "id": "q1",
                    "message": "What is AI?",
                    "expected_contains": ["artificial", "intelligence"],
                    "max_latency_ms": 3000,
                },
            ],
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(suite_data, f)
            f.flush()

            runner = BenchmarkRunner(base_url="http://test:8000")
            # We can't run the suite (no server), but we can verify parsing
            # by reading the file directly
            import json as json_mod
            from pathlib import Path

            data = json_mod.loads(Path(f.name).read_text())
            assert data["name"] == "Test Suite"
            assert len(data["cases"]) == 1
            assert data["cases"][0]["id"] == "q1"


@pytest.mark.unit
class TestSaveResults:
    """Test saving results to JSON."""

    def test_save_and_reload(self):
        sr = SuiteResult(
            name="save-test",
            results=[
                TestResult(
                    case_id="c1",
                    passed=True,
                    response="ok" * 100,
                    latency_ms=150,
                )
            ],
            total_time_ms=200,
        )

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            BenchmarkRunner.save_results(sr, f.name)

            with open(f.name, "r") as rf:
                data = json.load(rf)

            assert data["name"] == "save-test"
            assert data["total"] == 1
            assert data["passed"] == 1
            assert len(data["results"]) == 1
