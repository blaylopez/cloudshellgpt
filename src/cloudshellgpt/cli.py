"""CloudShellGPT — AWS CLI that speaks your language.

Entry point for the CLI. Built with Typer for clean command structure.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, cast

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from cloudshellgpt import __version__

if TYPE_CHECKING:
    from cloudshellgpt.bedrock_translator import BedrockError, Translation
    from cloudshellgpt.safety import SafetyCheck, SafetyLayer

app = typer.Typer(
    name="csgpt",
    help="AWS CLI that speaks your language. Natural language to AWS operations via Amazon Bedrock.",
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
    output: str = typer.Option(
        "table", "--output", "-o", help="Output format: table|json|yaml|csv"
    ),
    region: str | None = typer.Option(None, "--region", "-r", help="AWS region override"),
    explain: bool = typer.Option(
        False, "--explain", "-e", help="Show what the command does after execution"
    ),
    cost_only: bool = typer.Option(
        False, "--cost-only", help="Show cost preview without executing"
    ),
) -> None:
    """Execute AWS operations using natural language.

    Examples:
        csgpt "lista los buckets de S3"
        csgpt "muéstrame las lambdas que fallaron en las últimas 24h"
        csgpt "create a t3.micro ec2 with a security group that allows SSH"
    """
    _show_banner()

    with console.status("[bold green]Thinking...[/bold green]"):
        # Lazy imports for command execution
        from cloudshellgpt.audit import AuditLogger
        from cloudshellgpt.bedrock_translator import BedrockError, BedrockTranslator
        from cloudshellgpt.config import Config
        from cloudshellgpt.cost import CostEstimator
        from cloudshellgpt.executor import AWSExecutor
        from cloudshellgpt.formatter import Formatter, FormatType
        from cloudshellgpt.i18n import get_labels
        from cloudshellgpt.intent import IntentParser
        from cloudshellgpt.safety import SafetyLayer

        # Load user configuration
        cfg = Config()
        effective_region = region or cfg.region

        # 1. Parse intent
        parser = IntentParser()
        parsed = parser.parse(intent, region=region)

        # Get UI labels based on detected language
        ui_lang = (
            parsed.detected_language if parsed.detected_language != "unknown" else cfg.language
        )
        labels = get_labels(ui_lang)

        if not parsed.confidence or parsed.confidence < 0.5:
            console.print(f"[red]{labels['could_not_understand'].format(intent=intent)}[/red]")
            console.print(f"[yellow]{labels['did_you_mean']}[/yellow]")
            raise typer.Exit(1)

        # 2. Translate to AWS CLI via Bedrock
        translator = BedrockTranslator(region=effective_region, model_id=cfg.bedrock_model)
        try:
            translation = translator.translate(parsed)
        except BedrockError as e:
            _show_bedrock_error(e)
            raise typer.Exit(1) from None

        # 3. Cost estimation (graceful fallback if Cost Explorer fails)
        cost_estimator = CostEstimator(region=effective_region, max_cost_alert=cfg.max_cost_alert)
        cost_estimate = cost_estimator.estimate(translation.command)

        # 4. Safety check (with cost estimate integrated)
        safety = SafetyLayer(region=effective_region, max_cost_alert=cfg.max_cost_alert)
        check = safety.assess(translation, cost_estimate=cost_estimate)

    # --- From here on, no spinner (allows interactive input) ---

    if cost_only:
        if cost_estimate.status == "unknown":
            console.print(
                Panel(
                    "[bold yellow]Cost estimation unavailable[/bold yellow]\n"
                    "[dim]Cost Explorer API could not be reached.[/dim]",
                    title="[bold]Cost Preview[/bold]",
                    border_style="yellow",
                )
            )
        else:
            console.print(
                Panel(
                    f"Estimated cost: {check.estimated_cost}",
                    title="[bold]Cost Preview[/bold]",
                )
            )
        return

    # 5. Show warning if cost estimation is unavailable
    if cost_estimate.status == "unknown":
        console.print(
            Text.from_markup(
                "[bold yellow]\u26a0\ufe0f  Cost estimation unavailable "
                "\u2014 proceed with caution[/bold yellow]"
            )
        )

    # 6. Show what we're about to do
    console.print(
        Panel(
            f"[bold]{labels['command_label']}:[/bold]\n[cyan]{translation.command}[/cyan]\n\n"
            f"[bold]{labels['explanation_label']}:[/bold]\n{translation.explanation}\n\n"
            f"[bold]{labels['risk_label']}:[/bold] [{_risk_color(check.risk_level)}]{check.risk_level}[/{_risk_color(check.risk_level)}]\n"
            f"[bold]{labels['cost_label']}:[/bold] {check.estimated_cost}",
            title=f"[bold]{labels['plan_title']}[/bold]",
            border_style="blue",
        )
    )

    # 6b. Flag explanations (learning mode)
    if cfg.enable_learning_mode:
        _show_flag_explanations(translation.command, labels)

    # 7. Confirmation flow (varies by risk level)
    _handle_confirmation(check, safety, translation, yes, labels)

    # 8. Audit BEFORE execution (safety: record intent even if process crashes)
    audit = AuditLogger()
    entry_id = audit.log_before(
        intent=intent,
        command=translation.command,
        risk=check.risk_level,
        dry_run=dry_run,
    )

    # 9. Execute (dry_run only if user explicitly passed --dry-run flag;
    #    critical operations already did their dry-run in confirmation flow)
    executor = AWSExecutor(dry_run=dry_run, timeout=cfg.timeout)
    result = executor.run(translation.command)

    # 10. Audit AFTER execution (record outcome)
    audit.log_after(entry_id, result)

    # 11. Format output
    format_type: FormatType = cast(
        FormatType,
        output if output in ("table", "json", "yaml", "csv", "raw") else "table",
    )
    formatter = Formatter(format_type=format_type)
    formatter.render(result)

    # 12. Post-execution educational tip
    if result.exit_code == 0 and cfg.enable_learning_mode:
        # Prefer LLM-generated tip (localized) over static dictionary
        tip = translation.tip
        if not tip:
            from cloudshellgpt.learning import PostExecutionTips

            tips = PostExecutionTips()
            tip = tips.get_tip(translation.command)
        if tip:
            console.print(
                Panel(
                    f"[dim]{tip}[/dim]",
                    title=f"[bold green]{labels['tip_title']}[/bold green]",
                    border_style="green",
                    padding=(0, 1),
                )
            )

    # 13. Related command suggestions (learning mode)
    if result.exit_code == 0 and cfg.enable_learning_mode:
        # Prefer LLM-generated related commands (localized) over static dictionary
        if translation.related_commands:
            lines: list[str] = []
            for rc in translation.related_commands:
                cmd = rc.get("command", "")
                desc = rc.get("description", "")
                lines.append(f"  [cyan]{cmd}[/cyan]  {desc}")
            if lines:
                console.print(
                    Panel(
                        "\n".join(lines),
                        title=f"[bold magenta]{labels['related_title']}[/bold magenta]",
                        border_style="magenta",
                        padding=(0, 1),
                    )
                )
        else:
            from cloudshellgpt.learning import RelatedCommands

            related = RelatedCommands()
            suggestions = related.suggest(translation.command)
            if suggestions:
                lines = []
                for suggestion in suggestions:
                    lines.append(f"  [cyan]{suggestion.command}[/cyan]  {suggestion.description}")
                console.print(
                    Panel(
                        "\n".join(lines),
                        title=f"[bold magenta]{labels['related_title']}[/bold magenta]",
                        border_style="magenta",
                        padding=(0, 1),
                    )
                )

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
    topic: str = typer.Argument(
        ..., help="AWS service to learn: s3, ec2, lambda, dynamodb, iam, vpc"
    ),
) -> None:
    """Interactive tutorial for an AWS service."""
    from cloudshellgpt.learning import TutorialRunner

    runner = TutorialRunner(topic)
    runner.run()


@app.command()
def explain(
    command: str | None = typer.Argument(None, help="AWS CLI command to explain"),
    last: bool = typer.Option(False, "--last", help="Explain the last executed command"),
) -> None:
    """Explain what an AWS CLI command does in detail."""
    from cloudshellgpt.config import Config
    from cloudshellgpt.learning import Explainer

    cfg = Config()
    explainer = Explainer(region=cfg.region, model_id=cfg.bedrock_model)
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
        from cloudshellgpt.mcp_server import serve_mcp

        serve_mcp()
    else:
        console.print(f"[red]Unknown MCP action:[/red] {action}")
        raise typer.Exit(1)


@app.command()
def config(
    show: bool = typer.Option(False, "--show", help="Show current configuration"),
    init: bool = typer.Option(False, "--init", help="Create or reset config file with defaults"),
    set_region: str | None = typer.Option(None, "--set-region", help="Set default region"),
    set_language: str | None = typer.Option(
        None, "--set-language", help="Set default output language"
    ),
) -> None:
    """Configure CloudShellGPT."""
    from cloudshellgpt.config import ConfigManager

    cfg = ConfigManager()

    if init:
        cfg.reset_defaults()
        console.print(f"[green]Config file created with defaults at {cfg.config_path}[/green]")
    elif show:
        console.print(Panel(cfg.to_yaml(), title="[bold]Configuration[/bold]"))
    elif set_region:
        cfg.set("region", set_region)
        cfg.save()
        console.print(f"[green]Region set to {set_region}[/green]")
    elif set_language:
        cfg.set("language", set_language)
        cfg.save()
        console.print(f"[green]Language set to {set_language}[/green]")


def _version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"csgpt version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """CloudShellGPT — AWS CLI that speaks your language."""


def _show_flag_explanations(command: str, labels: dict[str, str]) -> None:
    """Display flag explanations for the translated command.

    Shows a Rich panel with each recognized flag and its description,
    helping users learn what each flag does before confirming execution.

    Args:
        command: The translated AWS CLI command containing flags to explain.
        labels: UI labels dictionary for i18n.
    """
    from cloudshellgpt.learning import FlagExplainer

    explainer = FlagExplainer()
    explanations = explainer.explain_flags(command)

    if not explanations:
        return

    lines: list[str] = []
    for item in explanations:
        lines.append(f"  [cyan]{item.flag}[/cyan]  {item.explanation}")

    console.print(
        Panel(
            "\n".join(lines),
            title=f"[bold blue]{labels['flags_title']}[/bold blue]",
            border_style="blue",
            padding=(0, 1),
        )
    )


def _show_bedrock_error(error: BedrockError) -> None:
    """Display a BedrockError as a Rich panel with actionable info.

    Args:
        error: The structured BedrockError to display.
    """
    lines: list[str] = []
    lines.append(f"[bold red]Error:[/bold red] {error.user_message}")
    if error.suggestion:
        lines.append(f"\n[bold yellow]Suggestion:[/bold yellow] {error.suggestion}")
    if error.technical_detail:
        lines.append(f"\n[dim]Detail: {error.technical_detail}[/dim]")

    console.print(
        Panel(
            "\n".join(lines),
            title=f"[bold red]Bedrock Error ({error.error_type.value})[/bold red]",
            border_style="red",
        )
    )


def _risk_color(level: str) -> str:
    """Map risk level to Rich color."""
    return {
        "low": "green",
        "medium": "yellow",
        "high": "red",
        "critical": "bold red",
    }.get(level, "white")


def _handle_confirmation(
    check: SafetyCheck,
    safety: SafetyLayer,
    translation: Translation,
    yes: bool,
    labels: dict[str, str],
) -> None:
    """Handle confirmation flow based on risk level.

    Implements the confirmation ladder:
    - low: execute directly (no confirmation)
    - medium: show command + explanation, ask Y/N (--yes can bypass)
    - high: show command + affected resources + cost, require typed confirmation
    - critical: force dry-run first, then require user to type "yes-i-understand"

    The --yes flag only bypasses medium-level confirmations.

    Args:
        check: The SafetyCheck result from the safety layer.
        safety: The SafetyLayer instance (for inject_dry_run on critical).
        translation: The translation being confirmed.
        yes: Whether the --yes flag was passed.
        labels: UI labels dictionary for i18n.

    Raises:
        typer.Exit: If the user cancels or fails confirmation.
    """
    risk = check.risk_level

    # low → execute directly
    if risk == "low":
        return

    # medium → simple Y/N (--yes can bypass)
    if risk == "medium":
        if yes:
            return
        confirmed = typer.confirm(f"\n{check.confirmation_prompt}", default=False)
        if not confirmed:
            console.print(f"[yellow]{labels['cancelled']}[/yellow]")
            raise typer.Exit(0)
        return

    # high → show affected resources + cost, require typed confirmation
    if risk == "high":
        _confirm_high_risk(check, translation, labels)
        return

    # critical → dry-run first, then "yes-i-understand"
    if risk == "critical":
        _confirm_critical_risk(check, safety, translation, labels)
        return


def _confirm_high_risk(
    check: SafetyCheck, translation: Translation, labels: dict[str, str]
) -> None:
    """Handle high-risk confirmation: require typed resource name."""
    resources_display = ", ".join(check.affected_resources) if check.affected_resources else "N/A"
    console.print(
        Panel(
            f"[bold red]{labels['confirm_high_banner']}[/bold red]\n\n"
            f"[bold]{labels['command_label']}:[/bold] [cyan]{translation.command}[/cyan]\n"
            f"[bold]{labels['affected_resources']}:[/bold] {resources_display}\n"
            f"[bold]{labels['estimated_cost']}:[/bold] {check.estimated_cost}",
            title=f"[bold red]{labels['confirm_high_title']}[/bold red]",
            border_style="red",
        )
    )

    if check.affected_resources:
        expected = check.affected_resources[0]
        prompt_text = f"\n{labels['type_resource'].format(resource=expected)}"
    else:
        expected = "confirm"
        prompt_text = f"\n{labels['type_confirm']}"

    user_input = typer.prompt(prompt_text)
    if user_input.strip() != expected:
        console.print(f"[yellow]{labels['confirmation_mismatch']}[/yellow]")
        raise typer.Exit(0)


def _confirm_critical_risk(
    check: SafetyCheck,
    safety: SafetyLayer,
    translation: Translation,
    labels: dict[str, str],
) -> None:
    """Handle critical-risk confirmation: dry-run first, then "yes-i-understand".

    Flow:
    1. Show a warning banner with affected resources and cost
    2. Perform automatic dry-run (inject dry-run, execute, show results)
    3. Ask the user to type exactly "yes-i-understand" to proceed
    4. If the user types anything else, cancel

    Args:
        check: The SafetyCheck with resource and cost info.
        safety: The SafetyLayer instance for dry-run injection.
        translation: The translation being confirmed.

    Raises:
        typer.Exit: If the user does not type "yes-i-understand".
    """
    from cloudshellgpt.executor import AWSExecutor

    # 1. Warning banner
    resources_lines = (
        "\n".join(f"  • {r}" for r in check.affected_resources)
        if check.affected_resources
        else "  • (unknown resources)"
    )
    console.print(
        Panel(
            f"[bold red]{labels['confirm_critical_banner']}[/bold red]\n\n"
            f"[bold]{labels['command_label']}:[/bold]\n  [cyan]{translation.command}[/cyan]\n\n"
            f"[bold]{labels['affected_resources']}:[/bold]\n{resources_lines}\n\n"
            f"[bold]{labels['estimated_cost']}:[/bold] {check.estimated_cost}\n\n"
            f"[dim]{labels['dry_run_performing']}[/dim]",
            title=f"[bold red]{labels['confirm_critical_title']}[/bold red]",
            border_style="bold red",
        )
    )

    # 2. Automatic dry-run
    console.print(f"\n[bold]{labels['dry_run_performing']}[/bold]")
    dry_run_result = safety.inject_dry_run(translation.command)

    if dry_run_result.preview_only:
        # Service doesn't support native dry-run — show preview
        console.print(
            Panel(
                f"[dim]{dry_run_result.dry_run_notes}[/dim]\n\n"
                f"[cyan]{dry_run_result.command}[/cyan]",
                title=f"[bold]{labels['dry_run_preview']}[/bold]",
                border_style="yellow",
            )
        )
    else:
        # Execute the dry-run command
        executor = AWSExecutor(dry_run=False, timeout=30)
        dr_exec_result = executor.run(dry_run_result.command)

        # AWS dry-run returns non-zero exit code with "DryRunOperation" error
        # when the operation WOULD have succeeded. This is a success signal.
        dry_run_success = dr_exec_result.exit_code == 0 or "DryRunOperation" in (
            dr_exec_result.stderr or ""
        )

        if dry_run_success:
            console.print(
                Panel(
                    f"[green]{labels['dry_run_success']}[/green]\n\n"
                    f"[dim]{dry_run_result.dry_run_notes}[/dim]",
                    title=f"[bold]{labels['dry_run_result']}[/bold]",
                    border_style="green",
                )
            )
        else:
            console.print(
                Panel(
                    f"[red]Dry-run returned errors:[/red]\n\n"
                    f"{dr_exec_result.stderr or dr_exec_result.stdout or '(no output)'}",
                    title=f"[bold red]{labels['dry_run_failed']}[/bold red]",
                    border_style="red",
                )
            )
            console.print(f"[yellow]{labels['dry_run_failed']}[/yellow]")
            raise typer.Exit(1)

    # 3. Require typed confirmation
    console.print(f"\n[bold]{labels['type_yes_i_understand']}[/bold]")
    user_input = typer.prompt("Confirm")
    if user_input.strip() != "yes-i-understand":
        console.print(f"[yellow]{labels['confirmation_mismatch']}[/yellow]")
        raise typer.Exit(0)


if __name__ == "__main__":
    app()
    sys.exit(0)
