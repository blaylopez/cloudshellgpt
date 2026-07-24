"""Audit logger — records all executed commands for compliance and debugging."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from cloudshellgpt.executor import ExecutionResult


class AuditLogger:
    """Logs all command executions to a local file.

    Format: JSON Lines (one JSON object per line)
    Default location: ~/.csgpt/audit.log
    """

    DEFAULT_PATH = Path.home() / ".csgpt" / "audit.log"

    def __init__(self, log_path: Path | None = None) -> None:
        self.log_path = log_path or self.DEFAULT_PATH
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        intent: str,
        command: str,
        risk: str,
        dry_run: bool,
        result: ExecutionResult,
    ) -> None:
        """Log a command execution.

        Args:
            intent: The original natural language intent
            command: The executed AWS command
            risk: Risk level (low/medium/high/critical)
            dry_run: Whether this was a dry-run
            result: The execution result
        """
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "intent": intent,
            "command": command,
            "risk_level": risk,
            "dry_run": dry_run,
            "exit_code": result.exit_code,
            "duration_ms": result.duration_ms,
            "stdout_size": len(result.stdout),
            "stderr": result.stderr if result.exit_code != 0 else None,
            "user": os.environ.get("USER", "unknown"),
        }

        try:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            # Never fail the user-facing operation due to logging issues
            pass

    def tail(self, n: int = 10) -> list[dict[str, object]]:
        """Return the last N entries from the log."""
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

    def clear(self) -> None:
        """Clear the audit log."""
        if self.log_path.exists():
            self.log_path.unlink()
