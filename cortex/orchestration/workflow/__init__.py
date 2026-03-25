"""
Phased Workflow — structured multi-step agent workflow pattern.

Ported from ml-infra's DevOps V2 agent architecture. Enables
complex workflows with:
  - Virtual filesystem seeding (pre-populate files for the agent)
  - Phase tracking (plan → generate → verify → fix)
  - Verification/self-correction loops
  - Rules injection (domain-specific constraints)

Usage::

    from cortex.orchestration.workflow import (
        PhasedWorkflow,
        WorkflowPhase,
        VerificationResult,
    )

    workflow = PhasedWorkflow(
        phases=[
            WorkflowPhase(name="plan", description="Create a plan"),
            WorkflowPhase(name="generate", description="Generate output"),
            WorkflowPhase(
                name="verify",
                description="Verify output",
                max_retries=2,
            ),
        ],
        seed_files={"requirements.txt": "flask>=2.0\\nrequests"},
    )
"""

from cortex.orchestration.workflow.phased import (
    PhasedWorkflow,
    VerificationResult,
    WorkflowPhase,
    WorkflowState,
)

__all__ = [
    "PhasedWorkflow",
    "WorkflowPhase",
    "WorkflowState",
    "VerificationResult",
]
