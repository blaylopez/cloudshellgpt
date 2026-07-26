"""Unit tests for CostEstimator — AWS Cost Explorer integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from cloudshellgpt.cost import CostEstimate, CostEstimator, CostTracker

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


# ---------------------------------------------------------------------------
# CostTracker — session tracking
# ---------------------------------------------------------------------------


class TestCostTracker:
    """Tests for CostTracker session tracking, persistence, and summary."""

    @pytest.mark.unit
    def test_track_adds_entry_to_session(self, tmp_cost_tracker: CostTracker) -> None:
        """Tracking a command persists it to the YAML session file."""
        tmp_cost_tracker.track("aws ec2 run-instances", "$45.50")

        assert tmp_cost_tracker.session_path.exists()
        import yaml

        with tmp_cost_tracker.session_path.open() as f:
            data = yaml.safe_load(f)

        assert len(data) == 1
        assert data[0]["command"] == "aws ec2 run-instances"
        assert data[0]["estimated_cost"] == "$45.50"
        assert "timestamp" in data[0]

    @pytest.mark.unit
    def test_session_summary_with_tracked_items(self, tmp_cost_tracker: CostTracker) -> None:
        """session_summary returns a string containing tracked commands and costs."""
        tmp_cost_tracker.track("aws ec2 run-instances", "$45.50")
        tmp_cost_tracker.track("aws s3 create-bucket", "$3.00")

        summary = tmp_cost_tracker.session_summary()

        assert "aws ec2 run-instances" in summary
        assert "$45.50" in summary
        assert "aws s3 create-bucket" in summary
        assert "$3.00" in summary
        assert "2 operations" in summary

    @pytest.mark.unit
    def test_session_summary_empty(self, tmp_cost_tracker: CostTracker) -> None:
        """session_summary returns a 'no costs' message when nothing tracked."""
        summary = tmp_cost_tracker.session_summary()

        assert "No costs tracked" in summary

    @pytest.mark.unit
    def test_track_truncates_long_commands(self, tmp_cost_tracker: CostTracker) -> None:
        """Commands longer than 200 characters are truncated when persisted."""
        long_command = "aws ec2 run-instances " + "x" * 250

        tmp_cost_tracker.track(long_command, "$10.00")

        import yaml

        with tmp_cost_tracker.session_path.open() as f:
            data = yaml.safe_load(f)

        assert len(data[0]["command"]) == 200

    @pytest.mark.unit
    def test_multiple_tracks_accumulate(self, tmp_cost_tracker: CostTracker) -> None:
        """Multiple track() calls accumulate all entries in the session file."""
        tmp_cost_tracker.track("aws ec2 run-instances", "$45.50")
        tmp_cost_tracker.track("aws rds create-db-instance", "$120.00")
        tmp_cost_tracker.track("aws s3api create-bucket", "$0.50")

        import yaml

        with tmp_cost_tracker.session_path.open() as f:
            data = yaml.safe_load(f)

        assert len(data) == 3
        assert data[0]["command"] == "aws ec2 run-instances"
        assert data[1]["command"] == "aws rds create-db-instance"
        assert data[2]["command"] == "aws s3api create-bucket"

    @pytest.mark.unit
    def test_clear_removes_session_data(self, tmp_cost_tracker: CostTracker) -> None:
        """clear() removes the session file and summary returns empty message."""
        tmp_cost_tracker.track("aws ec2 run-instances", "$45.50")
        tmp_cost_tracker.track("aws s3 ls", "$0.00")

        tmp_cost_tracker.clear()

        assert not tmp_cost_tracker.session_path.exists()
        assert "No costs tracked" in tmp_cost_tracker.session_summary()

    @pytest.mark.unit
    def test_track_with_unknown_cost_string(self, tmp_cost_tracker: CostTracker) -> None:
        """Tracking an item with 'unknown' cost persists correctly and summary works."""
        tmp_cost_tracker.track("aws ec2 run-instances", "unknown")

        import yaml

        with tmp_cost_tracker.session_path.open() as f:
            data = yaml.safe_load(f)

        assert data[0]["estimated_cost"] == "unknown"

        summary = tmp_cost_tracker.session_summary()
        assert "unknown" in summary
        assert "1 operations" in summary

    @pytest.mark.unit
    def test_session_summary_shows_all_costs(self, tmp_cost_tracker: CostTracker) -> None:
        """Summary faithfully includes all tracked costs regardless of amount."""
        tmp_cost_tracker.track("aws ec2 run-instances --instance-type m5.4xlarge", "$160.00")
        tmp_cost_tracker.track("aws s3api create-bucket --bucket test", "$0.50")
        tmp_cost_tracker.track("aws rds create-db-instance", "$250.00")

        summary = tmp_cost_tracker.session_summary()

        assert "$160.00" in summary
        assert "$0.50" in summary
        assert "$250.00" in summary
        assert "3 operations" in summary


# ---------------------------------------------------------------------------
# CostTracker — cumulative session accumulation
# ---------------------------------------------------------------------------


class TestCostTrackerSessionAccumulation:
    """Tests for CostTracker cumulative session tracking behavior.

    Verifies that multiple track() calls accumulate correctly, that order is
    preserved, and that session_summary reflects all tracked items.
    """

    @pytest.mark.unit
    def test_five_tracks_accumulate_in_order(self, tmp_cost_tracker: CostTracker) -> None:
        """Five track() calls persist all entries in insertion order."""
        import yaml

        commands = [
            ("aws ec2 run-instances --instance-type t3.micro", "$45.50"),
            ("aws s3api create-bucket --bucket demo", "$0.50"),
            ("aws rds create-db-instance --db-instance-id prod", "$120.00"),
            ("aws lambda create-function --function-name handler", "$5.00"),
            ("aws dynamodb create-table --table-name users", "$25.00"),
        ]

        for cmd, cost in commands:
            tmp_cost_tracker.track(cmd, cost)

        with tmp_cost_tracker.session_path.open() as f:
            data = yaml.safe_load(f)

        assert len(data) == 5
        for i, (cmd, cost) in enumerate(commands):
            assert data[i]["command"] == cmd
            assert data[i]["estimated_cost"] == cost
            assert "timestamp" in data[i]

    @pytest.mark.unit
    def test_session_summary_reflects_all_five_items(self, tmp_cost_tracker: CostTracker) -> None:
        """session_summary contains all commands, costs, and correct count after 5 tracks."""
        commands = [
            ("aws ec2 run-instances", "$45.50"),
            ("aws s3api create-bucket", "$0.50"),
            ("aws rds create-db-instance", "$120.00"),
            ("aws lambda create-function", "$5.00"),
            ("aws dynamodb create-table", "$25.00"),
        ]

        for cmd, cost in commands:
            tmp_cost_tracker.track(cmd, cost)

        summary = tmp_cost_tracker.session_summary()

        for cmd, cost in commands:
            assert cmd in summary, f"Command '{cmd}' not found in summary"
            assert cost in summary, f"Cost '{cost}' not found in summary"

        assert "5 operations" in summary

    @pytest.mark.unit
    def test_step_by_step_accumulation_does_not_overwrite(
        self, tmp_cost_tracker: CostTracker
    ) -> None:
        """Each individual track() adds to existing entries without overwriting."""
        import yaml

        # Track first entry and verify
        tmp_cost_tracker.track("aws ec2 describe-instances", "$0.00")
        with tmp_cost_tracker.session_path.open() as f:
            data = yaml.safe_load(f)
        assert len(data) == 1
        assert data[0]["command"] == "aws ec2 describe-instances"

        # Track second entry and verify both exist
        tmp_cost_tracker.track("aws s3 ls", "$0.00")
        with tmp_cost_tracker.session_path.open() as f:
            data = yaml.safe_load(f)
        assert len(data) == 2
        assert data[0]["command"] == "aws ec2 describe-instances"
        assert data[1]["command"] == "aws s3 ls"

        # Track third entry and verify all three exist
        tmp_cost_tracker.track("aws rds create-db-instance", "$80.00")
        with tmp_cost_tracker.session_path.open() as f:
            data = yaml.safe_load(f)
        assert len(data) == 3
        assert data[0]["command"] == "aws ec2 describe-instances"
        assert data[1]["command"] == "aws s3 ls"
        assert data[2]["command"] == "aws rds create-db-instance"

        # Track fourth entry and verify accumulation
        tmp_cost_tracker.track("aws lambda invoke --function-name fn out.json", "$0.01")
        with tmp_cost_tracker.session_path.open() as f:
            data = yaml.safe_load(f)
        assert len(data) == 4
        assert data[3]["command"] == "aws lambda invoke --function-name fn out.json"

    @pytest.mark.unit
    def test_clear_then_retrack_shows_only_new_items(self, tmp_cost_tracker: CostTracker) -> None:
        """After clear() and re-tracking, summary only contains new items."""
        # Track initial items
        tmp_cost_tracker.track("aws ec2 run-instances", "$45.50")
        tmp_cost_tracker.track("aws rds create-db-instance", "$120.00")
        tmp_cost_tracker.track("aws s3api create-bucket", "$0.50")

        # Verify initial state
        summary_before = tmp_cost_tracker.session_summary()
        assert "3 operations" in summary_before

        # Clear the session
        tmp_cost_tracker.clear()

        # Track new items
        tmp_cost_tracker.track("aws lambda create-function", "$5.00")
        tmp_cost_tracker.track("aws dynamodb create-table", "$25.00")

        # Verify summary only shows new items
        summary_after = tmp_cost_tracker.session_summary()
        assert "2 operations" in summary_after
        assert "aws lambda create-function" in summary_after
        assert "$5.00" in summary_after
        assert "aws dynamodb create-table" in summary_after
        assert "$25.00" in summary_after

        # Old items must NOT appear
        assert "aws ec2 run-instances" not in summary_after
        assert "$45.50" not in summary_after
        assert "$120.00" not in summary_after

    @pytest.mark.unit
    def test_large_accumulation_twelve_items(self, tmp_cost_tracker: CostTracker) -> None:
        """Tracking 12 items accumulates all and summary includes every one."""
        import yaml

        commands = [
            ("aws ec2 run-instances --instance-type t3.micro", "$45.50"),
            ("aws s3api create-bucket --bucket alpha", "$0.50"),
            ("aws rds create-db-instance --db-instance-id db1", "$120.00"),
            ("aws lambda create-function --function-name fn1", "$5.00"),
            ("aws dynamodb create-table --table-name tbl1", "$25.00"),
            ("aws ecs create-cluster --cluster-name cl1", "$30.00"),
            ("aws eks create-cluster --name eks1", "$73.00"),
            ("aws sqs create-queue --queue-name q1", "$0.40"),
            ("aws sns create-topic --name topic1", "$0.00"),
            ("aws elasticache create-cache-cluster --cache-cluster-id c1", "$50.00"),
            ("aws redshift create-cluster --cluster-identifier rs1", "$200.00"),
            ("aws kinesis create-stream --stream-name s1", "$15.00"),
        ]

        for cmd, cost in commands:
            tmp_cost_tracker.track(cmd, cost)

        # Verify YAML file has all 12 entries
        with tmp_cost_tracker.session_path.open() as f:
            data = yaml.safe_load(f)
        assert len(data) == 12

        # Verify summary contains all commands and costs
        summary = tmp_cost_tracker.session_summary()
        assert "12 operations" in summary

        for cmd, cost in commands:
            # Summary truncates commands at 80 chars, so check the first 80
            truncated_cmd = cmd[:80]
            assert truncated_cmd in summary, f"Command '{truncated_cmd}' not in summary"
            assert cost in summary, f"Cost '{cost}' not in summary"

    @pytest.mark.unit
    def test_accumulation_preserves_timestamps_in_order(
        self, tmp_cost_tracker: CostTracker
    ) -> None:
        """Timestamps in accumulated entries are monotonically non-decreasing."""
        from datetime import datetime

        import yaml

        for i in range(6):
            tmp_cost_tracker.track(f"aws s3api put-object --key file{i}.txt", f"${i}.00")

        with tmp_cost_tracker.session_path.open() as f:
            data = yaml.safe_load(f)

        timestamps = [datetime.fromisoformat(entry["timestamp"]) for entry in data]
        for i in range(len(timestamps) - 1):
            assert timestamps[i] <= timestamps[i + 1], (
                f"Timestamp at index {i} ({timestamps[i]}) is after "
                f"timestamp at index {i + 1} ({timestamps[i + 1]})"
            )
