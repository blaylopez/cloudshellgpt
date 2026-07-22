"""Output formatter — renders results in multiple formats (table, json, yaml, csv)."""
from __future__ import annotations

import json
import sys
from typing import Literal

import yaml
from rich.console import Console
from rich.table import Table

from cloudshellgpt.executor import ExecutionResult

FormatType = Literal["table", "json", "yaml", "csv", "raw"]


class Formatter:
    """Formats execution results for human or machine consumption."""

    def __init__(self, format_type: FormatType = "table") -> None:
        self.format_type = format_type
        self.console = Console()

    def render(self, result: ExecutionResult) -> None:
        """Render an ExecutionResult in the configured format.

        Args:
            result: The execution result to format
        """
        if result.exit_code != 0:
            self._render_error(result)
            return

        formatter = {
            "table": self._render_table,
            "json": self._render_json,
            "yaml": self._render_yaml,
            "csv": self._render_csv,
            "raw": self._render_raw,
        }.get(self.format_type, self._render_table)

        formatter(result)

    def _render_table(self, result: ExecutionResult) -> None:
        """Render as a Rich table (best for human consumption)."""
        parsed = self._try_parse_json(result.stdout)

        if isinstance(parsed, list) and parsed:
            # Render list of dicts as a table
            first = parsed[0]
            if isinstance(first, dict):
                table = Table(show_header=True, header_style="bold cyan")
                for key in first.keys():
                    table.add_column(str(key))

                for item in parsed[:50]:  # Limit rows
                    row = [str(item.get(k, "")) for k in first.keys()]
                    table.add_row(*row)

                self.console.print(table)
                if len(parsed) > 50:
                    self.console.print(f"[dim]... and {len(parsed) - 50} more[/dim]")
                return

        # Fallback to raw output
        self._render_raw(result)

    def _render_json(self, result: ExecutionResult) -> None:
        """Render as pretty JSON."""
        parsed = self._try_parse_json(result.stdout)
        if parsed is not None:
            self.console.print_json(json.dumps(parsed, indent=2, default=str))
        else:
            self.console.print(result.stdout)

    def _render_yaml(self, result: ExecutionResult) -> None:
        """Render as YAML."""
        parsed = self._try_parse_json(result.stdout)
        if parsed is not None:
            self.console.print(yaml.dump(parsed, default_flow_style=False))
        else:
            self.console.print(result.stdout)

    def _render_csv(self, result: ExecutionResult) -> None:
        """Render as CSV."""
        import csv
        import io

        parsed = self._try_parse_json(result.stdout)
        if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=parsed[0].keys())
            writer.writeheader()
            writer.writerows(parsed)
            self.console.print(output.getvalue())
        else:
            self.console.print(result.stdout)

    def _render_raw(self, result: ExecutionResult) -> None:
        """Render as plain text."""
        self.console.print(result.stdout)

    def _render_error(self, result: ExecutionResult) -> None:
        """Render an error result with context."""
        self.console.print(f"[red]✗ Command failed (exit {result.exit_code})[/red]")
        if result.error:
            self.console.print(f"[dim]Error: {result.error}[/dim]")
        if result.stderr:
            self.console.print(f"[yellow]{result.stderr}[/yellow]")

    def _try_parse_json(self, text: str) -> object | None:
        """Try to parse text as JSON, return None if not valid."""
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return None
