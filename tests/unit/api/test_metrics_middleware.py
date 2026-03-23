"""Unit tests for Prometheus metrics middleware."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.requests import Request
from starlette.responses import Response

from cortex.api.middleware import metrics as metrics_mod


@pytest.mark.unit
class TestSanitizePath:
    def test_collapses_id_after_projects(self):
        assert metrics_mod._sanitize_path("/api/v1/projects/prj_123/agents") == (
            "/api/v1/projects/{id}/agents"
        )

    def test_collapses_multiple_parameter_segments(self):
        p = metrics_mod._sanitize_path("/v1/conversations/conv-1/documents/doc-2")
        assert "{id}" in p
        assert "conv-1" not in p
        assert "doc-2" not in p

    def test_preserves_segments_not_after_reserved_keywords(self):
        assert metrics_mod._sanitize_path("/api/health") == "/api/health"


@pytest.mark.unit
class TestPrometheusMetricsMiddlewareRecording:
    @pytest.mark.asyncio
    async def test_dispatch_increments_counter_and_observes_latency(self):
        mock_labels_count = MagicMock()
        mock_labels_latency = MagicMock()
        mock_labels_active = MagicMock()

        mock_counter = MagicMock()
        mock_counter.labels.return_value = mock_labels_count
        mock_hist = MagicMock()
        mock_hist.labels.return_value = mock_labels_latency
        mock_gauge = MagicMock()
        mock_gauge.labels.return_value = mock_labels_active

        with patch("prometheus_client.Counter", return_value=mock_counter):
            with patch("prometheus_client.Histogram", return_value=mock_hist):
                with patch("prometheus_client.Gauge", return_value=mock_gauge):
                    mw = metrics_mod.PrometheusMetricsMiddleware(MagicMock())

        assert mw._available is True

        async def call_next(_req: Request) -> Response:
            return Response(status_code=201)

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/projects/abc",
            "headers": [],
        }
        req = Request(scope)
        req._url = req.url.replace(path="/api/v1/projects/abc")

        await mw.dispatch(req, call_next)

        mock_labels_active.inc.assert_called_once()
        mock_labels_active.dec.assert_called_once()
        mock_labels_count.inc.assert_called_once()
        mock_labels_latency.observe.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_skips_metrics_path(self):
        with patch("prometheus_client.Counter", return_value=MagicMock()):
            with patch("prometheus_client.Histogram", return_value=MagicMock()):
                with patch("prometheus_client.Gauge", return_value=MagicMock()):
                    mw = metrics_mod.PrometheusMetricsMiddleware(MagicMock())

        inner = AsyncMock(return_value=Response(status_code=200))
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/metrics",
            "headers": [],
        }
        req = Request(scope)
        req._url = req.url.replace(path="/metrics")

        await mw.dispatch(req, inner)
        inner.assert_awaited_once()
        mw._request_count.labels.assert_not_called()
