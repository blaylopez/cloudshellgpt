"""Cost tracker — tracks estimated costs of resources created during a session."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import boto3
import yaml
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError
from pydantic import BaseModel, Field
from rich.console import Console

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class CostError(Exception):
    """Raised when cost estimation fails or cannot be completed.

    Attributes:
        message: Human-readable description of the cost estimation failure.
        service: The AWS service that was being estimated, if applicable.
    """

    def __init__(self, message: str, *, service: str | None = None) -> None:
        self.message = message
        self.service = service
        super().__init__(message)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class CostEstimate(BaseModel):
    """Result of a cost estimation for an AWS command.

    Contains all information needed by the safety layer to decide whether to
    alert the user based on the max_cost_alert threshold.
    """

    status: Literal["estimated", "unknown"] = Field(
        description="Estimation status — 'unknown' when Cost Explorer API fails"
    )
    estimated_monthly_cost: float = Field(description="Estimated monthly cost in USD")
    currency: str = Field(default="USD")
    cost_breakdown: dict[str, float] = Field(
        default_factory=dict,
        description="Breakdown by component (e.g., {'EC2 hourly': 45.0, 'EBS storage': 12.0})",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Warnings such as 'exceeds max_cost_alert threshold'",
    )
    confidence: Literal["high", "medium", "low"] = Field(
        description="How confident the estimate is"
    )
    service: str = Field(description="The AWS service being estimated")
    command: str = Field(description="The command that triggered the estimate")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maps AWS CLI service names to Cost Explorer SERVICE dimension values
_CLI_TO_CE_SERVICE: dict[str, str] = {
    "ec2": "Amazon Elastic Compute Cloud - Compute",
    "rds": "Amazon Relational Database Service",
    "s3": "Amazon Simple Storage Service",
    "s3api": "Amazon Simple Storage Service",
    "lambda": "AWS Lambda",
    "dynamodb": "Amazon DynamoDB",
    "ecs": "Amazon Elastic Container Service",
    "eks": "Amazon Elastic Kubernetes Service",
    "elb": "Elastic Load Balancing",
    "elbv2": "Elastic Load Balancing",
    "cloudfront": "Amazon CloudFront",
    "sqs": "Amazon Simple Queue Service",
    "sns": "Amazon Simple Notification Service",
    "kinesis": "Amazon Kinesis",
    "redshift": "Amazon Redshift",
    "elasticache": "Amazon ElastiCache",
    "opensearch": "Amazon OpenSearch Service",
    "sagemaker": "Amazon SageMaker",
    "bedrock": "Amazon Bedrock",
    "glue": "AWS Glue",
    "emr": "Amazon Elastic MapReduce",
    "kms": "AWS Key Management Service",
    "secretsmanager": "AWS Secrets Manager",
    "route53": "Amazon Route 53",
    "cloudwatch": "Amazon CloudWatch",
    "logs": "Amazon CloudWatch",
    "iam": "AWS Identity and Access Management",
    "vpc": "Amazon Virtual Private Cloud",
}

# Verbs that indicate resource creation (billable operations)
_RESOURCE_CREATING_VERBS: set[str] = {
    "create",
    "run",
    "launch",
    "put",
    "start",
    "allocate",
    "provision",
    "deploy",
    "enable",
    "register",
}

# Read-only verbs that cost $0
_READ_ONLY_VERBS: set[str] = {
    "list",
    "ls",
    "describe",
    "get",
    "head",
    "wait",
    "show",
    "check",
    "lookup",
    "search",
    "scan",
}


# ---------------------------------------------------------------------------
# CostEstimator
# ---------------------------------------------------------------------------


class CostEstimator:
    """Estimates costs of AWS CLI commands using the AWS Cost Explorer API.

    Queries historical and forecasted costs from Cost Explorer to provide
    a pre-execution cost estimate. Works independently and can be consumed
    by the safety layer.

    Args:
        region: AWS region for the Cost Explorer client.
        max_cost_alert: USD threshold above which a budget warning is added.
    """

    def __init__(self, region: str = "us-east-1", max_cost_alert: int = 100) -> None:
        """Initialize the CostEstimator.

        Args:
            region: AWS region for the Cost Explorer client.
            max_cost_alert: USD threshold for cost alert warnings.
        """
        self.region = region
        self.max_cost_alert = max_cost_alert
        self._client = boto3.client(
            "ce",
            region_name=self.region,
            config=BotoConfig(
                connect_timeout=5,
                read_timeout=10,
                retries={"max_attempts": 2, "mode": "standard"},
            ),
        )

    def estimate(self, command: str) -> CostEstimate:
        """Estimate the monthly cost of an AWS CLI command before execution.

        Args:
            command: The full AWS CLI command string (e.g., "aws ec2 run-instances ...").

        Returns:
            CostEstimate with populated cost data and warnings.
        """
        service = self._detect_service(command)

        # Read-only commands cost nothing
        if not self._is_resource_creating(command):
            return CostEstimate(
                status="estimated",
                estimated_monthly_cost=0.0,
                currency="USD",
                cost_breakdown={},
                warnings=[],
                confidence="high",
                service=service,
                command=command,
            )

        # Query Cost Explorer for resource-creating commands
        try:
            historical = self._get_historical_cost(service)
            forecast = self._get_cost_forecast(service)

            # Use forecast if available, fall back to historical
            estimated_cost = forecast if forecast > 0.0 else historical
            confidence: Literal["high", "medium", "low"] = (
                "medium" if estimated_cost > 0.0 else "low"
            )

            cost_breakdown: dict[str, float] = {}
            if historical > 0.0:
                cost_breakdown[f"{service} (historical avg)"] = historical
            if forecast > 0.0:
                cost_breakdown[f"{service} (forecast)"] = forecast

            warnings: list[str] = []
            if estimated_cost > self.max_cost_alert:
                warnings.append(
                    f"Estimated cost ${estimated_cost:.2f}/month exceeds "
                    f"max_cost_alert threshold (${self.max_cost_alert})"
                )

            return CostEstimate(
                status="estimated",
                estimated_monthly_cost=round(estimated_cost, 2),
                currency="USD",
                cost_breakdown=cost_breakdown,
                warnings=warnings,
                confidence=confidence,
                service=service,
                command=command,
            )

        except Exception as exc:
            logger.warning("Cost Explorer API failed: %s", exc)
            return CostEstimate(
                status="unknown",
                estimated_monthly_cost=0.0,
                currency="USD",
                cost_breakdown={},
                warnings=[f"Cost estimation unavailable: {exc}"],
                confidence="low",
                service=service,
                command=command,
            )

    def _detect_service(self, command: str) -> str:
        """Extract the AWS service name from an AWS CLI command.

        Args:
            command: The full AWS CLI command string.

        Returns:
            The detected service name (e.g., "ec2", "s3").
        """
        parts = command.strip().split()
        # Expected format: aws <service> <subcommand> [args...]
        for i, part in enumerate(parts):
            if part == "aws" and i + 1 < len(parts):
                return parts[i + 1]
        # Fallback: return "unknown" if we can't detect the service
        return "unknown"

    def _is_resource_creating(self, command: str) -> bool:
        """Check if a command creates billable resources.

        Args:
            command: The full AWS CLI command string.

        Returns:
            True if the command is expected to create billable resources.
        """
        parts = command.strip().lower().split()
        # Expected format: aws <service> <subcommand> [args...]
        # Extract subcommand parts (skip "aws" and the service name)
        subcommand_parts = [p for p in parts[2:] if not p.startswith("-")]

        if not subcommand_parts:
            return False

        # Check the subcommand (e.g., "run-instances", "create-bucket", "ls")
        subcommand = subcommand_parts[0]

        # Check read-only verbs first (more specific)
        for verb in _READ_ONLY_VERBS:
            if subcommand == verb or subcommand.startswith(f"{verb}-"):
                return False

        # Check resource-creating verbs
        for verb in _RESOURCE_CREATING_VERBS:
            if subcommand == verb or subcommand.startswith(f"{verb}-"):
                return True

        # Default: not creating if verb is unrecognized
        return False

    def _get_historical_cost(self, service: str) -> float:
        """Query Cost Explorer for historical costs of a service over the last 30 days.

        Args:
            service: The AWS CLI service name (e.g., "ec2").

        Returns:
            The average monthly cost for the service.

        Raises:
            CostError: If the API call fails with a client error.
        """
        ce_service = self._map_cli_service_to_ce_service(service)
        now = datetime.now(tz=UTC)
        start = (now - timedelta(days=30)).strftime("%Y-%m-%d")
        end = now.strftime("%Y-%m-%d")

        try:
            response = self._client.get_cost_and_usage(
                TimePeriod={"Start": start, "End": end},
                Granularity="MONTHLY",
                Metrics=["UnblendedCost"],
                Filter={
                    "Dimensions": {
                        "Key": "SERVICE",
                        "Values": [ce_service],
                    }
                },
            )
        except ClientError as exc:
            raise CostError(
                f"Failed to get historical cost for {service}: {exc}",
                service=service,
            ) from exc

        # Sum costs from all result periods
        total = 0.0
        for result in response.get("ResultsByTime", []):
            amount_str = result.get("Total", {}).get("UnblendedCost", {}).get("Amount", "0")
            total += float(amount_str)

        return round(total, 2)

    def _get_cost_forecast(self, service: str) -> float:
        """Query Cost Explorer for forecasted costs of a service for the next 30 days.

        Args:
            service: The AWS CLI service name (e.g., "ec2").

        Returns:
            The forecasted monthly cost for the service.

        Raises:
            CostError: If the API call fails with a client error.
        """
        ce_service = self._map_cli_service_to_ce_service(service)
        now = datetime.now(tz=UTC)
        # Forecast starts tomorrow (CE requires future dates)
        start = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        end = (now + timedelta(days=30)).strftime("%Y-%m-%d")

        try:
            response = self._client.get_cost_forecast(
                TimePeriod={"Start": start, "End": end},
                Metric="UNBLENDED_COST",
                Granularity="MONTHLY",
                Filter={
                    "Dimensions": {
                        "Key": "SERVICE",
                        "Values": [ce_service],
                    }
                },
            )
        except ClientError as exc:
            # Forecast may not be available for all services
            logger.warning("Cost forecast unavailable for %s: %s", service, exc)
            return 0.0

        # Extract total forecast amount
        total_str = response.get("Total", {}).get("Amount", "0")
        return round(float(total_str), 2)

    def _map_cli_service_to_ce_service(self, cli_service: str) -> str:
        """Map an AWS CLI service name to a Cost Explorer SERVICE dimension value.

        Args:
            cli_service: The CLI service name (e.g., "ec2", "s3").

        Returns:
            The Cost Explorer service dimension value.
        """
        return _CLI_TO_CE_SERVICE.get(cli_service, cli_service)


# ---------------------------------------------------------------------------
# CostTracker
# ---------------------------------------------------------------------------


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

    def _load(self) -> list[dict[str, Any]]:
        """Load costs from disk."""
        if not self.session_path.exists():
            return []
        with self.session_path.open() as f:
            data = yaml.safe_load(f) or []
        return data

    def _save(self, costs: list[dict[str, Any]]) -> None:
        """Save costs to disk."""
        with self.session_path.open("w") as f:
            yaml.safe_dump(costs, f, default_flow_style=False)

    def clear(self) -> None:
        """Clear the session cost log."""
        if self.session_path.exists():
            self.session_path.unlink()
