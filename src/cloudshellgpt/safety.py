"""Safety layer — risk assessment, cost preview, confirmation flow, and dry-run support."""

from __future__ import annotations

from typing import Literal

import boto3
from pydantic import BaseModel, Field

from cloudshellgpt.bedrock_translator import Translation

RiskLevel = Literal["low", "medium", "high", "critical"]


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class SafetyError(Exception):
    """Raised when a safety check fails or cannot be completed.

    Attributes:
        message: Human-readable description of the safety failure.
        risk_level: The risk level that triggered the error, if applicable.
    """

    def __init__(self, message: str, *, risk_level: RiskLevel | None = None) -> None:
        self.message = message
        self.risk_level = risk_level
        super().__init__(message)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class SafetyCheck(BaseModel):
    """Result of a safety assessment on a translation.

    Contains all information needed for the CLI to decide whether to execute,
    prompt for confirmation, or require dry-run before proceeding.
    """

    risk_level: RiskLevel = Field(description="Assessed risk level of the operation")
    requires_confirmation: bool = Field(
        description="Whether user confirmation is needed before execution"
    )
    requires_dry_run: bool = Field(
        description="Whether a dry-run must be performed before real execution"
    )
    estimated_cost: str = Field(description="Estimated cost string (e.g. '$0.00')")
    confirmation_prompt: str = Field(
        description="Human-readable prompt to show the user for confirmation"
    )
    warnings: list[str] = Field(default_factory=list)
    affected_resources: list[str] = Field(default_factory=list)
    reversible: bool = Field(
        default=True,
        description="Whether the operation can be undone without data loss",
    )
    cost_breakdown: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DESTRUCTIVE_PATTERNS: list[str] = [
    # Generic destructive verbs
    "delete",
    "terminate",
    "rm",
    "remove",
    "drop",
    "destroy",
    "force",
    "purge",
    "wipe",
    "nuke",
    # AWS-specific destructive actions
    "deregister",
    "revoke",
    "detach",
    "disable",
    "release",
    "empty",
    # Dangerous flags
    "--recursive",
    "--force",
    "-f",
    "--no-preserve",
    "--skip-final-snapshot",
    "--force-delete",
    "--permanently-delete",
    "--no-undo",
    "--force-destroy",
    "--delete-all-versions",
    "--bypass-governance-retention",
    "--no-preserve-root",
]

DRY_RUN_SERVICES: list[str] = [
    "ec2",
    "rds",
    "s3api",
    "iam",
    "cloudformation",
    "lambda",
]


# ---------------------------------------------------------------------------
# Safety layer
# ---------------------------------------------------------------------------


class SafetyLayer:
    """Assesses risk and cost of AWS operations before execution.

    Combines:
    - Rule-based destructive pattern detection (independent of LLM assessment)
    - Risk upgrade ladder (never downgrades below LLM suggestion)
    - Cost estimation via AWS Cost Explorer API
    - Confirmation prompting appropriate to risk level

    Heuristic for classification:
    - If operation has a direct inverse and doesn't destroy data → medium
    - If operation eliminates data or access → high
    - If in doubt → upgrade
    """

    def __init__(self, region: str = "us-east-1") -> None:
        """Initialize the safety layer.

        Args:
            region: AWS region for Cost Explorer API calls.
        """
        self.ce_client = boto3.client("ce", region_name=region)
        self.region = region

    def assess(self, translation: Translation) -> SafetyCheck:
        """Run a full safety assessment on a translated command.

        Checks for destructive patterns INDEPENDENTLY of the LLM's risk
        assessment and upgrades risk accordingly. Never downgrades risk
        below what the LLM suggested.

        Args:
            translation: The Bedrock-generated translation to assess.

        Returns:
            SafetyCheck with all risk, cost, and confirmation information.

        Raises:
            SafetyError: If the assessment cannot be completed.
        """
        # Start with the LLM-provided risk level
        risk_level = self._validate_risk_level(translation.risk_level)

        # Upgrade risk if destructive patterns detected (independent of LLM)
        if self._is_destructive(translation.command):
            risk_level = self._upgrade_risk(risk_level)

        # Confirmation flow:
        # low → execute directly (no confirmation)
        # medium → show plan, ask Y/N
        # high → show command + affected resources + cost, typed confirmation
        # critical → dry-run first + "yes-i-understand"
        requires_confirmation = risk_level in ("medium", "high", "critical")

        # Dry-run required for critical or if LLM flagged it
        requires_dry_run = translation.requires_dry_run or risk_level == "critical"

        # Build confirmation prompt appropriate to risk level
        confirmation_prompt = self._build_confirmation_prompt(translation, risk_level)

        # Estimate costs for resource-creating operations
        cost_breakdown = self._estimate_costs(translation)

        # Determine reversibility: critical operations are not reversible
        reversible = risk_level not in ("critical",)

        return SafetyCheck(
            risk_level=risk_level,
            requires_confirmation=requires_confirmation,
            requires_dry_run=requires_dry_run,
            estimated_cost=translation.estimated_cost,
            confirmation_prompt=confirmation_prompt,
            warnings=translation.affected_resources,
            affected_resources=translation.affected_resources,
            reversible=reversible,
            cost_breakdown=cost_breakdown,
        )

    def _validate_risk_level(self, level: str) -> RiskLevel:
        """Validate and cast a string to RiskLevel.

        Args:
            level: Raw risk level string from the LLM.

        Returns:
            A valid RiskLevel literal. Defaults to 'low' if invalid.
        """
        if level in ("low", "medium", "high", "critical"):
            return level  # type: ignore[return-value]
        return "low"

    def _is_destructive(self, command: str) -> bool:
        """Check if a command contains destructive patterns.

        Scans the command against the full DESTRUCTIVE_PATTERNS list
        independently of the LLM's risk assessment.

        Args:
            command: The AWS CLI command string to check.

        Returns:
            True if any destructive pattern is found in the command.
        """
        cmd_lower = command.lower()
        return any(pattern in cmd_lower for pattern in DESTRUCTIVE_PATTERNS)

    def _upgrade_risk(self, current: RiskLevel) -> RiskLevel:
        """Upgrade risk level when destructive patterns are detected.

        Ladder:
        - low → high
        - medium → high
        - high → critical
        - critical → critical (already at max)

        Args:
            current: The current risk level before upgrade.

        Returns:
            The upgraded risk level.
        """
        ladder: dict[RiskLevel, RiskLevel] = {
            "low": "high",
            "medium": "high",
            "high": "critical",
            "critical": "critical",
        }
        return ladder[current]

    def _build_confirmation_prompt(self, translation: Translation, risk: RiskLevel) -> str:
        """Build a human-readable confirmation prompt based on risk level.

        - low: empty (no confirmation needed)
        - medium: show command + explanation, ask Y/N
        - high: show command + affected resources + cost, ask typed confirmation
        - critical: warning banner + affected resources + cost + "yes-i-understand"

        Args:
            translation: The translation containing command metadata.
            risk: The assessed risk level.

        Returns:
            Formatted confirmation prompt string.
        """
        if risk == "critical":
            resources = (
                "\n".join(f"  - {r}" for r in translation.affected_resources)
                or "  - (unknown resources)"
            )
            return (
                "\u26a0\ufe0f  CRITICAL OPERATION\n\n"
                "This action is IRREVERSIBLE and will affect:\n"
                f"{resources}\n\n"
                f"Estimated cost: {translation.estimated_cost}\n"
                f"Command: {translation.command}\n\n"
                "A dry-run will be performed first.\n"
                "Type 'yes-i-understand' to proceed:"
            )
        elif risk == "high":
            resources = ", ".join(translation.affected_resources) or "unknown"
            return (
                "\u26a0\ufe0f  HIGH RISK OPERATION\n\n"
                f"Command: {translation.command}\n"
                f"Affected: {resources}\n"
                f"Cost: {translation.estimated_cost}\n\n"
                "Type the resource name to confirm:"
            )
        elif risk == "medium":
            return (
                f"Command: {translation.command}\n"
                f"Explanation: {translation.explanation}\n\n"
                "Proceed? [Y/n]:"
            )
        # low — no confirmation needed
        return ""

    def _estimate_costs(self, translation: Translation) -> dict[str, str]:
        """Estimate costs for the operation via rule-based matching.

        Uses simple pattern matching against common resource-creating commands
        to provide a cost breakdown by component.

        Args:
            translation: The translation to estimate costs for.

        Returns:
            Dictionary mapping cost component names to estimated values.
        """
        cost_map: dict[str, str] = {
            "ec2 run-instances": "EC2 hourly cost",
            "rds create-db-instance": "RDS hourly cost",
            "lambda create-function": "Lambda invocation cost",
            "s3 mb": "S3 storage cost",
            "s3api create-bucket": "S3 storage cost",
            "elasticache create-cluster": "ElastiCache hourly cost",
            "ecs create-service": "ECS task cost",
        }

        breakdown: dict[str, str] = {}
        cmd_lower = translation.command.lower()
        for pattern, cost_type in cost_map.items():
            if pattern in cmd_lower:
                breakdown[cost_type] = translation.estimated_cost

        return breakdown
