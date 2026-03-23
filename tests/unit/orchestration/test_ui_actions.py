"""Tests for UI action emitters and schemas."""

from unittest.mock import AsyncMock

import pytest

from cortex.orchestration.ui_actions.emitter import (
    emit_action,
    emit_navigate,
    emit_open_search,
    emit_show_document,
)
from cortex.orchestration.ui_actions.schemas import ActionStatus, UIAction, UIActionUpdate


@pytest.mark.unit
class TestUIActionSchemas:
    """Tests for Pydantic schemas."""

    def test_action_generates_id(self):
        action = UIAction(action_type="navigate", args={"page_id": "home"})
        assert action.action_id.startswith("act_")
        assert len(action.action_id) > 4

    def test_action_serialization(self):
        action = UIAction(
            action_type="show_document",
            args={"document_id": "doc-1"},
            display_text="Opening doc-1…",
        )
        data = action.model_dump()

        assert data["action_type"] == "show_document"
        assert data["args"]["document_id"] == "doc-1"
        assert data["status"] == "executing"

    def test_action_update_serialization(self):
        update = UIActionUpdate(
            action_id="act_abc123",
            status=ActionStatus.COMPLETED,
            result={"success": True},
        )
        data = update.model_dump()

        assert data["action_id"] == "act_abc123"
        assert data["status"] == "completed"
        assert data["result"]["success"] is True


@pytest.mark.unit
class TestEmitters:
    """Tests for emit_* functions with a mock stream writer."""

    @pytest.fixture
    def mock_writer(self):
        writer = AsyncMock()
        writer.write_event = AsyncMock()
        return writer

    @pytest.mark.asyncio
    async def test_emit_action(self, mock_writer):
        action_id = await emit_action(
            mock_writer,
            action_type="custom_action",
            args={"key": "value"},
            display_text="Doing something…",
        )

        assert action_id.startswith("act_")
        mock_writer.write_event.assert_called_once()
        call_args = mock_writer.write_event.call_args
        assert call_args[0][0] == "ui_action"
        payload = call_args[0][1]
        assert payload["action_type"] == "custom_action"

    @pytest.mark.asyncio
    async def test_emit_navigate(self, mock_writer):
        action_id = await emit_navigate(mock_writer, page_id="documents")

        assert action_id.startswith("act_")
        payload = mock_writer.write_event.call_args[0][1]
        assert payload["action_type"] == "navigate"
        assert payload["args"]["page_id"] == "documents"

    @pytest.mark.asyncio
    async def test_emit_show_document(self, mock_writer):
        action_id = await emit_show_document(
            mock_writer, document_id="doc-42", project_id="proj-1"
        )

        payload = mock_writer.write_event.call_args[0][1]
        assert payload["action_type"] == "show_document"
        assert payload["args"]["document_id"] == "doc-42"
        assert payload["args"]["project_id"] == "proj-1"

    @pytest.mark.asyncio
    async def test_emit_open_search(self, mock_writer):
        action_id = await emit_open_search(
            mock_writer, query="refund policy", project_id="proj-1"
        )

        payload = mock_writer.write_event.call_args[0][1]
        assert payload["action_type"] == "open_search"
        assert payload["args"]["query"] == "refund policy"

    @pytest.mark.asyncio
    async def test_emit_navigate_default_display_text(self, mock_writer):
        await emit_navigate(mock_writer, page_id="settings")
        payload = mock_writer.write_event.call_args[0][1]
        assert "settings" in payload["display_text"].lower()

    @pytest.mark.asyncio
    async def test_emit_show_document_without_project(self, mock_writer):
        await emit_show_document(mock_writer, document_id="doc-1")
        payload = mock_writer.write_event.call_args[0][1]
        assert "project_id" not in payload["args"]
