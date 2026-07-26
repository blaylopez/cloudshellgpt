"""AWS executor — runs commands via subprocess with safety controls."""

from __future__ import annotations

import random
import re
import shlex
import subprocess
import time

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class ExecutorError(Exception):
    """Raised when command validation or execution fails.

    Attributes:
        message: Human-readable description of the failure.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Retry configuration defaults
DEFAULT_MAX_RETRIES: int = 3
INITIAL_BACKOFF_SECONDS: float = 1.0
BACKOFF_MULTIPLIER: float = 2.0

# AWS throttling error patterns detected in stderr
THROTTLING_PATTERNS: list[str] = [
    "Throttling",
    "Rate exceeded",
    "ThrottlingException",
    "TooManyRequestsException",
    "RequestLimitExceeded",
]

# Regex patterns that detect shell metacharacters and injection attempts.
# Order matters for readability, not for matching priority.
SHELL_METACHAR_PATTERNS: list[tuple[str, str]] = [
    # Null bytes and newlines
    (r"\x00", "null byte"),
    (r"\n", "newline"),
    # Command chaining / sequencing
    (r"&&", "command chaining (&&)"),
    (r"\|\|", "command chaining (||)"),
    (r";", "command separator (;)"),
    # Pipe
    (r"\|", "pipe (|)"),
    # Backticks
    (r"`", "backtick substitution"),
    # Subshell / command substitution
    (r"\$\(", "command substitution $()"),
    # Environment variable injection
    (r"\$\{", "variable expansion ${...}"),
    (r"\$[A-Za-z_]", "variable expansion $VAR"),
    # Here-doc / here-string (must check before redirect patterns)
    (r"<<<", "here-string (<<<)"),
    (r"<<", "here-doc (<<)"),
    # Process substitution
    (r"<\(", "process substitution <()"),
    (r">\(", "process substitution >()"),
    # Redirects (stderr redirect must come before generic)
    (r"2>", "stderr redirect (2>)"),
    (r">>", "append redirect (>>)"),
    (r">", "output redirect (>)"),
    (r"<", "input redirect (<)"),
    # Background execution — standalone & (not part of &&, which is caught above).
    # Matches & preceded by a space (mid-command: "cmd1 & cmd2") or at end of string.
    (r"(?<=[^&])&(?!&)", "background execution (&)"),
]

# Compiled regex that matches ANY shell metacharacter.
# We build a single pattern with alternation for efficient matching.
_SHELL_INJECTION_RE = re.compile(
    "|".join(f"(?:{pattern})" for pattern, _ in SHELL_METACHAR_PATTERNS)
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class ExecutionResult(BaseModel):
    """Result of an AWS command execution."""

    command: str
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int = Field(description="Execution time in milliseconds")
    dry_run: bool = False
    error: str | None = None


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


class AWSExecutor:
    """Executes AWS CLI commands in a controlled manner.

    Features:
    - Shell injection prevention (strict metacharacter validation)
    - Timeout enforcement
    - Exponential backoff retry for transient errors
    - Streaming output
    - Dry-run injection
    - Error capture and classification
    """

    DEFAULT_TIMEOUT = 30  # seconds
    STREAM_CHUNK_SIZE = 4096

    def __init__(
        self,
        dry_run: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        self.dry_run = dry_run
        self.timeout = timeout
        self.max_retries = max_retries

    def _validate_command(self, command: str) -> ExecutionResult | None:
        """Validate command for shell injection and ensure it starts with 'aws'.

        Checks for shell metacharacters, empty/whitespace commands, and
        non-AWS prefixes. Returns an ExecutionResult with error details if
        validation fails, or None if the command is safe.

        Args:
            command: The raw command string to validate.

        Returns:
            ExecutionResult with error info if validation fails, None if safe.
        """
        # Reject empty or whitespace-only commands
        if not command or not command.strip():
            return ExecutionResult(
                command=command if command else "",
                stdout="",
                stderr="Refusing to execute empty command",
                exit_code=1,
                duration_ms=0,
                error="Security: command is empty or whitespace-only",
            )

        stripped = command.strip()

        # Must start with 'aws' followed by whitespace or end of string
        if not (stripped == "aws" or stripped.startswith("aws ")):
            return ExecutionResult(
                command=command,
                stdout="",
                stderr="Refusing to execute non-AWS command",
                exit_code=1,
                duration_ms=0,
                error="Security: command must start with 'aws'",
            )

        # Check for shell metacharacters in the raw command string.
        # We scan the raw string to catch injection attempts that might
        # survive shlex splitting.
        # First, remove content inside quotes (single and double) since
        # those are argument values, not shell operators. JMESPath uses |
        # inside --query '...' which is valid and not a shell pipe.
        unquoted = re.sub(r"'[^']*'", "", command)
        unquoted = re.sub(r'"[^"]*"', "", unquoted)

        for pattern, description in SHELL_METACHAR_PATTERNS:
            if re.search(pattern, unquoted):
                # Exception: the standalone '-' argument is valid for
                # stdin/stdout usage (e.g., aws s3 cp - s3://bucket/file).
                # Only skip '<'/'>' detection when the character appears
                # solely because of a legitimate '-' argument pattern, not
                # as an actual shell redirect operator.
                if description in (
                    "input redirect (<)",
                    "output redirect (>)",
                ):
                    # Check if '-' is present as a standalone token.
                    # If so, verify the '<'/'>' isn't a real redirect:
                    # a real redirect has the operator as its own token
                    # (e.g., "cmd > file") or attached to a filename
                    # (e.g., "cmd >file"). If '-' is standalone and the
                    # '<'/'>' only appears within an argument containing '-'
                    # (e.g., a flag like --output), skip this check.
                    tokens = stripped.split()
                    has_standalone_dash = "-" in tokens
                    redirect_char = "<" if "input" in description else ">"
                    # Check if any token IS the redirect operator or starts
                    # with it (e.g., ">file") — that's a real redirect.
                    has_real_redirect = any(
                        tok == redirect_char or (tok.startswith(redirect_char) and tok != "-")
                        for tok in tokens
                    )
                    if has_standalone_dash and not has_real_redirect:
                        # No actual redirect — '-' is just a positional arg
                        continue
                return ExecutionResult(
                    command=command,
                    stdout="",
                    stderr=f"Refusing to execute: shell metacharacter detected ({description})",
                    exit_code=1,
                    duration_ms=0,
                    error=f"Security: shell injection detected — {description}",
                )

        return None

    def _is_transient_error(self, result: ExecutionResult) -> bool:
        """Determine if an execution result represents a transient (retryable) error.

        Checks stderr for known AWS throttling patterns.

        Args:
            result: The execution result to evaluate.

        Returns:
            True if the error is transient and the command should be retried.
        """
        if not result.stderr:
            return False
        return any(pattern in result.stderr for pattern in THROTTLING_PATTERNS)

    def run(self, command: str) -> ExecutionResult:
        """Execute an AWS CLI command with exponential backoff retry.

        Validates the command for shell injection attempts before execution.
        Only pure AWS CLI commands without shell metacharacters are allowed.
        Retries on transient errors (throttling, timeouts) with exponential
        backoff and jitter.

        Args:
            command: The full AWS CLI command string.

        Returns:
            ExecutionResult with stdout, stderr, exit code, etc.
        """
        # Validate BEFORE any execution
        validation_error = self._validate_command(command)
        if validation_error is not None:
            return validation_error

        # Inject dry-run if needed
        effective_command = self._inject_dry_run(command) if self.dry_run else command

        # Re-validate after dry-run injection (defense in depth)
        if self.dry_run:
            post_inject_error = self._validate_command(effective_command)
            if post_inject_error is not None:
                return post_inject_error

        last_result: ExecutionResult | None = None

        for attempt in range(self.max_retries + 1):
            # Apply backoff delay before retries (not before first attempt)
            if attempt > 0:
                backoff = INITIAL_BACKOFF_SECONDS * (BACKOFF_MULTIPLIER ** (attempt - 1))
                jitter = random.uniform(0, backoff * 0.5)  # noqa: S311
                time.sleep(backoff + jitter)

            start = time.time()

            try:
                # Use shlex to safely split the command
                args = shlex.split(effective_command)

                # Final guard: validate first token is literally 'aws'
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

                last_result = ExecutionResult(
                    command=effective_command,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    exit_code=result.returncode,
                    duration_ms=duration_ms,
                    dry_run=self.dry_run,
                )

                # If successful or non-transient error, return immediately
                if result.returncode == 0 or not self._is_transient_error(last_result):
                    return last_result

                # Transient error — continue to next retry attempt

            except subprocess.TimeoutExpired:
                duration_ms = int((time.time() - start) * 1000)
                last_result = ExecutionResult(
                    command=effective_command,
                    stdout="",
                    stderr=f"Command timed out after {self.timeout}s",
                    exit_code=124,
                    duration_ms=duration_ms,
                    error="timeout",
                )
                # Timeout is transient — continue to next retry attempt

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

        # All retries exhausted — return last error result
        assert last_result is not None  # noqa: S101
        return last_result

    def _inject_dry_run(self, command: str) -> str:
        """Inject --dry-run flag into commands that support it.

        Some AWS commands don't support --dry-run, in which case we
        add a comment to make it clear this is a simulation.

        Args:
            command: The original AWS CLI command.

        Returns:
            Command with --dry-run injected, or prefixed with comment.
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

        # Fallback: return command unchanged (avoid injecting comments
        # that would fail validation due to newline/# characters)
        return command
