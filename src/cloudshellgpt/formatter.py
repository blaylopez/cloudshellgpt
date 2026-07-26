"""Output formatter — renders results in multiple formats (table, json, yaml, csv).

Supports TTY auto-detection, Rich panels/progress, and multi-format output.
When stdout is not a TTY (piped), outputs plain JSON without colors.
"""

from __future__ import annotations

import csv
import io
import json
import sys
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, Literal

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from cloudshellgpt.executor import ExecutionResult

FormatType = Literal["table", "json", "yaml", "csv", "raw"]

# ---------------------------------------------------------------------------
# Mensajes de error en español (humanizados)
# ---------------------------------------------------------------------------

ERROR_MESSAGES: dict[str, str] = {
    "command_failed": "El comando falló con código de salida {exit_code}",
    "command_failed_detail": "Detalle: {error}",
    "stderr_output": "Salida de error del proceso:",
    "suggestion_check_credentials": (
        "Sugerencia: Verifica tus credenciales de AWS y permisos IAM."
    ),
    "suggestion_check_syntax": (
        "Sugerencia: Revisa la sintaxis del comando o ejecuta con --dry-run primero."
    ),
    "suggestion_check_region": ("Sugerencia: Confirma que la región configurada es correcta."),
    "dry_run_label": "Simulación (dry-run)",
    "executed_label": "Ejecutado",
    "duration_label": "Duración",
    "command_label": "Comando",
    "executing_label": "Ejecutando comando AWS...",
}


# ---------------------------------------------------------------------------
# Formatter
# ---------------------------------------------------------------------------


class Formatter:
    """Formats execution results for human or machine consumption.

    Auto-detects whether stdout is a TTY. When piped (no TTY), outputs plain
    JSON without Rich formatting or colors to support scripting workflows.

    Args:
        format_type: Output format to use (table, json, yaml, csv, raw).
        force_tty: Override TTY detection (useful for testing).
    """

    def __init__(
        self,
        format_type: FormatType = "table",
        force_tty: bool | None = None,
    ) -> None:
        self.format_type = format_type
        self._is_tty = force_tty if force_tty is not None else sys.stdout.isatty()
        self.console = Console(
            force_terminal=self._is_tty,
            no_color=not self._is_tty,
        )

    @property
    def is_tty(self) -> bool:
        """Whether the output is going to an interactive terminal."""
        return self._is_tty

    def render(self, result: ExecutionResult) -> None:
        """Render an ExecutionResult in the configured format.

        When not a TTY, always outputs plain JSON regardless of configured format.

        Args:
            result: The execution result to format.
        """
        if not self._is_tty:
            self._render_plain_json(result)
            return

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

    @contextmanager
    def progress_spinner(self, message: str | None = None) -> Generator[None, None, None]:
        """Context manager that shows a Rich spinner while work is in progress.

        Only displays the spinner when output is a TTY. In non-TTY mode,
        this is a no-op to avoid polluting piped output.

        Args:
            message: Optional message to display alongside the spinner.

        Yields:
            None — use as a context manager around long-running operations.
        """
        label = message or ERROR_MESSAGES["executing_label"]

        if not self._is_tty:
            yield
            return

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            console=self.console,
            transient=True,
        ) as progress:
            progress.add_task(label, total=None)
            yield

    # ------------------------------------------------------------------
    # TTY renderers (Rich formatting)
    # ------------------------------------------------------------------

    def _render_table(self, result: ExecutionResult) -> None:
        """Render as a Rich table wrapped in an info panel."""
        parsed = self._try_parse_json(result.stdout)

        if isinstance(parsed, list) and parsed:
            first = parsed[0]
            if isinstance(first, dict):
                table = Table(show_header=True, header_style="bold cyan")
                for key in first.keys():
                    table.add_column(str(key))

                for item in parsed[:50]:
                    row = [str(item.get(k, "")) for k in first.keys()]
                    table.add_row(*row)

                panel = self._build_info_panel(result, table)
                self.console.print(panel)

                if len(parsed) > 50:
                    self.console.print(f"[dim]... y {len(parsed) - 50} más[/dim]")
                return

        # Fallback: wrap raw output in panel
        panel = self._build_info_panel(result, Text(result.stdout))
        self.console.print(panel)

    def _render_json(self, result: ExecutionResult) -> None:
        """Render as pretty-printed JSON with syntax highlighting."""
        parsed = self._try_parse_json(result.stdout)
        if parsed is not None:
            self.console.print_json(json.dumps(parsed, indent=2, default=str))
        else:
            self.console.print(result.stdout)

    def _render_yaml(self, result: ExecutionResult) -> None:
        """Render as YAML output."""
        parsed = self._try_parse_json(result.stdout)
        if parsed is not None:
            output = yaml.dump(parsed, default_flow_style=False, allow_unicode=True)
            self.console.print(output)
        else:
            self.console.print(result.stdout)

    def _render_csv(self, result: ExecutionResult) -> None:
        """Render as CSV output."""
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
        """Render as plain text without extra formatting."""
        self.console.print(result.stdout)

    # ------------------------------------------------------------------
    # Non-TTY renderer (plain JSON for piping)
    # ------------------------------------------------------------------

    def _render_plain_json(self, result: ExecutionResult) -> None:
        """Output plain JSON without colors for non-TTY contexts (pipes, scripts).

        Args:
            result: The execution result to serialize.
        """
        data: dict[str, Any] = {
            "command": result.command,
            "exit_code": result.exit_code,
            "duration_ms": result.duration_ms,
            "dry_run": result.dry_run,
        }

        if result.exit_code == 0:
            parsed = self._try_parse_json(result.stdout)
            data["output"] = parsed if parsed is not None else result.stdout
        else:
            data["error"] = result.error
            data["stderr"] = result.stderr

        print(json.dumps(data, indent=2, default=str, ensure_ascii=False))

    # ------------------------------------------------------------------
    # Error rendering (Spanish, humanized)
    # ------------------------------------------------------------------

    def _render_error(self, result: ExecutionResult) -> None:
        """Render an error result with context and suggestions in Spanish.

        Args:
            result: The failed execution result.
        """
        title = ERROR_MESSAGES["command_failed"].format(exit_code=result.exit_code)

        error_parts: list[str] = []

        if result.error:
            error_parts.append(ERROR_MESSAGES["command_failed_detail"].format(error=result.error))

        if result.stderr:
            error_parts.append(f"\n{ERROR_MESSAGES['stderr_output']}")
            error_parts.append(result.stderr.strip())

        # Add contextual suggestion based on error content
        suggestion = self._get_error_suggestion(result)
        if suggestion:
            error_parts.append(f"\n💡 {suggestion}")

        body = "\n".join(error_parts) if error_parts else title

        panel = Panel(
            body,
            title=f"[red]✗ {title}[/red]",
            subtitle=f"[dim]{result.command}[/dim]",
            border_style="red",
            padding=(1, 2),
        )
        self.console.print(panel)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_info_panel(self, result: ExecutionResult, content: Table | Text) -> Panel:
        """Build a Rich Panel wrapping content with execution metadata.

        Args:
            result: Execution result for metadata.
            content: The renderable content to wrap.

        Returns:
            A Rich Panel with command info.
        """
        status = (
            ERROR_MESSAGES["dry_run_label"] if result.dry_run else ERROR_MESSAGES["executed_label"]
        )
        duration_s = result.duration_ms / 1000.0
        subtitle = f"[dim]{ERROR_MESSAGES['duration_label']}: {duration_s:.2f}s | {status}[/dim]"

        return Panel(
            content,
            title=f"[bold green]$ {result.command}[/bold green]",
            subtitle=subtitle,
            border_style="green",
            padding=(0, 1),
        )

    def _get_error_suggestion(self, result: ExecutionResult) -> str:
        """Return a contextual suggestion based on the error content.

        Args:
            result: The failed execution result.

        Returns:
            A suggestion string in Spanish, or empty string if no match.
        """
        combined = f"{result.stderr or ''} {result.error or ''}".lower()

        if any(
            kw in combined for kw in ("accessdenied", "unauthorized", "forbidden", "credentials")
        ):
            return ERROR_MESSAGES["suggestion_check_credentials"]

        if any(kw in combined for kw in ("invalidregion", "could not connect", "endpoint")):
            return ERROR_MESSAGES["suggestion_check_region"]

        if any(kw in combined for kw in ("invalidparametervalue", "malformed", "syntax", "usage:")):
            return ERROR_MESSAGES["suggestion_check_syntax"]

        return ""

    def _try_parse_json(self, text: str) -> Any:
        """Try to parse text as JSON, return None if not valid.

        Args:
            text: Raw text to attempt JSON parsing on.

        Returns:
            Parsed JSON value, or None if parsing fails.
        """
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return None
