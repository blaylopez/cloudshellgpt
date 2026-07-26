"""Audit logger — records all command intents and results for compliance and debugging."""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from cloudshellgpt.executor import ExecutionResult


class AuditLogger:
    """Logs command intents BEFORE execution and results AFTER.

    Critical safety invariant: logging must happen BEFORE execution so that
    even if the process crashes mid-execution, we have a record of what was
    attempted.

    Format: JSON Lines (one JSON object per line)
    Default location: ~/.csgpt/audit.log

    Never-crash guarantee: all public methods catch all exceptions internally
    and never propagate them to the caller.
    """

    DEFAULT_PATH = Path.home() / ".csgpt" / "audit.log"

    def __init__(self, log_path: Path | None = None) -> None:
        """Initialize the audit logger.

        Args:
            log_path: Custom path for the audit log file. Defaults to ~/.csgpt/audit.log.
        """
        self.log_path = log_path or self.DEFAULT_PATH
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    def log_before(
        self,
        intent: str,
        command: str,
        risk: str,
        dry_run: bool,
    ) -> str | None:
        """Log a command intent BEFORE execution.

        This is the primary safety mechanism: the audit entry is written before
        the command runs, ensuring we have a record even if the process crashes.

        Args:
            intent: The original natural language intent.
            command: The AWS command about to be executed.
            risk: Risk level (low/medium/high/critical).
            dry_run: Whether this will be a dry-run execution.

        Returns:
            A unique entry_id that can be used to correlate with log_after,
            or None if logging failed silently.
        """
        entry_id = uuid.uuid4().hex
        entry: dict[str, object] = {
            "entry_id": entry_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "phase": "before",
            "intent": intent,
            "command": command,
            "risk_level": risk,
            "dry_run": dry_run,
            "user": os.environ.get("USER", os.environ.get("USERNAME", "unknown")),
        }

        try:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            return None

        return entry_id

    def log_after(
        self,
        entry_id: str | None,
        result: ExecutionResult,
    ) -> None:
        """Log execution results AFTER a command completes.

        This appends a second log line correlating with the pre-execution entry
        via entry_id, recording the outcome.

        Args:
            entry_id: The id returned by log_before (may be None if pre-log failed).
            result: The execution result to record.
        """
        entry: dict[str, object] = {
            "entry_id": entry_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "phase": "after",
            "command": result.command,
            "exit_code": result.exit_code,
            "duration_ms": result.duration_ms,
            "dry_run": result.dry_run,
            "stdout_size": len(result.stdout),
            "stderr": result.stderr if result.exit_code != 0 else None,
            "error": result.error,
        }

        try:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass

    def log(
        self,
        intent: str,
        command: str,
        risk: str,
        dry_run: bool,
        result: ExecutionResult | None = None,
    ) -> None:
        """Convenience method: log intent and optionally a result in one call.

        Backwards-compatible with callers that want a single log() call.
        When result is None, only the pre-execution entry is written.

        Args:
            intent: The original natural language intent.
            command: The executed AWS command.
            risk: Risk level (low/medium/high/critical).
            dry_run: Whether this was a dry-run.
            result: The execution result (optional, for post-execution logging).
        """
        entry_id = self.log_before(intent, command, risk, dry_run)
        if result is not None:
            self.log_after(entry_id, result)

    def tail(self, n: int = 10) -> list[dict[str, object]]:
        """Return the last N entries from the log.

        Args:
            n: Number of entries to return. Defaults to 10.

        Returns:
            List of log entry dictionaries, most recent last.
        """
        try:
            if not self.log_path.exists():
                return []

            entries: list[dict[str, object]] = []
            with self.log_path.open("r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

            return entries[-n:]
        except OSError:
            return []

    def clear(self) -> None:
        """Clear the audit log.

        Silently ignores errors if the file cannot be deleted.
        """
        try:
            if self.log_path.exists():
                self.log_path.unlink()
        except OSError:
            pass
