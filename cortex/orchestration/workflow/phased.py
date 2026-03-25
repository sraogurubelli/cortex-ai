"""
Phased workflow engine for structured multi-step agent execution.

Implements the plan → generate → verify → fix pattern from ml-infra's
DevOps V2 agent. Each phase can have:
  - A verification function that checks the output
  - Retry logic for self-correction
  - Rules that constrain the agent's behavior
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


class PhaseStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class VerificationResult:
    """Result of a phase verification check."""

    passed: bool
    errors: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


@dataclass
class WorkflowPhase:
    """Definition of a single workflow phase.

    Attributes:
        name: Unique phase name (e.g. "plan", "generate", "verify").
        description: Human-readable description for the agent's prompt.
        max_retries: Number of self-correction attempts on verification failure.
        verify: Optional async callable that validates the phase output.
            Receives (phase_name, output, state) and returns VerificationResult.
        rules: Domain-specific rules injected into the agent's prompt
            during this phase.
    """

    name: str
    description: str = ""
    max_retries: int = 0
    verify: Optional[Callable[..., Awaitable[VerificationResult]]] = None
    rules: list[str] = field(default_factory=list)


@dataclass
class WorkflowState:
    """Runtime state of a phased workflow."""

    current_phase: str = ""
    phase_statuses: dict[str, PhaseStatus] = field(default_factory=dict)
    phase_outputs: dict[str, Any] = field(default_factory=dict)
    retry_counts: dict[str, int] = field(default_factory=dict)
    files: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return all(
            s == PhaseStatus.COMPLETED
            for s in self.phase_statuses.values()
        )


class PhasedWorkflow:
    """Orchestrates a multi-phase agent workflow.

    Example::

        async def verify_yaml(phase, output, state):
            import yaml
            try:
                yaml.safe_load(output)
                return VerificationResult(passed=True)
            except yaml.YAMLError as e:
                return VerificationResult(passed=False, errors=[str(e)])

        workflow = PhasedWorkflow(
            phases=[
                WorkflowPhase(name="plan", description="Create generation plan"),
                WorkflowPhase(
                    name="generate",
                    description="Generate YAML",
                    verify=verify_yaml,
                    max_retries=2,
                    rules=["All fields must have descriptions"],
                ),
            ],
            seed_files={"template.yaml": "apiVersion: v1\\nkind: ConfigMap"},
        )

        state = workflow.create_state()
        # Use state.files and get_phase_prompt() to drive agent execution
    """

    def __init__(
        self,
        phases: list[WorkflowPhase],
        seed_files: dict[str, str] | None = None,
    ):
        self._phases = {p.name: p for p in phases}
        self._phase_order = [p.name for p in phases]
        self._seed_files = seed_files or {}

    @property
    def phases(self) -> list[WorkflowPhase]:
        return [self._phases[n] for n in self._phase_order]

    def create_state(self) -> WorkflowState:
        """Create initial workflow state with seed files."""
        return WorkflowState(
            current_phase=self._phase_order[0] if self._phase_order else "",
            phase_statuses={
                name: PhaseStatus.PENDING for name in self._phase_order
            },
            files=dict(self._seed_files),
        )

    def get_phase_prompt(self, state: WorkflowState) -> str:
        """Build the prompt augmentation for the current phase.

        Includes phase description, rules, retry context (if retrying),
        and file listing.
        """
        phase = self._phases.get(state.current_phase)
        if not phase:
            return ""

        parts = [f"## Current Phase: {phase.name}"]
        if phase.description:
            parts.append(phase.description)

        if phase.rules:
            parts.append("\n### Rules")
            for rule in phase.rules:
                parts.append(f"- {rule}")

        retries = state.retry_counts.get(phase.name, 0)
        if retries > 0:
            parts.append(f"\n### Retry #{retries}")
            parts.append("Previous attempt had errors:")
            for err in state.errors[-3:]:
                parts.append(f"- {err}")

        if state.files:
            parts.append("\n### Available Files")
            for fname in sorted(state.files):
                parts.append(f"- {fname}")

        return "\n".join(parts)

    async def advance_phase(
        self,
        state: WorkflowState,
        output: Any,
    ) -> WorkflowState:
        """Mark current phase complete (with optional verification) and advance.

        If verification fails and retries remain, the phase stays current
        with status RETRYING.
        """
        phase_name = state.current_phase
        phase = self._phases.get(phase_name)
        if not phase:
            return state

        state.phase_statuses[phase_name] = PhaseStatus.RUNNING
        state.phase_outputs[phase_name] = output

        # Run verification if configured
        if phase.verify:
            try:
                result = await phase.verify(phase_name, output, state)
                if not result.passed:
                    retries = state.retry_counts.get(phase_name, 0)
                    if retries < phase.max_retries:
                        state.retry_counts[phase_name] = retries + 1
                        state.phase_statuses[phase_name] = PhaseStatus.RETRYING
                        state.errors.extend(result.errors)
                        logger.info(
                            "Phase %s verification failed, retry %d/%d",
                            phase_name, retries + 1, phase.max_retries,
                        )
                        return state
                    else:
                        state.phase_statuses[phase_name] = PhaseStatus.FAILED
                        state.errors.extend(result.errors)
                        logger.warning("Phase %s failed after %d retries", phase_name, retries)
                        return state
            except Exception:
                logger.exception("Verification error in phase %s", phase_name)

        state.phase_statuses[phase_name] = PhaseStatus.COMPLETED

        # Advance to next phase
        idx = self._phase_order.index(phase_name)
        if idx + 1 < len(self._phase_order):
            state.current_phase = self._phase_order[idx + 1]
        else:
            state.current_phase = ""

        return state
