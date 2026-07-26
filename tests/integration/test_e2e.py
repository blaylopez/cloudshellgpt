"""End-to-end integration tests — full pipeline from intent to formatted output.

Tests the complete flow: IntentParser → BedrockTranslator (mocked) → SafetyLayer (real)
→ AWSExecutor (mocked subprocess) → Formatter (real) → AuditLogger (real, tmp_path).

Uses real modules for IntentParser, SafetyLayer, Formatter, and AuditLogger.
Mocks only Bedrock (boto3 converse) and subprocess (AWS CLI execution).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from cloudshellgpt.audit import AuditLogger
from cloudshellgpt.bedrock_translator import BedrockTranslator, Translation
from cloudshellgpt.cost import CostEstimate
from cloudshellgpt.executor import AWSExecutor
from cloudshellgpt.formatter import Formatter
from cloudshellgpt.intent import IntentParser
from cloudshellgpt.safety import SafetyLayer

# ---------------------------------------------------------------------------
# Helper: build a mock Bedrock converse response
# ---------------------------------------------------------------------------


def _bedrock_response(translation_json: dict[str, Any]) -> dict[str, Any]:
    """Build a mock Bedrock converse() response wrapping a translation JSON.

    Args:
        translation_json: The translation payload the model would return.

    Returns:
        Dict mimicking the Bedrock Converse API response shape.
    """
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": json.dumps(translation_json)}],
            }
        },
        "usage": {"inputTokens": 100, "outputTokens": 60, "totalTokens": 160},
        "stopReason": "end_turn",
        "metrics": {"latencyMs": 300},
    }


def _cost_estimate_unknown(command: str) -> CostEstimate:
    """Build a CostEstimate with status 'unknown' for testing.

    Args:
        command: The command that triggered the estimate.

    Returns:
        A CostEstimate with unknown status (simulating Cost Explorer failure).
    """
    return CostEstimate(
        status="unknown",
        estimated_monthly_cost=0.0,
        cost_breakdown={},
        warnings=[],
        confidence="low",
        service="unknown",
        command=command,
    )


# ---------------------------------------------------------------------------
# Flow 1: List S3 buckets → show table output
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestListFlowShowTable:
    """E2E: 'list S3 buckets' → IntentParser → Bedrock (mocked) → Safety (low)
    → Executor (mocked) → Formatter renders table output."""

    def test_list_s3_buckets_full_pipeline(self, tmp_path: Path) -> None:
        """Full pipeline: list intent produces table output without confirmation."""
        # 1. Parse intent (real IntentParser — rule-based, no mock needed)
        parser = IntentParser()
        intent = parser.parse("list my S3 buckets", region="us-east-1")

        assert intent.service == "s3"
        assert intent.action == "list"
        assert intent.confidence >= 0.5

        # 2. Translate via Bedrock (mocked)
        bedrock_payload = {
            "command": "aws s3api list-buckets --output json",
            "explanation": "Lists all S3 buckets in the account",
            "detailed_explanation": (
                "Uses s3api list-buckets to retrieve all buckets. "
                "Returns bucket names and creation dates."
            ),
            "risk_level": "low",
            "estimated_cost": "$0.00",
            "requires_dry_run": False,
            "affected_resources": [],
            "flags_used": {"--output": "JSON format for programmatic access"},
        }

        with patch("boto3.client") as mock_boto:
            mock_bedrock_client = MagicMock()
            mock_bedrock_client.converse.return_value = _bedrock_response(bedrock_payload)
            mock_boto.return_value = mock_bedrock_client

            translator = BedrockTranslator()
            translation = translator.translate(intent)

        assert translation.command == "aws s3api list-buckets --output json"
        assert translation.risk_level == "low"

        # 3. Safety assessment (real SafetyLayer — should classify as low risk)
        with patch("boto3.client") as mock_boto:
            mock_ce_client = MagicMock()
            mock_boto.return_value = mock_ce_client
            safety = SafetyLayer(region="us-east-1")

        cost_estimate = _cost_estimate_unknown(translation.command)
        check = safety.assess(translation, cost_estimate=cost_estimate)

        assert check.risk_level == "low"
        assert check.requires_confirmation is False
        assert check.requires_dry_run is False

        # 4. Execute (mocked subprocess — simulates AWS CLI returning JSON)
        s3_output = json.dumps(
            {
                "Buckets": [
                    {"Name": "my-app-bucket", "CreationDate": "2024-01-15T10:30:00Z"},
                    {"Name": "logs-bucket", "CreationDate": "2024-02-20T08:15:00Z"},
                    {"Name": "backup-data", "CreationDate": "2024-03-10T14:45:00Z"},
                ]
            }
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=s3_output,
                stderr="",
                returncode=0,
            )
            executor = AWSExecutor(dry_run=False, timeout=30)
            result = executor.run(translation.command)

        assert result.exit_code == 0
        assert "my-app-bucket" in result.stdout
        assert result.dry_run is False

        # 5. Format output (real Formatter — verify it doesn't crash)
        formatter = Formatter(format_type="table", force_tty=True)
        # render() prints to console; we just verify it doesn't raise
        formatter.render(result)

        # 6. Audit logging (real AuditLogger with tmp_path)
        audit = AuditLogger(log_path=tmp_path / "audit.log")
        entry_id = audit.log_before(
            intent="list my S3 buckets",
            command=translation.command,
            risk=check.risk_level,
            dry_run=False,
        )

        assert entry_id is not None
        audit.log_after(entry_id, result)

        # Verify audit log has both entries
        entries = audit.tail(10)
        assert len(entries) == 2
        assert entries[0]["phase"] == "before"
        assert entries[1]["phase"] == "after"
        assert entries[1]["exit_code"] == 0


# ---------------------------------------------------------------------------
# Flow 2: Create EC2 instance → confirm → execute
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCreateFlowConfirmExecute:
    """E2E: 'create an EC2 instance' → IntentParser → Bedrock (mocked)
    → Safety (medium, needs confirmation) → simulate user confirming
    → Executor (mocked) → Formatter renders output."""

    def test_create_ec2_requires_confirmation_then_executes(self, tmp_path: Path) -> None:
        """Full pipeline: create intent triggers medium risk, confirmation,
        then executes successfully."""
        # 1. Parse intent (real IntentParser)
        parser = IntentParser()
        intent = parser.parse("create a t3.micro EC2 instance", region="us-east-1")

        assert intent.service == "ec2"
        assert intent.action == "create"
        assert intent.confidence >= 0.5

        # 2. Translate via Bedrock (mocked)
        bedrock_payload = {
            "command": (
                "aws ec2 run-instances --instance-type t3.micro "
                "--image-id ami-0abcdef1234567890 --count 1 --output json"
            ),
            "explanation": "Launches a t3.micro EC2 instance",
            "detailed_explanation": (
                "Creates one t3.micro instance using the specified AMI. "
                "t3.micro is free-tier eligible. Returns instance ID on success."
            ),
            "risk_level": "medium",
            "estimated_cost": "$8.50/month",
            "requires_dry_run": False,
            "affected_resources": ["ec2:instance/new"],
            "flags_used": {
                "--instance-type": "t3.micro (2 vCPU, 1 GiB RAM)",
                "--count": "Number of instances to launch",
            },
        }

        with patch("boto3.client") as mock_boto:
            mock_bedrock_client = MagicMock()
            mock_bedrock_client.converse.return_value = _bedrock_response(bedrock_payload)
            mock_boto.return_value = mock_bedrock_client

            translator = BedrockTranslator()
            translation = translator.translate(intent)

        assert "run-instances" in translation.command
        assert translation.risk_level == "medium"

        # 3. Safety assessment (real SafetyLayer — should classify as medium)
        with patch("boto3.client") as mock_boto:
            mock_ce_client = MagicMock()
            mock_boto.return_value = mock_ce_client
            safety = SafetyLayer(region="us-east-1")

        cost_estimate = CostEstimate(
            status="estimated",
            estimated_monthly_cost=8.50,
            cost_breakdown={"EC2 hourly": 8.50},
            warnings=[],
            confidence="medium",
            service="ec2",
            command=translation.command,
        )
        check = safety.assess(translation, cost_estimate=cost_estimate)

        assert check.risk_level == "medium"
        assert check.requires_confirmation is True
        assert check.requires_dry_run is False

        # 4. Simulate user confirming (in real CLI, user types 'Y')
        # The confirmation is handled by the CLI's _handle_confirmation().
        # In this test, we assert the check metadata and proceed to execution.
        assert "Proceed?" in check.confirmation_prompt or "Y/n" in check.confirmation_prompt

        # 5. Execute (mocked subprocess — EC2 run-instances response)
        ec2_output = json.dumps(
            {
                "Instances": [
                    {
                        "InstanceId": "i-0abc123def456789",
                        "InstanceType": "t3.micro",
                        "State": {"Name": "pending"},
                        "LaunchTime": "2024-06-15T12:00:00Z",
                    }
                ]
            }
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=ec2_output,
                stderr="",
                returncode=0,
            )
            executor = AWSExecutor(dry_run=False, timeout=30)
            result = executor.run(translation.command)

        assert result.exit_code == 0
        assert "i-0abc123def456789" in result.stdout

        # 6. Format output (real Formatter)
        formatter = Formatter(format_type="json", force_tty=True)
        formatter.render(result)

        # 7. Audit logging
        audit = AuditLogger(log_path=tmp_path / "audit.log")
        entry_id = audit.log_before(
            intent="create a t3.micro EC2 instance",
            command=translation.command,
            risk=check.risk_level,
            dry_run=False,
        )

        assert entry_id is not None
        audit.log_after(entry_id, result)

        entries = audit.tail(10)
        assert len(entries) == 2
        assert entries[0]["risk_level"] == "medium"
        assert entries[1]["exit_code"] == 0


# ---------------------------------------------------------------------------
# Flow 3: Delete all S3 objects recursively → safety blocks
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDeleteFlowSafetyBlocks:
    """E2E: 'delete all S3 objects recursively' → IntentParser → Bedrock (mocked)
    → SafetyLayer (critical risk) → safety requires typed confirmation
    → verify blocking behavior (no execution without confirmation)."""

    def test_recursive_delete_triggers_critical_safety(self, tmp_path: Path) -> None:
        """Full pipeline: recursive delete classified as critical,
        requires dry-run and typed confirmation."""
        # 1. Parse intent (real IntentParser)
        parser = IntentParser()
        intent = parser.parse(
            "delete all S3 objects recursively from prod-bucket",
            region="us-east-1",
        )

        assert intent.service == "s3"
        assert intent.action == "delete"
        assert intent.confidence >= 0.5

        # 2. Translate via Bedrock (mocked)
        bedrock_payload = {
            "command": "aws s3 rm s3://prod-bucket --recursive",
            "explanation": "Deletes ALL objects in prod-bucket recursively",
            "detailed_explanation": (
                "⚠️ IRREVERSIBLE: Removes every object in the bucket. "
                "The bucket itself remains but will be empty. "
                "Consider creating a backup first."
            ),
            "risk_level": "critical",
            "estimated_cost": "$0.00",
            "requires_dry_run": True,
            "affected_resources": ["s3://prod-bucket/*"],
            "flags_used": {"--recursive": "Deletes all objects, not just the first match"},
        }

        with patch("boto3.client") as mock_boto:
            mock_bedrock_client = MagicMock()
            mock_bedrock_client.converse.return_value = _bedrock_response(bedrock_payload)
            mock_boto.return_value = mock_bedrock_client

            translator = BedrockTranslator()
            translation = translator.translate(intent)

        assert translation.command == "aws s3 rm s3://prod-bucket --recursive"
        assert translation.risk_level == "critical"
        assert translation.requires_dry_run is True

        # 3. Safety assessment (real SafetyLayer — must classify as critical)
        with patch("boto3.client") as mock_boto:
            mock_ce_client = MagicMock()
            mock_boto.return_value = mock_ce_client
            safety = SafetyLayer(region="us-east-1")

        cost_estimate = _cost_estimate_unknown(translation.command)
        check = safety.assess(translation, cost_estimate=cost_estimate)

        # Critical because: "rm" + "--recursive" triggers critical pattern
        assert check.risk_level == "critical"
        assert check.requires_confirmation is True
        assert check.requires_dry_run is True

        # Verify the confirmation prompt requires typed confirmation
        assert "yes-i-understand" in check.confirmation_prompt.lower()

        # Verify the check is not marked as reversible (critical = irreversible)
        assert check.reversible is False

        # Verify affected resources are propagated
        assert "s3://prod-bucket/*" in check.affected_resources

        # Verify warnings include cost estimation caveat
        assert any("cost" in w.lower() or "caution" in w.lower() for w in check.warnings)

        # 4. Safety BLOCKS execution — no subprocess should be called
        # In the real CLI, the user would need to type "yes-i-understand"
        # and a dry-run would be performed first. Here we verify the safety
        # layer correctly identifies this as needing blocking.

        # Simulate what happens if the user does NOT confirm:
        # The executor should never be called. We verify by asserting
        # the safety check's blocking properties are set.
        assert check.requires_dry_run is True
        assert check.requires_confirmation is True

        # 5. Verify dry-run injection behavior
        dry_run_result = safety.inject_dry_run(translation.command)
        # s3 rm doesn't support native --dry-run, so it should be preview_only
        assert dry_run_result.preview_only is True
        assert dry_run_result.is_native_dry_run is False

        # 6. Audit logging (even blocked commands should be logged)
        audit = AuditLogger(log_path=tmp_path / "audit.log")
        entry_id = audit.log_before(
            intent="delete all S3 objects recursively from prod-bucket",
            command=translation.command,
            risk=check.risk_level,
            dry_run=True,  # Would be forced to dry-run
        )
        assert entry_id is not None

        entries = audit.tail(10)
        assert len(entries) == 1
        assert entries[0]["risk_level"] == "critical"
        assert entries[0]["dry_run"] is True

    def test_safety_layer_upgrades_llm_risk_when_destructive(self) -> None:
        """SafetyLayer must upgrade risk independently of what the LLM says.

        Even if Bedrock returns risk_level='low', the safety layer's pattern
        detection must override to critical for recursive delete."""
        # Create a translation where LLM underestimates risk
        translation = Translation(
            command="aws s3 rm s3://important-data --recursive",
            explanation="Delete all objects",
            detailed_explanation="Removes everything recursively",
            risk_level="low",  # LLM says low — WRONG!
            estimated_cost="$0.00",
            requires_dry_run=False,
            affected_resources=["s3://important-data/*"],
            flags_used={"--recursive": "Delete all"},
        )

        with patch("boto3.client") as mock_boto:
            mock_ce_client = MagicMock()
            mock_boto.return_value = mock_ce_client
            safety = SafetyLayer(region="us-east-1")

        cost_estimate = _cost_estimate_unknown(translation.command)
        check = safety.assess(translation, cost_estimate=cost_estimate)

        # Safety MUST upgrade to critical (rm + --recursive)
        assert check.risk_level == "critical"
        assert check.requires_confirmation is True
        assert check.requires_dry_run is True

    def test_single_resource_delete_classified_as_high(self) -> None:
        """A single-resource delete (no --recursive) should be high, not critical."""
        translation = Translation(
            command="aws s3api delete-bucket --bucket my-test-bucket",
            explanation="Delete the test bucket",
            detailed_explanation="Removes the bucket (must be empty first)",
            risk_level="high",
            estimated_cost="$0.00",
            requires_dry_run=False,
            affected_resources=["s3://my-test-bucket"],
            flags_used={},
        )

        with patch("boto3.client") as mock_boto:
            mock_ce_client = MagicMock()
            mock_boto.return_value = mock_ce_client
            safety = SafetyLayer(region="us-east-1")

        cost_estimate = _cost_estimate_unknown(translation.command)
        check = safety.assess(translation, cost_estimate=cost_estimate)

        # High risk but NOT critical (no --recursive or force flags)
        assert check.risk_level == "high"
        assert check.requires_confirmation is True
        # High risk doesn't force dry-run unless LLM flagged it
        assert "yes-i-understand" not in check.confirmation_prompt.lower()
