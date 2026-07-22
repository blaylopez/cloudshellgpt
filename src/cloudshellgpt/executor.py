"""AWS executor — runs commands via subprocess with safety controls."""
from __future__ import annotations

import shlex
import subprocess
import time
from dataclasses import dataclass


@dataclass
class ExecutionResult:
    """Result of an AWS command execution."""

    command: str
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    dry_run: bool = False
    error: str | None = None


class AWSExecutor:
    """Executes AWS CLI commands in a controlled manner.

    Features:
    - Timeout enforcement
    - Streaming output
    - Dry-run injection
    - Error capture and classification
    """

    DEFAULT_TIMEOUT = 30  # seconds
    STREAM_CHUNK_SIZE = 4096

    def __init__(self, dry_run: bool = False, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.dry_run = dry_run
        self.timeout = timeout

    def run(self, command: str) -> ExecutionResult:
        """Execute an AWS CLI command.

        Args:
            command: The full AWS CLI command string

        Returns:
            ExecutionResult with stdout, stderr, exit code, etc.
        """
        start = time.time()

        # Inject dry-run if needed
        effective_command = self._inject_dry_run(command) if self.dry_run else command

        try:
            # Use shlex to safely split the command
            args = shlex.split(effective_command)

            # Validate it's actually an AWS command
            if not args or args[0] != "aws":
                return ExecutionResult(
                    command=effective_command,
                    stdout="",
                    stderr="Refusing to execute non-AWS command",
                    exit_code=1,
                    duration_ms=0,
                    error="Security: command must start with 'aws'",
                )

            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )

            duration_ms = int((time.time() - start) * 1000)

            return ExecutionResult(
                command=effective_command,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                duration_ms=duration_ms,
                dry_run=self.dry_run,
            )

        except subprocess.TimeoutExpired:
            duration_ms = int((time.time() - start) * 1000)
            return ExecutionResult(
                command=effective_command,
                stdout="",
                stderr=f"Command timed out after {self.timeout}s",
                exit_code=124,
                duration_ms=duration_ms,
                error="timeout",
            )
        except FileNotFoundError:
            return ExecutionResult(
                command=effective_command,
                stdout="",
                stderr="AWS CLI not found. Install it: https://aws.amazon.com/cli/",
                exit_code=127,
                duration_ms=0,
                error="aws_cli_missing",
            )
        except Exception as e:
            return ExecutionResult(
                command=effective_command,
                stdout="",
                stderr=str(e),
                exit_code=1,
                duration_ms=0,
                error=type(e).__name__,
            )

    def _inject_dry_run(self, command: str) -> str:
        """Inject --dry-run flag into commands that support it.

        Some AWS commands don't support --dry-run, in which case we
        add a comment to make it clear this is a simulation.
        """
        # Commands that natively support --dry-run
        dry_run_supported = [
            "ec2 run-instances",
            "ec2 terminate-instances",
            "ec2 delete-volume",
            "rds delete-db-instance",
            "s3api delete-bucket",
            "iam delete-user",
        ]

        for pattern in dry_run_supported:
            if pattern in command:
                return command + " --dry-run"

        # Fallback: prefix with a comment marker
        return f"# DRY-RUN (no --dry-run support for this command):\n{command}"
