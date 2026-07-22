"""CloudShellGPT — AWS CLI that speaks your language.

Entry point for the CLI. Built with Typer for clean command structure.
"""
from __future__ import annotations

import sys
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from cloudshellgpt import __version__
from cloudshellgpt.intent import IntentParser
from cloudshellgpt.bedrock_translator import BedrockTranslator
from cloudshellgpt.safety import SafetyLayer
from cloudshellgpt.executor import AWSExecutor
from cloudshellgpt.formatter import Formatter
from cloudshellgpt.audit import AuditLogger
from cloudshellgpt.mcp_server import serve_mcp

app = typer.Typer(
    name="csgpt",
    help="AWS CLI that speaks your language. Natural language → AWS operations via Amazon Bedrock.",
    add_completion=True,
    no_args_is_help=True,
    rich_markup_mode="rich",
)

console = Console()


def _show_banner() -> None:
    """Show the CloudShellGPT banner on first run."""
    banner = Text()
    banner.append("⚡ ", style="bold yellow")
    banner.append("CloudShellGPT", style="bold cyan")
    banner.append(f" v{__version__}", style="dim")
    banner.append(" — AWS CLI that speaks your language", style="dim italic")
    console.print(banner)


@app.command()
def ask(
    intent: str = typer.Argument(..., help="Your request in natural language (any language)"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Preview without executing"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation for safe commands"),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table|json|yaml|csv"),
    region: Optional[str] = typer.Option(None, "--region", "-r", help="AWS region override"),
    explain: bool = typer.Option(False, "--explain", "-e", help="Show what the command does after execution"),
    cost_only: bool = typer.Option(False, "--cost-only", help="Show cost preview without executing"),
) -> None:
    """Execute AWS operations using natural language.

    Examples:
        csgpt "lista los buckets de S3"
        csgpt "muéstrame las lambdas que fallaron en las últimas 24h"
        csgpt "create a t3.micro ec2 with a security group that allows SSH"
    """
    _show_banner()

    with console.status("[bold green]Thinking...[/bold green]"):
        # 1. Parse intent
        parser = IntentParser()
        parsed = parser.parse(intent, region=region)

        if not parsed.confidence or parsed.confidence < 0.5:
            console.print(f"[red]Could not understand:[/red] {intent}")
            console.print(f"[yellow]Did you mean:[/yellow] {parsed.suggestion}")
            raise typer.Exit(1)

        # 2. Translate to AWS CLI via Bedrock
        translator = BedrockTranslator()
        translation = translator.translate(parsed)

        # 3. Safety check
        safety = SafetyLayer()
        check = safety.assess(translation)

        if cost_only:
            console.print(Panel(check.cost_summary(), title="[bold]Cost Preview[/bold]"))
            return

        # 4. Show what we're about to do
        console.print(
            Panel(
                f"[bold]Command:[/bold]\n[cyan]{translation.command}[/cyan]\n\n"
                f"[bold]Explanation:[/bold]\n{translation.explanation}\n\n"
                f"[bold]Risk:[/bold] [{_risk_color(check.risk_level)}]{check.risk_level}[/{_risk_color(check.risk_level)}]\n"
                f"[bold]Cost:[/bold] {check.estimated_cost}",
                title="[bold]Plan[/bold]",
                border_style="blue",
            )
        )

        # 5. Confirm if needed
        if check.requires_confirmation and not yes:
            confirmed = typer.confirm(f"\n{check.confirmation_prompt}", default=False)
            if not confirmed:
                console.print("[yellow]Cancelled.[/yellow]")
                raise typer.Exit(0)

        # 6. Execute
        executor = AWSExecutor(dry_run=dry_run or check.requires_dry_run)
        result = executor.run(translation.command)

        # 7. Audit
        AuditLogger().log(
            intent=intent,
            command=translation.command,
            risk=check.risk_level,
            dry_run=dry_run,
            result=result,
        )

        # 8. Format output
        formatter = Formatter(format_type=output)
        formatter.render(result)

        if explain:
            console.print(
                Panel(
                    translation.detailed_explanation,
                    title="[bold]Learn: What just happened?[/bold]",
                    border_style="green",
                )
            )


@app.command()
def learn(
    topic: str = typer.Argument(..., help="AWS service to learn: s3, ec2, lambda, dynamodb, iam, vpc"),
) -> None:
    """Interactive tutorial for an AWS service."""
    from cloudshellgpt.learning import TutorialRunner
    runner = TutorialRunner(topic)
    runner.run()


@app.command()
def explain(
    command: Optional[str] = typer.Argument(None, help="AWS CLI command to explain"),
    last: bool = typer.Option(False, "--last", help="Explain the last executed command"),
) -> None:
    """Explain what an AWS CLI command does in detail."""
    from cloudshellgpt.learning import Explainer
    explainer = Explainer()
    if last:
        explainer.explain_last()
    elif command:
        explainer.explain(command)
    else:
        console.print("[red]Provide a command or use --last[/red]")
        raise typer.Exit(1)


@app.command()
def cost_summary() -> None:
    """Show the cumulative estimated cost of resources created in this session."""
    from cloudshellgpt.cost import CostTracker
    tracker = CostTracker()
    summary = tracker.session_summary()
    console.print(Panel(summary, title="[bold]Session Cost Summary[/bold]", border_style="yellow"))


@app.command()
def mcp(
    action: str = typer.Argument("serve", help="MCP action: serve"),
) -> None:
    """Run CloudShellGPT as an MCP server (for Kiro, Claude, Cursor)."""
    if action == "serve":
        console.print("[dim]Starting MCP server on stdio...[/dim]")
        serve_mcp()
    else:
        console.print(f"[red]Unknown MCP action:[/red] {action}")
        raise typer.Exit(1)


@app.command()
def config(
    show: bool = typer.Option(False, "--show", help="Show current configuration"),
    set_region: Optional[str] = typer.Option(None, "--set-region", help="Set default region"),
    set_language: Optional[str] = typer.Option(None, "--set-language", help="Set default output language"),
) -> None:
    """Configure CloudShellGPT."""
    from cloudshellgpt.config import ConfigManager
    cfg = ConfigManager()

    if show:
        console.print(Panel(cfg.to_yaml(), title="[bold]Configuration[/bold]"))
    elif set_region:
        cfg.set("region", set_region)
        cfg.save()
        console.print(f"[green]Region set to {set_region}[/green]")
    elif set_language:
        cfg.set("language", set_language)
        cfg.save()
        console.print(f"[green]Language set to {set_language}[/green]")


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", "-V", help="Show version and exit"),
) -> None:
    """CloudShellGPT — AWS CLI that speaks your language."""
    if version:
        console.print(f"csgpt version {__version__}")
        raise typer.Exit()


def _risk_color(level: str) -> str:
    """Map risk level to Rich color."""
    return {
        "low": "green",
        "medium": "yellow",
        "high": "red",
        "critical": "bold red",
    }.get(level, "white")


if __name__ == "__main__":
    app()
    sys.exit(0)
