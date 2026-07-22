"""Safety layer — risk assessment, cost preview, and dry-run support."""
from __future__ import annotations

from typing import Literal

import boto3
from pydantic import BaseModel

from cloudshellgpt.bedrock_translator import Translation


RiskLevel = Literal["low", "medium", "high", "critical"]


class SafetyCheck(BaseModel):
    """Result of a safety assessment on a translation."""

    risk_level: RiskLevel
    requires_confirmation: bool
    requires_dry_run: bool
    estimated_cost: str
    confirmation_prompt: str
    warnings: list[str] = []
    affected_resources: list[str] = []
    reversible: bool = True
    cost_breakdown: dict[str, str] = {}


class SafetyLayer:
    """Assesses risk and cost of AWS operations before execution.

    Combines:
    - Rule-based risk detection (from Translation.risk_level)
    - Cost estimation (via AWS Cost Explorer API)
    - Confirmation prompting for high-risk operations
    """

    DESTRUCTIVE_PATTERNS = [
        "delete",
        "terminate",
        "rm -rf",
        "remove",
        "drop",
        "destroy",
        "force",
    ]

    def __init__(self, region: str = "us-east-1") -> None:
        self.ce_client = boto3.client("ce", region_name=region)
        self.region = region

    def assess(self, translation: Translation) -> SafetyCheck:
        """Run a full safety assessment.

        Args:
            translation: The Bedrock-generated translation

        Returns:
            SafetyCheck with all risk/cost information
        """
        # Start with the LLM-provided risk level
        risk_level = translation.risk_level

        # Upgrade risk if we see dangerous patterns
        if self._is_destructive(translation.command):
            risk_level = self._upgrade_risk(risk_level)

        # Determine if confirmation is required
        requires_confirmation = risk_level in ("high", "critical")

        # Determine if dry-run should be used
        requires_dry_run = translation.requires_dry_run or risk_level == "critical"

        # Build confirmation prompt
        confirmation_prompt = self._build_confirmation_prompt(translation, risk_level)

        # Get cost preview if creating new resources
        cost_breakdown = self._estimate_costs(translation)

        return SafetyCheck(
            risk_level=risk_level,
            requires_confirmation=requires_confirmation,
            requires_dry_run=requires_dry_run,
            estimated_cost=translation.estimated_cost,
            confirmation_prompt=confirmation_prompt,
            warnings=translation.affected_resources,
            affected_resources=translation.affected_resources,
            reversible=risk_level != "critical",
            cost_breakdown=cost_breakdown,
        )

    def _is_destructive(self, command: str) -> bool:
        """Check if a command contains destructive patterns."""
        cmd_lower = command.lower()
        return any(pattern in cmd_lower for pattern in self.DESTRUCTIVE_PATTERNS)

    def _upgrade_risk(self, current: RiskLevel) -> RiskLevel:
        """Upgrade risk level if destructive patterns are detected."""
        ladder: dict[RiskLevel, RiskLevel] = {
            "low": "high",
            "medium": "high",
            "high": "critical",
            "critical": "critical",
        }
        return ladder[current]

    def _build_confirmation_prompt(self, translation: Translation, risk: RiskLevel) -> str:
        """Build a human-readable confirmation prompt."""
        if risk == "critical":
            return (
                f"⚠️  CRITICAL OPERATION\n\n"
                f"This action is IRREVERSIBLE and will affect:\n"
                + "\n".join(f"  - {r}" for r in translation.affected_resources)
                + f"\n\nEstimated cost: {translation.estimated_cost}\n"
                f"\nType 'yes-i-understand' to proceed:"
            )
        elif risk == "high":
            return (
                f"⚠️  HIGH RISK OPERATION\n\n"
                f"Affected: {', '.join(translation.affected_resources) or 'unknown'}\n"
                f"Cost: {translation.estimated_cost}\n\n"
                f"Proceed?"
            )
        return "Proceed?"

    def _estimate_costs(self, translation: Translation) -> dict[str, str]:
        """Estimate costs via Cost Explorer or rule-based."""
        # Simple rule-based estimation for common services
        cost_map = {
            "ec2 run-instances": "EC2 hourly cost",
            "rds create-db-instance": "RDS hourly cost",
            "lambda create-function": "Lambda invocation cost",
            "s3 mb": "S3 storage cost",
        }

        breakdown = {}
        for pattern, cost_type in cost_map.items():
            if pattern in translation.command:
                breakdown[cost_type] = translation.estimated_cost

        return breakdown
