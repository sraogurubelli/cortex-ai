"""
Conversation replay infrastructure for reproducing and evaluating
multi-turn conversations.

Load a recorded conversation corpus and replay it against a live
endpoint to detect regressions, measure quality drift, and compare
model performance.

Usage::

    from evals.replay import ReplayRunner, ConversationCorpus

    corpus = ConversationCorpus.from_json("test_conversations.json")
    runner = ReplayRunner(
        base_url="http://localhost:8000",
        endpoint="/api/v1/projects/default/chat",
    )
    report = await runner.replay(corpus)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ConversationTurn:
    """A single turn in a recorded conversation."""

    role: str  # "user" or "assistant"
    content: str
    expected_keywords: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RecordedConversation:
    """A complete recorded conversation for replay."""

    id: str
    turns: list[ConversationTurn]
    system_prompt: str = ""
    model: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class ConversationCorpus:
    """Collection of recorded conversations for bulk replay."""

    def __init__(self, conversations: list[RecordedConversation]) -> None:
        self.conversations = conversations

    @classmethod
    def from_json(cls, path: str) -> "ConversationCorpus":
        """Load a corpus from a JSON file.

        Expected format::

            [
                {
                    "id": "conv-1",
                    "system_prompt": "You are helpful",
                    "turns": [
                        {"role": "user", "content": "Hello"},
                        {"role": "assistant", "content": "Hi there!", "expected_keywords": ["hi"]},
                        {"role": "user", "content": "What is Python?"},
                        {"role": "assistant", "content": "...", "expected_keywords": ["language"]}
                    ]
                }
            ]
        """
        with open(path, "r") as f:
            data = json.load(f)

        conversations = []
        for entry in data:
            turns = [
                ConversationTurn(
                    role=t["role"],
                    content=t["content"],
                    expected_keywords=t.get("expected_keywords", []),
                    metadata=t.get("metadata", {}),
                )
                for t in entry.get("turns", [])
            ]
            conversations.append(RecordedConversation(
                id=entry.get("id", ""),
                turns=turns,
                system_prompt=entry.get("system_prompt", ""),
                model=entry.get("model", ""),
                tags=entry.get("tags", []),
                metadata=entry.get("metadata", {}),
            ))
        return cls(conversations)

    def filter_by_tag(self, tag: str) -> "ConversationCorpus":
        """Filter conversations by tag."""
        filtered = [c for c in self.conversations if tag in c.tags]
        return ConversationCorpus(filtered)

    def __len__(self) -> int:
        return len(self.conversations)


@dataclass
class ReplayTurnResult:
    """Result of replaying a single conversation turn."""

    turn_index: int
    expected_role: str
    actual_response: str = ""
    latency_ms: int = 0
    keyword_matches: list[str] = field(default_factory=list)
    keyword_misses: list[str] = field(default_factory=list)
    passed: bool = False
    error: Optional[str] = None


@dataclass
class ReplayResult:
    """Result of replaying a complete conversation."""

    conversation_id: str
    turn_results: list[ReplayTurnResult] = field(default_factory=list)
    total_latency_ms: int = 0

    @property
    def passed(self) -> bool:
        return all(t.passed for t in self.turn_results)

    @property
    def pass_rate(self) -> float:
        if not self.turn_results:
            return 0.0
        return sum(1 for t in self.turn_results if t.passed) / len(self.turn_results)


class ReplayRunner:
    """Replays recorded conversations against a live endpoint."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        endpoint: str = "/api/v1/projects/default/chat",
        model: str = "",
        auth_token: str = "",
        timeout_seconds: int = 60,
    ) -> None:
        self.base_url = base_url
        self.endpoint = endpoint
        self.model = model
        self.auth_token = auth_token
        self.timeout_seconds = timeout_seconds

    async def replay(self, corpus: ConversationCorpus) -> list[ReplayResult]:
        """Replay all conversations in the corpus.

        Returns a list of ReplayResult, one per conversation.
        """
        results = []
        for conv in corpus.conversations:
            result = await self._replay_conversation(conv)
            results.append(result)
        return results

    async def _replay_conversation(self, conv: RecordedConversation) -> ReplayResult:
        """Replay a single conversation turn by turn."""
        try:
            import httpx
        except ImportError:
            return ReplayResult(
                conversation_id=conv.id,
                turn_results=[ReplayTurnResult(
                    turn_index=0, expected_role="user",
                    error="httpx not installed",
                )],
            )

        result = ReplayResult(conversation_id=conv.id)
        history: list[dict] = []
        total_start = time.monotonic()

        url = f"{self.base_url.rstrip('/')}{self.endpoint}"
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            for i, turn in enumerate(conv.turns):
                if turn.role == "user":
                    start = time.monotonic()
                    payload: dict[str, Any] = {
                        "message": turn.content,
                        "conversation_history": history,
                    }
                    if conv.system_prompt:
                        payload["system_prompt"] = conv.system_prompt
                    model = conv.model or self.model
                    if model:
                        payload["model"] = model

                    try:
                        resp = await client.post(url, json=payload, headers=headers)
                        latency = int((time.monotonic() - start) * 1000)

                        if resp.status_code != 200:
                            result.turn_results.append(ReplayTurnResult(
                                turn_index=i, expected_role="user",
                                latency_ms=latency,
                                error=f"HTTP {resp.status_code}",
                            ))
                            break

                        data = resp.json()
                        response_text = data.get("response", "")
                        history.append({"role": "user", "content": turn.content})
                        history.append({"role": "assistant", "content": response_text})

                    except Exception as e:
                        latency = int((time.monotonic() - start) * 1000)
                        result.turn_results.append(ReplayTurnResult(
                            turn_index=i, expected_role="user",
                            latency_ms=latency, error=str(e),
                        ))
                        break

                elif turn.role == "assistant":
                    actual = history[-1]["content"] if history else ""
                    response_lower = actual.lower()

                    matches = [kw for kw in turn.expected_keywords if kw.lower() in response_lower]
                    misses = [kw for kw in turn.expected_keywords if kw.lower() not in response_lower]

                    passed = len(misses) == 0 if turn.expected_keywords else True

                    result.turn_results.append(ReplayTurnResult(
                        turn_index=i,
                        expected_role="assistant",
                        actual_response=actual[:500],
                        keyword_matches=matches,
                        keyword_misses=misses,
                        passed=passed,
                    ))

        result.total_latency_ms = int((time.monotonic() - total_start) * 1000)
        return result
