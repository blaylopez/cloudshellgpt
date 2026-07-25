"""Unit tests for CostEstimator — AWS Cost Explorer integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from cloudshellgpt.cost import CostEstimate, CostEstimator

# ---------------------------------------------------------------------------
# Service detection
# ---------------------------------------------------------------------------


class TestDetectService:
    """Tests for CostEstimator._detect_service."""

    @pytest.mark.parametrize(
        ("command", "expected"),
        [
            ("aws ec2 run-instances --instance-type t3.micro", "ec2"),
            ("aws s3 ls", "s3"),
            ("aws rds create-db-instance --db-instance-id test", "rds"),
            ("aws lambda invoke --function-name my-fn out.json", "lambda"),
            ("aws dynamodb put-item --table my-table", "dynamodb"),
            ("aws s3api list-buckets", "s3api"),
            ("aws iam create-user --user-name bob", "iam"),
            ("aws cloudwatch put-metric-alarm --alarm-name test", "cloudwatch"),
        ],
    )
    def test_detects_service_from_command(self, command: str, expected: str) -> None:
        with patch("boto3.client"):
            estimator = CostEstimator()
        assert estimator._detect_service(command) == expected

    def test_returns_unknown_for_unparseable_command(self) -> None:
        with patch("boto3.client"):
            estimator = CostEstimator()
        assert estimator._detect_service("not a valid command") == "unknown"

    def test_returns_unknown_for_empty_command(self) -> None:
        with patch("boto3.client"):
            estimator = CostEstimator()
        assert estimator._detect_service("") == "unknown"


# ---------------------------------------------------------------------------
# Resource-creating detection
# ---------------------------------------------------------------------------


class TestIsResourceCreating:
    """Tests for CostEstimator._is_resource_creating."""

    @pytest.mark.parametrize(
        "command",
        [
            "aws ec2 run-instances --instance-type t3.micro",
            "aws rds create-db-instance --db-instance-id test",
            "aws s3api create-bucket --bucket my-bucket",
            "aws lambda create-function --function-name test",
            "aws ec2 start-instances --instance-ids i-123",
            "aws ec2 allocate-address",
            "aws ecs register-task-definition --family test",
        ],
    )
    def test_detects_resource_creating_commands(self, command: str) -> None:
        with patch("boto3.client"):
            estimator = CostEstimator()
        assert estimator._is_resource_creating(command) is True

    @pytest.mark.parametrize(
        "command",
        [
            "aws s3 ls",
            "aws ec2 describe-instances",
            "aws rds describe-db-instances",
            "aws lambda list-functions",
            "aws iam get-user",
            "aws ec2 wait instance-running --instance-ids i-123",
        ],
    )
    def test_detects_read_only_commands(self, command: str) -> None:
        with patch("boto3.client"):
            estimator = CostEstimator()
        assert estimator._is_resource_creating(command) is False


# ---------------------------------------------------------------------------
# CLI to CE service mapping
# ---------------------------------------------------------------------------


class TestMapCliServiceToCeService:
    """Tests for CostEstimator._map_cli_service_to_ce_service."""

    @pytest.mark.parametrize(
        ("cli_service", "expected"),
        [
            ("ec2", "Amazon Elastic Compute Cloud - Compute"),
            ("s3", "Amazon Simple Storage Service"),
            ("s3api", "Amazon Simple Storage Service"),
            ("rds", "Amazon Relational Database Service"),
            ("lambda", "AWS Lambda"),
            ("dynamodb", "Amazon DynamoDB"),
        ],
    )
    def test_maps_known_services(self, cli_service: str, expected: str) -> None:
        with patch("boto3.client"):
            estimator = CostEstimator()
        assert estimator._map_cli_service_to_ce_service(cli_service) == expected

    def test_returns_original_for_unknown_service(self) -> None:
        with patch("boto3.client"):
            estimator = CostEstimator()
        assert estimator._map_cli_service_to_ce_service("newservice") == "newservice"


# ---------------------------------------------------------------------------
# Estimate — read-only commands
# ---------------------------------------------------------------------------


class TestEstimateReadOnly:
    """Tests for CostEstimator.estimate with read-only commands."""

    def test_read_only_returns_zero_cost_high_confidence(self) -> None:
        with patch("boto3.client"):
            estimator = CostEstimator()

        result = estimator.estimate("aws s3 ls")

        assert result.status == "estimated"
        assert result.estimated_monthly_cost == 0.0
        assert result.confidence == "high"
        assert result.service == "s3"
        assert result.command == "aws s3 ls"
        assert result.warnings == []

    def test_describe_command_returns_zero_cost(self) -> None:
        with patch("boto3.client"):
            estimator = CostEstimator()

        result = estimator.estimate("aws ec2 describe-instances")

        assert result.status == "estimated"
        assert result.estimated_monthly_cost == 0.0
        assert result.confidence == "high"


# ---------------------------------------------------------------------------
# Estimate — resource-creating commands (happy path)
# ---------------------------------------------------------------------------


class TestEstimateResourceCreating:
    """Tests for CostEstimator.estimate with resource-creating commands."""

    def test_returns_estimated_cost_from_forecast(self) -> None:
        mock_client = MagicMock()
        mock_client.get_cost_and_usage.return_value = {
            "ResultsByTime": [{"Total": {"UnblendedCost": {"Amount": "45.50", "Unit": "USD"}}}]
        }
        mock_client.get_cost_forecast.return_value = {"Total": {"Amount": "52.30", "Unit": "USD"}}

        with patch("boto3.client", return_value=mock_client):
            estimator = CostEstimator()

        result = estimator.estimate("aws ec2 run-instances --instance-type t3.micro")

        assert result.status == "estimated"
        assert result.estimated_monthly_cost == 52.30
        assert result.confidence == "medium"
        assert result.service == "ec2"
        assert "ec2 (forecast)" in result.cost_breakdown

    def test_falls_back_to_historical_when_forecast_is_zero(self) -> None:
        mock_client = MagicMock()
        mock_client.get_cost_and_usage.return_value = {
            "ResultsByTime": [{"Total": {"UnblendedCost": {"Amount": "30.00", "Unit": "USD"}}}]
        }
        mock_client.get_cost_forecast.return_value = {"Total": {"Amount": "0", "Unit": "USD"}}

        with patch("boto3.client", return_value=mock_client):
            estimator = CostEstimator()

        result = estimator.estimate("aws rds create-db-instance --db-instance-id test")

        assert result.estimated_monthly_cost == 30.00
        assert "rds (historical avg)" in result.cost_breakdown

    def test_low_confidence_when_no_cost_data(self) -> None:
        mock_client = MagicMock()
        mock_client.get_cost_and_usage.return_value = {"ResultsByTime": []}
        mock_client.get_cost_forecast.return_value = {"Total": {"Amount": "0", "Unit": "USD"}}

        with patch("boto3.client", return_value=mock_client):
            estimator = CostEstimator()

        result = estimator.estimate("aws ec2 run-instances --instance-type t3.micro")

        assert result.estimated_monthly_cost == 0.0
        assert result.confidence == "low"


# ---------------------------------------------------------------------------
# Budget alert threshold
# ---------------------------------------------------------------------------


class TestBudgetAlert:
    """Tests for budget alert when cost exceeds max_cost_alert."""

    def test_adds_warning_when_cost_exceeds_threshold(self) -> None:
        mock_client = MagicMock()
        mock_client.get_cost_and_usage.return_value = {
            "ResultsByTime": [{"Total": {"UnblendedCost": {"Amount": "150.00", "Unit": "USD"}}}]
        }
        mock_client.get_cost_forecast.return_value = {"Total": {"Amount": "160.00", "Unit": "USD"}}

        with patch("boto3.client", return_value=mock_client):
            estimator = CostEstimator(max_cost_alert=100)

        result = estimator.estimate("aws ec2 run-instances --instance-type m5.4xlarge")

        assert len(result.warnings) == 1
        assert "exceeds max_cost_alert threshold" in result.warnings[0]
        assert "$100" in result.warnings[0]

    def test_no_warning_when_cost_below_threshold(self) -> None:
        mock_client = MagicMock()
        mock_client.get_cost_and_usage.return_value = {
            "ResultsByTime": [{"Total": {"UnblendedCost": {"Amount": "50.00", "Unit": "USD"}}}]
        }
        mock_client.get_cost_forecast.return_value = {"Total": {"Amount": "55.00", "Unit": "USD"}}

        with patch("boto3.client", return_value=mock_client):
            estimator = CostEstimator(max_cost_alert=100)

        result = estimator.estimate("aws ec2 run-instances --instance-type t3.micro")

        assert result.warnings == []

    def test_custom_threshold_triggers_warning(self) -> None:
        mock_client = MagicMock()
        mock_client.get_cost_and_usage.return_value = {
            "ResultsByTime": [{"Total": {"UnblendedCost": {"Amount": "25.00", "Unit": "USD"}}}]
        }
        mock_client.get_cost_forecast.return_value = {"Total": {"Amount": "30.00", "Unit": "USD"}}

        with patch("boto3.client", return_value=mock_client):
            estimator = CostEstimator(max_cost_alert=20)

        result = estimator.estimate("aws lambda create-function --function-name test")

        assert len(result.warnings) == 1
        assert "$20" in result.warnings[0]


# ---------------------------------------------------------------------------
# Fallback behavior — Cost Explorer API errors
# ---------------------------------------------------------------------------


class TestFallbackBehavior:
    """Tests for graceful fallback when Cost Explorer API fails."""

    def test_returns_unknown_status_on_client_error(self) -> None:
        mock_client = MagicMock()
        mock_client.get_cost_and_usage.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Not authorized"}},
            "GetCostAndUsage",
        )

        with patch("boto3.client", return_value=mock_client):
            estimator = CostEstimator()

        result = estimator.estimate("aws ec2 run-instances --instance-type t3.micro")

        assert result.status == "unknown"
        assert result.estimated_monthly_cost == 0.0
        assert result.confidence == "low"
        assert len(result.warnings) == 1
        assert "Cost estimation unavailable" in result.warnings[0]

    def test_returns_unknown_on_generic_exception(self) -> None:
        mock_client = MagicMock()
        mock_client.get_cost_and_usage.side_effect = RuntimeError("Network timeout")

        with patch("boto3.client", return_value=mock_client):
            estimator = CostEstimator()

        result = estimator.estimate("aws rds create-db-instance --db-instance-id test")

        assert result.status == "unknown"
        assert result.confidence == "low"
        assert "Network timeout" in result.warnings[0]

    def test_forecast_failure_still_uses_historical(self) -> None:
        mock_client = MagicMock()
        mock_client.get_cost_and_usage.return_value = {
            "ResultsByTime": [{"Total": {"UnblendedCost": {"Amount": "75.00", "Unit": "USD"}}}]
        }
        mock_client.get_cost_forecast.side_effect = ClientError(
            {"Error": {"Code": "DataUnavailableException", "Message": "No data"}},
            "GetCostForecast",
        )

        with patch("boto3.client", return_value=mock_client):
            estimator = CostEstimator()

        # The forecast failure is handled internally (returns 0.0),
        # so it falls back to historical
        result = estimator.estimate("aws ec2 run-instances --instance-type t3.micro")

        assert result.status == "estimated"
        assert result.estimated_monthly_cost == 75.00
        assert result.confidence == "medium"


# ---------------------------------------------------------------------------
# CostEstimate model validation
# ---------------------------------------------------------------------------


class TestCostEstimateModel:
    """Tests for CostEstimate Pydantic model."""

    def test_creates_valid_estimate(self) -> None:
        estimate = CostEstimate(
            status="estimated",
            estimated_monthly_cost=45.50,
            confidence="medium",
            service="ec2",
            command="aws ec2 run-instances",
        )
        assert estimate.currency == "USD"
        assert estimate.cost_breakdown == {}
        assert estimate.warnings == []

    def test_estimate_with_all_fields(self) -> None:
        estimate = CostEstimate(
            status="estimated",
            estimated_monthly_cost=120.0,
            currency="USD",
            cost_breakdown={"EC2 hourly": 100.0, "EBS storage": 20.0},
            warnings=["exceeds threshold"],
            confidence="high",
            service="ec2",
            command="aws ec2 run-instances --instance-type m5.xlarge",
        )
        assert estimate.estimated_monthly_cost == 120.0
        assert len(estimate.cost_breakdown) == 2
        assert estimate.warnings == ["exceeds threshold"]
