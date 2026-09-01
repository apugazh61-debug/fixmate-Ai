"""
Docker-based sandbox execution and verification.

Runs code inside a throwaway container (`python:3.12-slim`) with a hard
timeout and no network access, capturing stdout/stderr/exit code.

If Docker is not installed or the daemon is not running on the host,
all functions degrade gracefully and report `is_available() == False`
with a clear reason — never raising unhandled exceptions.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


DEFAULT_IMAGE = "python:3.12-slim"
DEFAULT_TIMEOUT = 5


@dataclass
class SandboxRunResult:
    """Output from executing a single code snippet in Docker."""
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    error: str = ""

    @property
    def combined_output(self) -> str:
        out = self.stdout.strip()
        err = self.stderr.strip()
        if out and err:
            return f"{out}\n{err}"
        return out or err or (self.error if not self.success else "(no output)")


@dataclass
class VerificationResult:
    """Comparison of execution between original (broken) and fixed code."""
    before_ok: bool
    after_ok: bool
    before_output: str
    after_output: str
    error: str = ""
    runs_executed: bool = False


class DockerUnavailable(RuntimeError):
    """Raised or reported when Docker cannot be used."""


def get_availability_status() -> tuple[bool, str]:
    """Check if Docker is installed and the daemon is reachable."""
    docker_bin = shutil.which("docker")
    if not docker_bin:
        return False, "Docker CLI not found in PATH."

    try:
        proc = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if proc.returncode == 0:
            return True, "Docker daemon is running and reachable."
        err_msg = proc.stderr.strip() or "Docker daemon is not running."
        # Keep message clean and short
        first_line = err_msg.splitlines()[0] if err_msg else "Docker daemon unreachable."
        return False, f"Docker daemon not running: {first_line}"
    except subprocess.TimeoutExpired:
        return False, "Docker daemon connection timed out."
    except Exception as exc:  # noqa: BLE001
        return False, f"Docker check failed: {exc}"


def is_available() -> bool:
    """Returns True only if Docker is installed and the daemon is responding."""
    available, _ = get_availability_status()
    return available


def run_in_sandbox(
    code: str,
    timeout: int = DEFAULT_TIMEOUT,
    image: str = DEFAULT_IMAGE,
) -> SandboxRunResult:
    """Run a Python snippet inside a throwaway container with no network.
    
    Returns a SandboxRunResult. Never raises exceptions.
    """
    available, reason = get_availability_status()
    if not available:
        return SandboxRunResult(
            success=False,
            exit_code=-1,
            stdout="",
            stderr="",
            error=reason,
        )

    try:
        proc = subprocess.run(
            ["docker", "run", "--rm", "-i", "--network", "none", image, "python3", "-"],
            input=code,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return SandboxRunResult(
            success=(proc.returncode == 0),
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            error="",
        )
    except subprocess.TimeoutExpired:
        return SandboxRunResult(
            success=False,
            exit_code=-1,
            stdout="",
            stderr=f"Execution timed out after {timeout}s.",
            timed_out=True,
            error=f"Timeout ({timeout}s)",
        )
    except Exception as exc:  # noqa: BLE001
        return SandboxRunResult(
            success=False,
            exit_code=-1,
            stdout="",
            stderr="",
            error=f"Sandbox error: {exc}",
        )


def verify_fix_in_sandbox(
    original_code: str,
    fixed_code: str,
    timeout: int = DEFAULT_TIMEOUT,
    image: str = DEFAULT_IMAGE,
) -> VerificationResult:
    """Execute both original and fixed code in sandbox to verify behavior.
    
    Gracefully returns error in VerificationResult if Docker is unavailable.
    """
    available, reason = get_availability_status()
    if not available:
        return VerificationResult(
            before_ok=False,
            after_ok=False,
            before_output="",
            after_output="",
            error=reason,
            runs_executed=False,
        )

    before_res = run_in_sandbox(original_code, timeout=timeout, image=image)
    after_res = run_in_sandbox(fixed_code, timeout=timeout, image=image)

    return VerificationResult(
        before_ok=before_res.success,
        after_ok=after_res.success,
        before_output=before_res.combined_output,
        after_output=after_res.combined_output,
        error="",
        runs_executed=True,
    )
