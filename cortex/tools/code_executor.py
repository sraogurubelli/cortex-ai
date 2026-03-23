"""
Code Execution Sandbox tool.

Provides a secure way for agents to execute Python code.
Supports two backends:
  - **E2B** (cloud sandbox): preferred for production.
  - **subprocess** (local): fallback when E2B is unavailable.

Environment variables:
  - ``CORTEX_E2B_API_KEY``: Enables E2B backend.
  - ``CORTEX_CODE_EXEC_TIMEOUT``: Max execution time in seconds (default 30).

Usage::

    from cortex.tools.code_executor import create_code_execution_tool

    tool = create_code_execution_tool()
    # Attach to an agent's tool list
"""

import asyncio
import logging
import os
import subprocess
import sys
import tempfile
from typing import Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30


class CodeExecutionInput(BaseModel):
    """Input schema for the code execution tool."""

    code: str = Field(description="Python code to execute")
    language: str = Field(default="python", description="Programming language (only python supported)")


class CodeExecutionResult(BaseModel):
    """Result of code execution."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    error: str = ""
    artifacts: list[str] = []


async def _run_e2b(code: str, api_key: str, timeout: int) -> CodeExecutionResult:
    """Execute code using E2B Code Interpreter SDK."""
    try:
        from e2b_code_interpreter import AsyncSandbox

        sandbox = await AsyncSandbox.create(api_key=api_key, timeout=timeout)
        try:
            execution = await sandbox.run_code(code)
            stdout_parts = []
            stderr_parts = []
            artifacts = []

            for log in execution.logs.stdout:
                stdout_parts.append(str(log))
            for log in execution.logs.stderr:
                stderr_parts.append(str(log))

            if execution.results:
                for r in execution.results:
                    if hasattr(r, "png") and r.png:
                        artifacts.append(f"[chart: {len(r.png)} bytes base64 PNG]")
                    elif hasattr(r, "text") and r.text:
                        stdout_parts.append(str(r.text))

            return CodeExecutionResult(
                stdout="\n".join(stdout_parts),
                stderr="\n".join(stderr_parts),
                exit_code=0 if not execution.error else 1,
                error=str(execution.error) if execution.error else "",
                artifacts=artifacts,
            )
        finally:
            await sandbox.kill()
    except ImportError:
        return CodeExecutionResult(
            exit_code=1,
            error="e2b_code_interpreter not installed. pip install e2b-code-interpreter",
        )
    except Exception as e:
        return CodeExecutionResult(exit_code=1, error=str(e))


async def _run_subprocess(code: str, timeout: int) -> CodeExecutionResult:
    """Execute code in a local subprocess (sandboxed via temp file)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        tmp_path = f.name

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, tmp_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            return CodeExecutionResult(
                exit_code=137,
                error=f"Execution timed out after {timeout}s",
            )

        return CodeExecutionResult(
            stdout=stdout.decode(errors="replace"),
            stderr=stderr.decode(errors="replace"),
            exit_code=proc.returncode or 0,
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


async def execute_code(code: str, language: str = "python") -> str:
    """Execute code and return formatted result string."""
    if language != "python":
        return f"Error: Only Python execution is supported, got: {language}"

    timeout = int(os.environ.get("CORTEX_CODE_EXEC_TIMEOUT", _DEFAULT_TIMEOUT))
    e2b_key = os.environ.get("CORTEX_E2B_API_KEY")

    if e2b_key:
        result = await _run_e2b(code, e2b_key, timeout)
    else:
        result = await _run_subprocess(code, timeout)

    parts: list[str] = []
    if result.stdout:
        parts.append(f"Output:\n{result.stdout}")
    if result.stderr:
        parts.append(f"Stderr:\n{result.stderr}")
    if result.error:
        parts.append(f"Error:\n{result.error}")
    if result.artifacts:
        parts.append(f"Artifacts: {', '.join(result.artifacts)}")
    if not parts:
        parts.append("(no output)")
    if result.exit_code != 0:
        parts.append(f"Exit code: {result.exit_code}")

    return "\n".join(parts)


def create_code_execution_tool() -> StructuredTool:
    """Create a LangChain tool for code execution."""
    return StructuredTool.from_function(
        coroutine=_tool_fn,
        name="execute_python_code",
        description=(
            "Execute Python code in a secure sandbox. "
            "Use this to run calculations, process data, generate charts, "
            "or test code snippets. Returns stdout, stderr, and any artifacts."
        ),
        args_schema=CodeExecutionInput,
    )


async def _tool_fn(code: str, language: str = "python") -> str:
    return await execute_code(code, language)
