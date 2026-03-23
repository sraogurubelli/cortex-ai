"""
Conversation Replay — record and replay full conversations for regression testing.

Records the request/response pairs from a live conversation and saves them
to a JSON file.  On replay, the recorded inputs are sent to the API and the
new outputs are compared against the recorded outputs.

Usage::

    from evals.replay import ConversationRecorder, replay_conversation

    # Recording a conversation
    recorder = ConversationRecorder(conversation_name="onboarding-flow")
    recorder.add_turn(
        message="How do I create a project?",
        response="To create a project, navigate to...",
        metadata={"model": "gpt-4o", "latency_ms": 1200},
    )
    recorder.save("evals/recordings/onboarding.json")

    # Replaying and comparing
    results = await replay_conversation(
        recording_path="evals/recordings/onboarding.json",
        base_url="http://localhost:8000",
        project_uid="proj-123",
    )
    for turn in results:
        print(f"Turn {turn['index']}: {'MATCH' if turn['match'] else 'DIFF'}")
"""

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------


@dataclass
class ConversationTurn:
    """A single turn in a recorded conversation."""

    index: int
    message: str
    response: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationRecording:
    """A full recorded conversation."""

    name: str
    turns: list[ConversationTurn] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class ConversationRecorder:
    """Records conversation turns for later replay.

    Args:
        conversation_name: Human-readable name for the recording.
    """

    def __init__(self, conversation_name: str = "unnamed"):
        self._recording = ConversationRecording(name=conversation_name)
        self._index = 0

    def add_turn(
        self,
        message: str,
        response: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a single conversation turn."""
        self._recording.turns.append(
            ConversationTurn(
                index=self._index,
                message=message,
                response=response,
                metadata=metadata or {},
            )
        )
        self._index += 1

    def save(self, path: str | Path) -> None:
        """Save the recording to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "name": self._recording.name,
            "metadata": self._recording.metadata,
            "turns": [
                {
                    "index": t.index,
                    "message": t.message,
                    "response": t.response,
                    "metadata": t.metadata,
                }
                for t in self._recording.turns
            ],
        }

        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("Recording saved to %s (%d turns)", path, len(self._recording.turns))


def load_recording(path: str | Path) -> ConversationRecording:
    """Load a conversation recording from a JSON file."""
    with open(path, "r") as f:
        data = json.load(f)

    return ConversationRecording(
        name=data.get("name", "unnamed"),
        metadata=data.get("metadata", {}),
        turns=[
            ConversationTurn(
                index=t["index"],
                message=t["message"],
                response=t["response"],
                metadata=t.get("metadata", {}),
            )
            for t in data.get("turns", [])
        ],
    )


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------


@dataclass
class ReplayTurnResult:
    """Result of replaying a single conversation turn."""

    index: int
    message: str
    expected_response: str
    actual_response: str
    match: bool
    similarity_score: float
    latency_ms: float
    error: str | None = None


async def replay_conversation(
    recording_path: str | Path,
    base_url: str = "http://localhost:8000",
    project_uid: str = "default",
    auth_token: str | None = None,
    similarity_threshold: float = 0.5,
) -> list[ReplayTurnResult]:
    """Replay a recorded conversation and compare outputs.

    Each turn is sent sequentially (maintaining conversation context via
    ``conversation_id``).  The new response is compared against the
    recorded response using word-overlap similarity.

    Args:
        recording_path: Path to the recording JSON file.
        base_url: Cortex-AI server URL.
        project_uid: Project UID for the chat API.
        auth_token: Optional Bearer token.
        similarity_threshold: Minimum similarity to consider a "match".

    Returns:
        List of ``ReplayTurnResult`` for each turn.
    """
    recording = load_recording(recording_path)
    results: list[ReplayTurnResult] = []
    conversation_id: str | None = None

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    async with aiohttp.ClientSession() as session:
        for turn in recording.turns:
            start = time.monotonic()
            try:
                payload: dict[str, Any] = {
                    "message": turn.message,
                    "stream": False,
                }
                if conversation_id:
                    payload["conversation_id"] = conversation_id

                url = f"{base_url}/api/v1/projects/{project_uid}/chat"
                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    latency = (time.monotonic() - start) * 1000
                    body = await resp.json()

                    actual = body.get("response", body.get("message", ""))
                    conversation_id = body.get("conversation_id", conversation_id)

            except Exception as exc:
                latency = (time.monotonic() - start) * 1000
                results.append(
                    ReplayTurnResult(
                        index=turn.index,
                        message=turn.message,
                        expected_response=turn.response,
                        actual_response="",
                        match=False,
                        similarity_score=0.0,
                        latency_ms=latency,
                        error=str(exc),
                    )
                )
                continue

            sim = _word_overlap_similarity(turn.response, actual)
            results.append(
                ReplayTurnResult(
                    index=turn.index,
                    message=turn.message,
                    expected_response=turn.response,
                    actual_response=actual,
                    match=sim >= similarity_threshold,
                    similarity_score=sim,
                    latency_ms=latency,
                )
            )

    return results


def _word_overlap_similarity(a: str, b: str) -> float:
    """Jaccard word-overlap similarity between two strings."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)
