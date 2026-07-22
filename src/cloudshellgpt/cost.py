"""Cost tracker — tracks estimated costs of resources created during a session."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import yaml
from rich.console import Console
from rich.panel import Panel


class CostTracker:
    """Tracks estimated AWS costs of resources created in a session."""

    DEFAULT_PATH = Path.home() / ".csgpt" / "session_costs.yaml"

    def __init__(self, session_path: Path | None = None) -> None:
        self.session_path = session_path or self.DEFAULT_PATH
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        self.console = Console()

    def track(self, command: str, estimated_cost: str) -> None:
        """Track a new cost item."""
        costs = self._load()
        costs.append(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "command": command[:200],  # Truncate
                "estimated_cost": estimated_cost,
            }
        )
        self._save(costs)

    def session_summary(self) -> str:
        """Return a human-readable summary of session costs."""
        costs = self._load()
        if not costs:
            return "[dim]No costs tracked in this session.[/dim]"

        lines = [f"[bold]Session costs ({len(costs)} operations):[/bold]\n"]
        for c in costs:
            lines.append(f"  • {c['estimated_cost']:>10} — {c['command'][:80]}")

        return "\n".join(lines)

    def _load(self) -> list[dict]:
        """Load costs from disk."""
        if not self.session_path.exists():
            return []
        with self.session_path.open() as f:
            data = yaml.safe_load(f) or []
        return data

    def _save(self, costs: list[dict]) -> None:
        """Save costs to disk."""
        with self.session_path.open("w") as f:
            yaml.safe_dump(costs, f, default_flow_style=False)

    def clear(self) -> None:
        """Clear the session cost log."""
        if self.session_path.exists():
            self.session_path.unlink()
