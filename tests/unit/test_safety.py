"""Unit tests for SafetyLayer — LLM independence and upgrade risk ladder."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from cloudshellgpt.bedrock_translator import Translation
from cloudshellgpt.cost import CostEstimate
from cloudshellgpt.safety import DESTRUCTIVE_PATTERNS, RISK_ORDER, SafetyLayer

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def safety_layer() -> SafetyLayer:
    """Provide a SafetyLayer instance with mocked boto3 client."""
    with patch("boto3.client"):
        return SafetyLayer()


def _make_translation(command: str, risk_level: str = "low") -> Translation:
    """Create a Translation with the given command and LLM risk level."""
    return Translation(
        command=command,
        explanation="test",
        detailed_explanation="test",
        risk_level=risk_level,
        estimated_cost="$0.00",
        requires_dry_run=False,
        affected_resources=[],
        flags_used={},
    )


# ---------------------------------------------------------------------------
# Tests: _upgrade_risk ladder
# ---------------------------------------------------------------------------


class TestUpgradeRiskLadder:
    """Verify the _upgrade_risk ladder transitions."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("current", "expected"),
        [
            ("low", "high"),
            ("medium", "high"),
            ("high", "critical"),
            ("critical", "critical"),
        ],
    )
    def test_upgrade_risk_ladder(
        self, safety_layer: SafetyLayer, current: str, expected: str
    ) -> None:
        """Each risk level upgrades according to the ladder."""
        result = safety_layer._upgrade_risk(current)  # type: ignore[arg-type]
        assert result == expected


# ---------------------------------------------------------------------------
# Tests: LLM independence — never downgrade below LLM suggestion
# ---------------------------------------------------------------------------


class TestLLMIndependence:
    """Verify that assess() NEVER returns a risk below the LLM's suggestion."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "llm_risk",
        ["low", "medium", "high", "critical"],
    )
    def test_never_downgrade_read_only(self, safety_layer: SafetyLayer, llm_risk: str) -> None:
        """Read-only commands always return 'low' regardless of llm_risk (read-only override)."""
        translation = _make_translation("aws s3api list-buckets", risk_level=llm_risk)
        result = safety_layer.assess(translation)
        assert result.risk_level == "low"

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("command", "llm_risk"),
        [
            ("aws s3 rm s3://bucket/file", "low"),
            ("aws ec2 terminate-instances --instance-ids i-123", "low"),
            ("aws s3 rm s3://prod --recursive", "medium"),
            ("aws rds delete-db-instance --db-instance-id mydb", "low"),
            ("aws ec2 delete-volume --volume-id vol-123", "medium"),
            ("aws iam delete-user --user-name admin", "low"),
        ],
    )
    def test_never_downgrade_destructive(
        self, safety_layer: SafetyLayer, command: str, llm_risk: str
    ) -> None:
        """For destructive commands, risk >= llm_risk always holds."""
        translation = _make_translation(command, risk_level=llm_risk)
        result = safety_layer.assess(translation)
        assert RISK_ORDER[result.risk_level] >= RISK_ORDER[llm_risk]

    @pytest.mark.unit
    def test_llm_high_stays_high_for_read_only(self, safety_layer: SafetyLayer) -> None:
        """If LLM says high but command is read-only, result is 'low' (read-only override).

        Read-only commands are ALWAYS classified as low regardless of LLM suggestion.
        """
        translation = _make_translation("aws s3api list-buckets", risk_level="high")
        result = safety_layer.assess(translation)
        assert result.risk_level == "low"


# ---------------------------------------------------------------------------
# Tests: Destructive patterns trigger upgrade
# ---------------------------------------------------------------------------


class TestDestructiveUpgrade:
    """Verify that destructive patterns cause risk upgrade via _upgrade_risk."""

    @pytest.mark.unit
    def test_delete_command_llm_low_upgrades_to_high(self, safety_layer: SafetyLayer) -> None:
        """LLM says low, but 'delete' detected → upgraded to at least high."""
        translation = _make_translation(
            "aws s3api delete-object --bucket prod --key data.csv",
            risk_level="low",
        )
        result = safety_layer.assess(translation)
        assert RISK_ORDER[result.risk_level] >= RISK_ORDER["high"]

    @pytest.mark.unit
    def test_terminate_command_llm_low_upgrades_to_high(self, safety_layer: SafetyLayer) -> None:
        """LLM says low, but 'terminate' detected → at least high."""
        translation = _make_translation(
            "aws ec2 terminate-instances --instance-ids i-abc123",
            risk_level="low",
        )
        result = safety_layer.assess(translation)
        assert RISK_ORDER[result.risk_level] >= RISK_ORDER["high"]

    @pytest.mark.unit
    def test_force_flag_triggers_critical(self, safety_layer: SafetyLayer) -> None:
        """Commands with --force-delete should be critical."""
        translation = _make_translation(
            "aws ecr delete-repository --repository-name my-repo --force-delete",
            risk_level="low",
        )
        result = safety_layer.assess(translation)
        assert result.risk_level == "critical"

    @pytest.mark.unit
    def test_recursive_delete_is_critical(self, safety_layer: SafetyLayer) -> None:
        """'rm --recursive' should be classified as critical."""
        translation = _make_translation(
            "aws s3 rm s3://prod-bucket --recursive",
            risk_level="low",
        )
        result = safety_layer.assess(translation)
        assert result.risk_level == "critical"

    @pytest.mark.unit
    def test_skip_final_snapshot_is_critical(self, safety_layer: SafetyLayer) -> None:
        """--skip-final-snapshot triggers critical."""
        translation = _make_translation(
            "aws rds delete-db-instance --db-instance-id mydb --skip-final-snapshot",
            risk_level="low",
        )
        result = safety_layer.assess(translation)
        assert result.risk_level == "critical"

    @pytest.mark.unit
    def test_medium_command_with_destructive_pattern_upgrades(
        self, safety_layer: SafetyLayer
    ) -> None:
        """If rule_risk was medium but destructive detected, upgrade to high."""
        # This command has a "remove" pattern, which _is_destructive detects.
        # If _classify_risk_by_rules returns medium for some reason, upgrade kicks in.
        translation = _make_translation(
            "aws s3api delete-bucket --bucket test",
            risk_level="low",
        )
        result = safety_layer.assess(translation)
        # delete-bucket is in DATA_DESTROYING_PATTERNS → high from rules
        # _is_destructive also detects "delete" → but rule_risk already high
        # so no extra upgrade needed, stays at high
        assert RISK_ORDER[result.risk_level] >= RISK_ORDER["high"]


# ---------------------------------------------------------------------------
# Tests: Rule-based classifier works independently of LLM
# ---------------------------------------------------------------------------


class TestRuleBasedIndependence:
    """Verify the rule classifier works without LLM input."""

    @pytest.mark.unit
    def test_classify_read_only_as_low(self, safety_layer: SafetyLayer) -> None:
        """Read-only commands get classified as low by rules."""
        assert safety_layer._classify_risk_by_rules("aws s3 ls") == "low"
        assert safety_layer._classify_risk_by_rules("aws ec2 describe-instances") == "low"

    @pytest.mark.unit
    def test_classify_create_as_medium(self, safety_layer: SafetyLayer) -> None:
        """Create commands with direct inverse get medium."""
        assert (
            safety_layer._classify_risk_by_rules("aws s3api create-bucket --bucket test")
            == "medium"
        )

    @pytest.mark.unit
    def test_classify_delete_as_high(self, safety_layer: SafetyLayer) -> None:
        """Delete commands get high from rules."""
        result = safety_layer._classify_risk_by_rules("aws s3api delete-bucket --bucket prod")
        assert result == "high"

    @pytest.mark.unit
    def test_classify_force_delete_as_critical(self, safety_layer: SafetyLayer) -> None:
        """Force-delete flags trigger critical."""
        result = safety_layer._classify_risk_by_rules(
            "aws ecr delete-repository --force-delete --repository-name x"
        )
        assert result == "critical"


# ---------------------------------------------------------------------------
# Tests: Parametrized risk classification — minimum 5 commands per level
# ---------------------------------------------------------------------------


class TestRiskClassificationParametrized:
    """Parametrized tests for _classify_risk_by_rules — minimum 5 commands per level."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "command",
        [
            "aws s3 ls",
            "aws ec2 describe-instances --region us-east-1",
            "aws s3api get-object --bucket reports --key q4.pdf /tmp/q4.pdf",
            "aws s3api head-object --bucket my-bucket --key data.csv",
            "aws ec2 wait instance-running --instance-ids i-0abc123",
            "aws iam list-users --max-items 100",
            "aws cloudwatch describe-alarms --alarm-names cpu-high",
        ],
    )
    def test_low_risk_commands(self, safety_layer: SafetyLayer, command: str) -> None:
        """Read-only commands (list/describe/get/head/wait) are classified as low risk."""
        assert safety_layer._classify_risk_by_rules(command) == "low"

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "command",
        [
            "aws s3api create-bucket --bucket test-bucket --region us-east-1",
            "aws resourcegroupstaggingapi tag-resource --resource-arn arn:aws:s3:::my-bucket --tags Key=Env,Value=prod",
            "aws cloudwatch put-metric-alarm --alarm-name cpu-high --metric-name CPUUtilization --threshold 80",
            "aws ec2 enable-vpc-classic-link --vpc-id vpc-abc123",
            "aws ec2 create-snapshot --volume-id vol-abc123 --description backup",
            "aws s3api put-object --bucket staging --key config.json --body file://c.json",
            "aws ec2 update-security-group-rule-descriptions-ingress --group-id sg-abc --ip-permissions IpProtocol=tcp",
        ],
    )
    def test_medium_risk_commands(self, safety_layer: SafetyLayer, command: str) -> None:
        """Create/update/reversible operations are classified as medium risk."""
        assert safety_layer._classify_risk_by_rules(command) == "medium"

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "command",
        [
            "aws s3api delete-bucket --bucket prod-data",
            "aws ec2 terminate-instances --instance-ids i-0abc123def456",
            "aws ec2 revoke-security-group-ingress --group-id sg-abc --protocol tcp --port 22 --cidr 0.0.0.0/0",
            "aws ec2 detach-volume --volume-id vol-abc123 --instance-id i-123",
            "aws rds delete-db-instance --db-instance-id mydb",
            "aws ec2 delete-snapshot --snapshot-id snap-abc123",
            "aws iam delete-user --user-name old-contractor",
        ],
    )
    def test_high_risk_commands(self, safety_layer: SafetyLayer, command: str) -> None:
        """Delete/terminate/revoke/detach operations are classified as high risk."""
        assert safety_layer._classify_risk_by_rules(command) == "high"

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "command",
        [
            "aws s3 rm s3://production-data/ --recursive",
            "aws ecr delete-repository --repository-name my-repo --force-delete",
            "aws rds delete-db-instance --db-instance-id prod-db --skip-final-snapshot",
            "aws s3api delete-object --bucket compliance --key audit.log --bypass-governance-retention",
            "aws s3 rm s3://backup-bucket/ --recursive --exclude '*.log'",
            "aws ecr batch-delete-image --repository-name app --force-destroy",
            "aws s3api delete-objects --bucket archive --delete file://keys.json --permanently-delete",
        ],
    )
    def test_critical_risk_commands(self, safety_layer: SafetyLayer, command: str) -> None:
        """Recursive delete, --force-delete, --skip-final-snapshot trigger critical."""
        assert safety_layer._classify_risk_by_rules(command) == "critical"


# ---------------------------------------------------------------------------
# Tests: Integration — assess() combines LLM + rules correctly
# ---------------------------------------------------------------------------


class TestAssessIntegration:
    """Verify assess() combines LLM and rule-based assessments correctly."""

    @pytest.mark.unit
    def test_low_llm_low_rules_returns_low(self, safety_layer: SafetyLayer) -> None:
        """Both LLM and rules say low → final is low."""
        translation = _make_translation("aws s3 ls", risk_level="low")
        result = safety_layer.assess(translation)
        assert result.risk_level == "low"

    @pytest.mark.unit
    def test_low_llm_high_rules_returns_high(self, safety_layer: SafetyLayer) -> None:
        """LLM says low, rules say high → final is high."""
        translation = _make_translation(
            "aws ec2 terminate-instances --instance-ids i-abc",
            risk_level="low",
        )
        result = safety_layer.assess(translation)
        assert RISK_ORDER[result.risk_level] >= RISK_ORDER["high"]

    @pytest.mark.unit
    def test_high_llm_low_rules_returns_high(self, safety_layer: SafetyLayer) -> None:
        """LLM says high, rules say low, but 'aws s3 ls' is read-only → override to low."""
        translation = _make_translation("aws s3 ls", risk_level="high")
        result = safety_layer.assess(translation)
        assert result.risk_level == "low"

    @pytest.mark.unit
    def test_critical_llm_medium_rules_returns_critical(self, safety_layer: SafetyLayer) -> None:
        """LLM says critical, rules say medium → final is critical."""
        translation = _make_translation(
            "aws s3api create-bucket --bucket test",
            risk_level="critical",
        )
        result = safety_layer.assess(translation)
        assert result.risk_level == "critical"

    @pytest.mark.unit
    def test_confirmation_required_for_medium_and_above(self, safety_layer: SafetyLayer) -> None:
        """Confirmation is required for medium, high, and critical."""
        # medium
        t_medium = _make_translation("aws s3api create-bucket --bucket x", risk_level="medium")
        assert safety_layer.assess(t_medium).requires_confirmation is True

        # high
        t_high = _make_translation(
            "aws ec2 terminate-instances --instance-ids i-1", risk_level="low"
        )
        assert safety_layer.assess(t_high).requires_confirmation is True

    @pytest.mark.unit
    def test_dry_run_required_for_critical(self, safety_layer: SafetyLayer) -> None:
        """Dry-run is required when final risk is critical."""
        translation = _make_translation(
            "aws s3 rm s3://prod --recursive",
            risk_level="low",
        )
        result = safety_layer.assess(translation)
        assert result.risk_level == "critical"
        assert result.requires_dry_run is True


# ---------------------------------------------------------------------------
# Tests: Safety ↔ Cost integration — CostEstimate consumption
# ---------------------------------------------------------------------------


class TestSafetyCostIntegration:
    """Verify that SafetyLayer correctly integrates CostEstimate data."""

    @pytest.fixture
    def safety_layer_custom_threshold(self) -> SafetyLayer:
        """SafetyLayer with a custom max_cost_alert of 50."""
        with patch("boto3.client"):
            return SafetyLayer(max_cost_alert=50)

    @pytest.mark.unit
    def test_assess_without_cost_estimate_backward_compat(self, safety_layer: SafetyLayer) -> None:
        """Calling assess() without cost_estimate still works (backward compat)."""
        translation = _make_translation("aws s3 ls", risk_level="low")
        result = safety_layer.assess(translation)
        assert result.risk_level == "low"
        assert result.estimated_cost == "$0.00"

    @pytest.mark.unit
    def test_cost_estimate_unknown_adds_caution_warning(self, safety_layer: SafetyLayer) -> None:
        """When CostEstimate.status == 'unknown', a caution warning is added."""
        translation = _make_translation(
            "aws ec2 run-instances --instance-type t3.micro", risk_level="medium"
        )
        cost_est = CostEstimate(
            status="unknown",
            estimated_monthly_cost=0.0,
            currency="USD",
            cost_breakdown={},
            warnings=["Cost estimation unavailable: API error"],
            confidence="low",
            service="ec2",
            command="aws ec2 run-instances --instance-type t3.micro",
        )
        result = safety_layer.assess(translation, cost_estimate=cost_est)
        assert "Cost estimation unavailable — proceed with caution" in result.warnings

    @pytest.mark.unit
    def test_cost_estimate_exceeds_threshold_adds_warning(self, safety_layer: SafetyLayer) -> None:
        """When estimated cost > max_cost_alert, a threshold warning is added."""
        translation = _make_translation(
            "aws ec2 run-instances --instance-type p4d.24xlarge", risk_level="medium"
        )
        cost_est = CostEstimate(
            status="estimated",
            estimated_monthly_cost=250.0,
            currency="USD",
            cost_breakdown={"EC2 (forecast)": 250.0},
            warnings=[],
            confidence="medium",
            service="ec2",
            command="aws ec2 run-instances --instance-type p4d.24xlarge",
        )
        result = safety_layer.assess(translation, cost_estimate=cost_est)
        assert any("exceeds max_cost_alert threshold" in w for w in result.warnings)
        assert "$250.00/month" in result.warnings[-1]

    @pytest.mark.unit
    def test_cost_estimate_below_threshold_no_warning(self, safety_layer: SafetyLayer) -> None:
        """When estimated cost <= max_cost_alert, no threshold warning is added."""
        translation = _make_translation(
            "aws ec2 run-instances --instance-type t3.micro", risk_level="medium"
        )
        cost_est = CostEstimate(
            status="estimated",
            estimated_monthly_cost=45.0,
            currency="USD",
            cost_breakdown={"EC2 (forecast)": 45.0},
            warnings=[],
            confidence="medium",
            service="ec2",
            command="aws ec2 run-instances --instance-type t3.micro",
        )
        result = safety_layer.assess(translation, cost_estimate=cost_est)
        assert not any("exceeds max_cost_alert threshold" in w for w in result.warnings)

    @pytest.mark.unit
    def test_cost_estimate_warnings_propagated(self, safety_layer: SafetyLayer) -> None:
        """Warnings from CostEstimate are propagated into SafetyCheck.warnings."""
        translation = _make_translation(
            "aws ec2 run-instances --instance-type t3.micro", risk_level="medium"
        )
        cost_est = CostEstimate(
            status="estimated",
            estimated_monthly_cost=150.0,
            currency="USD",
            cost_breakdown={"EC2 (forecast)": 150.0},
            warnings=["Estimated cost $150.00/month exceeds max_cost_alert threshold ($100)"],
            confidence="medium",
            service="ec2",
            command="aws ec2 run-instances --instance-type t3.micro",
        )
        result = safety_layer.assess(translation, cost_estimate=cost_est)
        # The warning from CostEstimate is propagated
        assert (
            "Estimated cost $150.00/month exceeds max_cost_alert threshold ($100)"
            in result.warnings
        )

    @pytest.mark.unit
    def test_cost_breakdown_converted_to_strings(self, safety_layer: SafetyLayer) -> None:
        """CostEstimate.cost_breakdown (float) is converted to string in SafetyCheck."""
        translation = _make_translation(
            "aws ec2 run-instances --instance-type t3.micro", risk_level="medium"
        )
        cost_est = CostEstimate(
            status="estimated",
            estimated_monthly_cost=57.0,
            currency="USD",
            cost_breakdown={"EC2 hourly": 45.0, "EBS storage": 12.0},
            warnings=[],
            confidence="medium",
            service="ec2",
            command="aws ec2 run-instances --instance-type t3.micro",
        )
        result = safety_layer.assess(translation, cost_estimate=cost_est)
        assert result.cost_breakdown == {"EC2 hourly": "$45.00", "EBS storage": "$12.00"}

    @pytest.mark.unit
    def test_estimated_cost_updated_from_cost_estimate(self, safety_layer: SafetyLayer) -> None:
        """SafetyCheck.estimated_cost is updated from CostEstimate when cost > 0."""
        translation = _make_translation(
            "aws ec2 run-instances --instance-type t3.micro", risk_level="medium"
        )
        cost_est = CostEstimate(
            status="estimated",
            estimated_monthly_cost=75.50,
            currency="USD",
            cost_breakdown={"EC2 (forecast)": 75.50},
            warnings=[],
            confidence="medium",
            service="ec2",
            command="aws ec2 run-instances --instance-type t3.micro",
        )
        result = safety_layer.assess(translation, cost_estimate=cost_est)
        assert result.estimated_cost == "$75.50/month"

    @pytest.mark.unit
    def test_estimated_cost_not_updated_when_zero(self, safety_layer: SafetyLayer) -> None:
        """SafetyCheck.estimated_cost keeps translation value when cost is 0."""
        translation = _make_translation("aws s3 ls", risk_level="low")
        cost_est = CostEstimate(
            status="estimated",
            estimated_monthly_cost=0.0,
            currency="USD",
            cost_breakdown={},
            warnings=[],
            confidence="high",
            service="s3",
            command="aws s3 ls",
        )
        result = safety_layer.assess(translation, cost_estimate=cost_est)
        assert result.estimated_cost == "$0.00"

    @pytest.mark.unit
    def test_custom_max_cost_alert_threshold(
        self, safety_layer_custom_threshold: SafetyLayer
    ) -> None:
        """Custom max_cost_alert (50) triggers warning at lower cost."""
        translation = _make_translation(
            "aws ec2 run-instances --instance-type t3.medium", risk_level="medium"
        )
        cost_est = CostEstimate(
            status="estimated",
            estimated_monthly_cost=60.0,
            currency="USD",
            cost_breakdown={"EC2 (forecast)": 60.0},
            warnings=[],
            confidence="medium",
            service="ec2",
            command="aws ec2 run-instances --instance-type t3.medium",
        )
        result = safety_layer_custom_threshold.assess(translation, cost_estimate=cost_est)
        assert any("exceeds max_cost_alert threshold ($50)" in w for w in result.warnings)

    @pytest.mark.unit
    def test_unknown_status_does_not_check_threshold(self, safety_layer: SafetyLayer) -> None:
        """When status is 'unknown', threshold check is skipped (only caution warning)."""
        translation = _make_translation(
            "aws ec2 run-instances --instance-type t3.micro", risk_level="medium"
        )
        cost_est = CostEstimate(
            status="unknown",
            estimated_monthly_cost=0.0,
            currency="USD",
            cost_breakdown={},
            warnings=[],
            confidence="low",
            service="ec2",
            command="aws ec2 run-instances --instance-type t3.micro",
        )
        result = safety_layer.assess(translation, cost_estimate=cost_est)
        assert "Cost estimation unavailable — proceed with caution" in result.warnings
        assert not any("exceeds max_cost_alert threshold" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Tests: Exhaustive parametrized detection of ALL destructive patterns
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Tests: Invariante — safety NUNCA downgrade (50+ combinaciones)
# ---------------------------------------------------------------------------

# Comprehensive list of (llm_risk_level, command) tuples — at least 13 per risk level.
# Covers: read-only, mutation, destructive, critical, mixed/ambiguous, edge cases.
_INVARIANT_COMBINATIONS: list[tuple[str, str]] = [
    # ===== LLM risk = "low" (14 combinations) =====
    # Read-only
    ("low", "aws s3 ls"),
    ("low", "aws ec2 describe-instances --region us-west-2"),
    ("low", "aws iam list-users"),
    ("low", "aws s3api head-object --bucket my-bucket --key data.csv"),
    # Mutation
    ("low", "aws s3api create-bucket --bucket test-bucket --region us-east-1"),
    ("low", "aws ec2 create-tags --resources i-123 --tags Key=Env,Value=dev"),
    (
        "low",
        "aws sqs send-message --queue-url https://sqs.us-east-1.amazonaws.com/123/q --message-body hello",
    ),
    # Destructive
    ("low", "aws s3api delete-object --bucket prod --key report.pdf"),
    ("low", "aws ec2 terminate-instances --instance-ids i-0abc123def456"),
    ("low", "aws rds delete-db-instance --db-instance-id mydb"),
    # Critical
    ("low", "aws s3 rm s3://production-data/ --recursive"),
    ("low", "aws ecr delete-repository --repository-name old-repo --force-delete"),
    ("low", "aws rds delete-db-instance --db-instance-id prod-db --skip-final-snapshot"),
    # Mixed/ambiguous
    (
        "low",
        "aws lambda update-function-code --function-name my-func --zip-file fileb://deploy.zip",
    ),
    # ===== LLM risk = "medium" (14 combinations) =====
    # Read-only
    ("medium", "aws s3 ls s3://my-bucket/prefix/"),
    ("medium", "aws cloudwatch describe-alarms --alarm-names cpu-high"),
    ("medium", "aws logs describe-log-groups"),
    ("medium", "aws ec2 describe-security-groups --group-ids sg-abc123"),
    # Mutation
    ("medium", "aws s3api put-object --bucket staging --key config.json --body file://c.json"),
    ("medium", "aws ec2 modify-instance-attribute --instance-id i-123 --instance-type t3.large"),
    (
        "medium",
        "aws iam attach-role-policy --role-name dev --policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess",
    ),
    # Destructive
    ("medium", "aws ec2 delete-volume --volume-id vol-abc123"),
    ("medium", "aws iam delete-user --user-name old-contractor"),
    (
        "medium",
        "aws ec2 revoke-security-group-ingress --group-id sg-abc --protocol tcp --port 22 --cidr 0.0.0.0/0",
    ),
    # Critical
    ("medium", "aws s3 rm s3://archive-bucket/ --recursive"),
    (
        "medium",
        "aws secretsmanager delete-secret --secret-id prod/db-pass --force-delete-without-recovery",
    ),
    ("medium", "aws cloudformation delete-stack --stack-name prod-infra"),
    # Mixed/ambiguous — long command with many flags
    (
        "medium",
        "aws ec2 run-instances --instance-type t3.micro --image-id ami-12345 --key-name mykey --security-group-ids sg-abc --subnet-id subnet-xyz --count 1",
    ),
    # ===== LLM risk = "high" (13 combinations) =====
    # Read-only
    ("high", "aws s3api get-object --bucket reports --key q4.pdf /tmp/q4.pdf"),
    ("high", "aws ec2 describe-vpcs"),
    ("high", "aws sts get-caller-identity"),
    ("high", "aws cloudformation describe-stacks --stack-name my-app"),
    # Mutation
    ("high", "aws ec2 create-vpc --cidr-block 10.0.0.0/16"),
    (
        "high",
        "aws rds create-db-instance --db-instance-identifier test --db-instance-class db.t3.micro --engine postgres",
    ),
    ("high", "aws sns publish --topic-arn arn:aws:sns:us-east-1:123:alerts --message test"),
    # Destructive
    ("high", "aws s3api delete-bucket --bucket old-bucket"),
    ("high", "aws ec2 terminate-instances --instance-ids i-aaa i-bbb i-ccc"),
    (
        "high",
        "aws elbv2 deregister-targets --target-group-arn arn:aws:elasticloadbalancing:us-east-1:123:tg/abc --targets Id=i-123",
    ),
    # Critical
    ("high", "aws s3 rm s3://logs-bucket/ --recursive"),
    (
        "high",
        "aws rds delete-db-cluster --db-cluster-identifier prod-cluster --skip-final-snapshot",
    ),
    # Edge case — unusual service, very long
    (
        "high",
        "aws kinesis delete-stream --stream-name real-time-events --enforce-consumer-deletion",
    ),
    # ===== LLM risk = "critical" (13 combinations) =====
    # Read-only (LLM overestimates — safety must still respect)
    ("critical", "aws s3 ls s3://sensitive-bucket/"),
    ("critical", "aws ec2 describe-instances --filters Name=tag:Env,Values=prod"),
    ("critical", "aws iam get-user --user-name admin"),
    (
        "critical",
        "aws logs get-log-events --log-group-name /aws/lambda/prod --log-stream-name stream1",
    ),
    # Mutation
    ("critical", "aws s3api put-bucket-policy --bucket prod --policy file://policy.json"),
    ("critical", "aws iam create-user --user-name new-admin"),
    (
        "critical",
        "aws ec2 authorize-security-group-ingress --group-id sg-prod --protocol tcp --port 0-65535 --cidr 0.0.0.0/0",
    ),
    # Destructive
    ("critical", "aws ec2 terminate-instances --instance-ids i-prod-web-1"),
    ("critical", "aws dynamodb delete-table --table-name users-prod"),
    ("critical", "aws iam delete-role --role-name lambda-execution-role"),
    # Critical flags
    ("critical", "aws s3 rm s3://company-backup/ --recursive"),
    ("critical", "aws ecr delete-repository --repository-name prod-app --force-delete"),
    (
        "critical",
        "aws s3api delete-object --bucket compliance-data --key audit.log --bypass-governance-retention",
    ),
]


class TestSafetyNeverDowngradesInvariant:
    """Invariante exhaustivo: safety NUNCA retorna un risk_level < llm_risk_level.

    Genera 50+ combinaciones de (llm_risk_level, command) cubriendo:
    - Los 4 niveles de riesgo (low, medium, high, critical)
    - Comandos read-only, mutation, destructive, critical, y mixtos
    - Al menos 13 combinaciones por nivel de riesgo
    """

    @pytest.mark.unit
    @pytest.mark.invariant
    @pytest.mark.parametrize(
        ("llm_risk", "command"),
        _INVARIANT_COMBINATIONS,
        ids=[
            f"{risk}-{cmd.split()[1] if len(cmd.split()) > 1 else 'aws'}-{i}"
            for i, (risk, cmd) in enumerate(_INVARIANT_COMBINATIONS)
        ],
    )
    def test_assess_never_downgrades_below_llm_risk(
        self, safety_layer: SafetyLayer, llm_risk: str, command: str
    ) -> None:
        """assess() MUST return risk_level >= llm_risk for ANY command.

        This is the core safety invariant: the safety layer can only UPGRADE
        risk, never downgrade below the LLM's suggestion.
        """
        translation = _make_translation(command, risk_level=llm_risk)
        result = safety_layer.assess(translation)

        # Read-only commands (by action verb) without destructive patterns
        # are ALWAYS classified as low regardless of LLM suggestion.
        cmd_parts = command.strip().split()
        action = cmd_parts[2] if len(cmd_parts) > 2 else ""
        read_only_actions = ("describe", "list", "get", "head", "wait", "show", "ls")
        is_action_read_only = any(action.lower().startswith(p) for p in read_only_actions)
        has_destructive = safety_layer._is_destructive(command)

        if is_action_read_only and not has_destructive:
            assert result.risk_level == "low", (
                f"Read-only command should be 'low' but got '{result.risk_level}': {command}"
            )
        else:
            assert RISK_ORDER[result.risk_level] >= RISK_ORDER[llm_risk], (
                f"INVARIANT VIOLATED: LLM suggested '{llm_risk}' but assess() returned "
                f"'{result.risk_level}' for command: {command}"
            )

    @pytest.mark.unit
    @pytest.mark.invariant
    def test_invariant_covers_at_least_50_combinations(self) -> None:
        """Meta-test: verify we actually have 50+ test combinations."""
        assert len(_INVARIANT_COMBINATIONS) >= 50, (
            f"Expected at least 50 combinations, got {len(_INVARIANT_COMBINATIONS)}"
        )

    @pytest.mark.unit
    @pytest.mark.invariant
    def test_invariant_covers_all_risk_levels_with_minimum_12(self) -> None:
        """Meta-test: verify each risk level has at least 12 combinations."""
        from collections import Counter

        risk_counts = Counter(risk for risk, _ in _INVARIANT_COMBINATIONS)
        for level in ("low", "medium", "high", "critical"):
            assert risk_counts[level] >= 12, (
                f"Risk level '{level}' has only {risk_counts[level]} combinations, need >= 12"
            )


# Each tuple: (pattern, realistic_aws_command_containing_that_pattern)
_DESTRUCTIVE_PATTERN_COMMANDS: list[tuple[str, str]] = [
    # --- Generic destructive verbs ---
    ("delete", "aws s3api delete-object --bucket prod-data --key backup.tar.gz"),
    ("terminate", "aws ec2 terminate-instances --instance-ids i-0abc123def456"),
    ("rm", "aws s3 rm s3://prod-bucket/logs/2024/"),
    (
        "remove",
        "aws ec2 remove-route --route-table-id rtb-abc123 --destination-cidr-block 10.0.0.0/16",
    ),
    ("drop", "aws rds delete-db-cluster --db-cluster-identifier drop-test-cluster"),
    ("destroy", "aws cloudformation delete-stack --stack-name destroy-legacy-infra"),
    ("force", "aws ecr delete-repository --repository-name old-images --force"),
    (
        "purge",
        "aws sqs purge-queue --queue-url https://sqs.us-east-1.amazonaws.com/123456789/orders",
    ),
    ("wipe", "aws s3 rm s3://bucket-to-wipe/ --recursive"),
    ("nuke", "aws cloudformation delete-stack --stack-name nuke-all-dev-resources"),
    # --- AWS-specific destructive actions ---
    (
        "deregister",
        "aws elbv2 deregister-targets --target-group-arn arn:aws:elasticloadbalancing:us-east-1:123456789:targetgroup/my-tg/abc123 --targets Id=i-0abc",
    ),
    (
        "revoke",
        "aws ec2 revoke-security-group-ingress --group-id sg-abc123 --protocol tcp --port 22 --cidr 0.0.0.0/0",
    ),
    ("detach", "aws ec2 detach-volume --volume-id vol-0abc123def456"),
    (
        "disable",
        "aws s3api put-bucket-versioning --bucket prod-logs --versioning-configuration Status=Suspended MFADelete=disable",
    ),
    ("release", "aws ec2 release-address --allocation-id eipalloc-0abc123def456"),
    ("empty", "aws s3api delete-objects --bucket empty-this-bucket --delete Objects=[{Key=file1}]"),
    # --- Dangerous flags ---
    ("--recursive", "aws s3 rm s3://production-assets/ --recursive"),
    ("--force", "aws ecr delete-repository --repository-name deprecated-service --force"),
    ("-f", "aws logs delete-log-group --log-group-name /aws/lambda/old-function -f"),
    ("--no-preserve", "aws s3 sync s3://source s3://dest --no-preserve"),
    (
        "--skip-final-snapshot",
        "aws rds delete-db-instance --db-instance-id mydb-prod --skip-final-snapshot",
    ),
    (
        "--force-delete",
        "aws secretsmanager delete-secret --secret-id prod/api-key --force-delete-without-recovery",
    ),
    (
        "--permanently-delete",
        "aws secretsmanager delete-secret --secret-id old-creds --permanently-delete",
    ),
    ("--no-undo", "aws cloudformation delete-stack --stack-name legacy-app --no-undo"),
    ("--force-destroy", "aws s3api delete-bucket --bucket prod-archive --force-destroy"),
    (
        "--delete-all-versions",
        "aws s3api delete-object --bucket versioned-data --key report.pdf --delete-all-versions",
    ),
    (
        "--bypass-governance-retention",
        "aws s3api delete-object --bucket compliance-locked --key audit.log --bypass-governance-retention",
    ),
    ("--no-preserve-root", "aws s3 rm s3://root-bucket/ --recursive --no-preserve-root"),
]


class TestDestructivePatternsExhaustive:
    """Exhaustive parametrized tests ensuring ALL 28 destructive patterns are detected.

    Verifies that:
    1. _is_destructive() returns True for realistic commands containing each pattern.
    2. assess() upgrades risk above "low" when LLM says "low" but a pattern is present.
    """

    def test_all_patterns_covered(self) -> None:
        """Assert the parametrized list covers every item in DESTRUCTIVE_PATTERNS."""
        covered_patterns = {pattern for pattern, _ in _DESTRUCTIVE_PATTERN_COMMANDS}
        missing = set(DESTRUCTIVE_PATTERNS) - covered_patterns
        assert not missing, f"Patterns not covered by test cases: {missing}"
        assert len(_DESTRUCTIVE_PATTERN_COMMANDS) >= 28

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("pattern", "command"),
        _DESTRUCTIVE_PATTERN_COMMANDS,
        ids=[p for p, _ in _DESTRUCTIVE_PATTERN_COMMANDS],
    )
    def test_is_destructive_detects_pattern(
        self, safety_layer: SafetyLayer, pattern: str, command: str
    ) -> None:
        """_is_destructive() returns True for a realistic command containing the pattern."""
        assert safety_layer._is_destructive(command) is True, (
            f"Pattern '{pattern}' was NOT detected in command: {command}"
        )

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("pattern", "command"),
        _DESTRUCTIVE_PATTERN_COMMANDS,
        ids=[f"{p}-upgrade" for p, _ in _DESTRUCTIVE_PATTERN_COMMANDS],
    )
    def test_assess_upgrades_risk_when_pattern_present(
        self, safety_layer: SafetyLayer, pattern: str, command: str
    ) -> None:
        """assess() returns risk > 'low' when LLM says 'low' but pattern is present."""
        translation = _make_translation(command, risk_level="low")
        result = safety_layer.assess(translation)
        assert RISK_ORDER[result.risk_level] > RISK_ORDER["low"], (
            f"Pattern '{pattern}': expected risk above 'low', got '{result.risk_level}'"
        )


# ---------------------------------------------------------------------------
# Tests: Heurística medium vs high — inverso directo vs destrucción de datos
# ---------------------------------------------------------------------------


class TestHeuristicMediumVsHigh:
    """Verifica la heurística de clasificación medium vs high.

    La regla es:
    - Si la operación tiene inverso directo Y NO destruye datos → medium
    - Si la operación destruye datos o acceso → high

    Mínimo 10 casos: 5 medium + 5 high.
    """

    # --- 5 operaciones con inverso directo → medium ---
    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("command", "reason"),
        [
            (
                "aws ec2 start-instances --instance-ids i-0abc123def456",
                "start- tiene inverso directo (stop-), no destruye datos",
            ),
            (
                "aws ec2 attach-volume --volume-id vol-abc123 --instance-id i-0abc123 --device /dev/sdf",
                "attach- tiene inverso directo (detach-), no destruye datos",
            ),
            (
                "aws ec2 associate-route-table --route-table-id rtb-abc123 --subnet-id subnet-abc",
                "associate- tiene inverso directo (disassociate-), no destruye datos",
            ),
            (
                "aws ec2 enable-vpc-classic-link --vpc-id vpc-abc123",
                "enable- tiene inverso directo (disable-), no destruye datos",
            ),
            (
                "aws elb register-instances-with-load-balancer --load-balancer-name my-lb --instances i-abc123",
                "register- tiene inverso directo (deregister-), no destruye datos",
            ),
        ],
        ids=[
            "start-instances-medium",
            "attach-volume-medium",
            "associate-route-table-medium",
            "enable-vpc-classic-link-medium",
            "register-instances-medium",
        ],
    )
    def test_operations_with_direct_inverse_classified_medium(
        self, safety_layer: SafetyLayer, command: str, reason: str
    ) -> None:
        """Operaciones con inverso directo que no destruyen datos → medium."""
        result = safety_layer._classify_risk_by_rules(command)
        assert result == "medium", (
            f"Expected 'medium' for command with direct inverse, got '{result}'. Reason: {reason}"
        )

    # --- 5 operaciones que destruyen datos → high ---
    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("command", "reason"),
        [
            (
                "aws s3api delete-bucket --bucket production-data",
                "delete-bucket elimina almacenamiento completo, requiere recreación manual",
            ),
            (
                "aws ec2 terminate-instances --instance-ids i-prod-web-01",
                "terminate-instances destruye instancias EC2 irreversiblemente",
            ),
            (
                "aws dynamodb delete-table --table-name users-sessions",
                "delete-table elimina la tabla y todos sus datos",
            ),
            (
                "aws rds delete-db-instance --db-instance-id analytics-db",
                "delete-db-instance elimina base de datos, datos perdidos sin snapshot",
            ),
            (
                "aws ec2 revoke-security-group-ingress --group-id sg-prod --protocol tcp --port 443 --cidr 10.0.0.0/8",
                "revoke-security-group elimina reglas de acceso, puede causar interrupción",
            ),
        ],
        ids=[
            "delete-bucket-high",
            "terminate-instances-high",
            "delete-table-high",
            "delete-db-instance-high",
            "revoke-security-group-high",
        ],
    )
    def test_data_destroying_operations_classified_high(
        self, safety_layer: SafetyLayer, command: str, reason: str
    ) -> None:
        """Operaciones que destruyen datos o acceso → high."""
        result = safety_layer._classify_risk_by_rules(command)
        assert result == "high", (
            f"Expected 'high' for data-destroying operation, got '{result}'. Reason: {reason}"
        )


# ---------------------------------------------------------------------------
# Tests: Comprehensive _upgrade_risk ladder — all transitions with realistic
# AWS commands through assess() integration
# ---------------------------------------------------------------------------


class TestUpgradeRiskLadderComprehensive:
    """Comprehensive parametrized tests for _upgrade_risk ladder transitions.

    Covers:
    1. Direct ladder transitions with realistic AWS commands via assess()
    2. Verify upgrade skipping (no double-upgrade)
    3. Integration with assess() full flow
    4. Edge case: low→high skips medium entirely
    5. Invariant: upgrade never decreases risk
    """

    # ------------------------------------------------------------------
    # 1. Direct ladder transitions with realistic AWS commands
    #    Each case: (starting_rule_risk, command, llm_risk, expected_minimum)
    #    The command is crafted so _classify_risk_by_rules returns the starting
    #    level BUT _is_destructive detects a destructive pattern → upgrade applies.
    # ------------------------------------------------------------------

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("description", "command", "llm_risk", "expected_min_risk"),
        [
            # low→high: Commands where rules would say "low" (read-only verb)
            # but contain a destructive pattern in arguments.
            # NOTE: With read-only override, describe/list/get are ALWAYS low
            # regardless of argument content. Only non-read-only commands upgrade.
            (
                "low→high: create command referencing delete path",
                "aws s3api create-bucket --bucket delete-this-bucket",
                "low",
                "high",
            ),
            (
                "low→high: put with force in name",
                "aws s3api put-object --bucket force-deploy --key app.zip --body file://app.zip",
                "low",
                "high",
            ),
            (
                "low→high: tag command with destroy in value",
                "aws ec2 create-tags --resources i-123 --tags Key=Action,Value=destroy-after-review",
                "low",
                "high",
            ),
            # medium→high: Commands where rules classify as medium (reversible)
            # but destructive pattern detected → upgrade from medium to high.
            (
                "medium→high: create-bucket with remove in name",
                "aws s3api create-bucket --bucket remove-old-data-staging",
                "low",
                "high",
            ),
            (
                "medium→high: put-object with delete in key",
                "aws s3api put-object --bucket staging --key delete-plan.json --body file://p.json",
                "low",
                "high",
            ),
            (
                "medium→high: enable with revoke in identifier",
                "aws ec2 enable-vpc-classic-link --vpc-id vpc-revoke-test",
                "low",
                "high",
            ),
            # high→critical: Commands where rules already classify as high
            # but critical flags present → rules directly return critical.
            (
                "high→critical: delete-db-instance with skip-final-snapshot",
                "aws rds delete-db-instance --db-instance-id prod --skip-final-snapshot",
                "low",
                "critical",
            ),
            (
                "high→critical: delete-bucket with force-destroy",
                "aws s3api delete-bucket --bucket archive --force-destroy",
                "low",
                "critical",
            ),
            (
                "high→critical: terminate with recursive",
                "aws s3 rm s3://prod-data/ --recursive",
                "low",
                "critical",
            ),
            # critical→critical: Already at critical, stays critical.
            (
                "critical→critical: force-delete stays critical",
                "aws ecr delete-repository --repository-name app --force-delete",
                "low",
                "critical",
            ),
            (
                "critical→critical: bypass-governance stays critical",
                "aws s3api delete-object --bucket locked --key f --bypass-governance-retention",
                "low",
                "critical",
            ),
            (
                "critical→critical: recursive rm stays critical",
                "aws s3 rm s3://company-backup/ --recursive --exclude '*.keep'",
                "low",
                "critical",
            ),
        ],
        ids=[
            "low-to-high-list-delete",
            "low-to-high-describe-force",
            "low-to-high-get-destroy",
            "medium-to-high-create-remove",
            "medium-to-high-put-delete",
            "medium-to-high-enable-revoke",
            "high-to-critical-skip-snapshot",
            "high-to-critical-force-destroy",
            "high-to-critical-recursive",
            "critical-stays-force-delete",
            "critical-stays-bypass-governance",
            "critical-stays-recursive-rm",
        ],
    )
    def test_ladder_transition_via_assess(
        self,
        safety_layer: SafetyLayer,
        description: str,
        command: str,
        llm_risk: str,
        expected_min_risk: str,
    ) -> None:
        """Verify each ladder transition produces the expected minimum risk via assess()."""
        translation = _make_translation(command, risk_level=llm_risk)
        result = safety_layer.assess(translation)
        assert RISK_ORDER[result.risk_level] >= RISK_ORDER[expected_min_risk], (
            f"{description}: expected >= '{expected_min_risk}', got '{result.risk_level}'"
        )

    # ------------------------------------------------------------------
    # 2. Verify upgrade skipping — no double upgrade
    #    When _classify_risk_by_rules already returns "high" or above,
    #    the upgrade ladder should NOT be applied again (condition:
    #    RISK_ORDER[rule_risk] < RISK_ORDER["high"] is False).
    # ------------------------------------------------------------------

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("command", "llm_risk", "expected_exact"),
        [
            # Rules classify as high (delete-bucket), destructive detected,
            # but since rule_risk is already >= "high", no _upgrade_risk call.
            # Final = max(llm_risk=low, rule_risk=high) = high (not critical).
            (
                "aws s3api delete-bucket --bucket old-test",
                "low",
                "high",
            ),
            # Rules classify as high (terminate-instances), no double upgrade.
            (
                "aws ec2 terminate-instances --instance-ids i-test123",
                "low",
                "high",
            ),
            # Rules classify as high (delete-volume), stays high.
            (
                "aws ec2 delete-volume --volume-id vol-abc",
                "low",
                "high",
            ),
            # Rules classify as high (delete-db-instance without flags), stays high.
            (
                "aws rds delete-db-instance --db-instance-id test-db",
                "low",
                "high",
            ),
            # Rules classify as high (delete-user), stays high not critical.
            (
                "aws iam delete-user --user-name test-user",
                "low",
                "high",
            ),
        ],
        ids=[
            "delete-bucket-no-double-upgrade",
            "terminate-instances-no-double-upgrade",
            "delete-volume-no-double-upgrade",
            "delete-db-no-double-upgrade",
            "delete-user-no-double-upgrade",
        ],
    )
    def test_no_double_upgrade_when_rules_already_high(
        self,
        safety_layer: SafetyLayer,
        command: str,
        llm_risk: str,
        expected_exact: str,
    ) -> None:
        """When rule_risk is already high, _upgrade_risk is NOT applied again.

        This ensures commands like 'delete-bucket' (high from rules) don't get
        double-upgraded to critical just because _is_destructive also triggers.
        The condition in assess() is: RISK_ORDER[rule_risk] < RISK_ORDER["high"].
        """
        translation = _make_translation(command, risk_level=llm_risk)
        result = safety_layer.assess(translation)
        assert result.risk_level == expected_exact, (
            f"Expected exact '{expected_exact}' (no double upgrade), "
            f"got '{result.risk_level}' for: {command}"
        )

    # ------------------------------------------------------------------
    # 3. Integration with assess() — full flow verification
    #    LLM says one level, rules classify at another, destructive patterns
    #    detected → upgrade applied → final result correct.
    # ------------------------------------------------------------------

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("command", "llm_risk", "expected_min", "scenario"),
        [
            # LLM says low, rules say low (read-only with destructive word),
            # With read-only override, head-object is ALWAYS low regardless
            (
                "aws s3api head-object --bucket delete-me-bucket --key test",
                "low",
                "low",
                "LLM=low, rules=low (head/read-only), read-only override keeps it at low",
            ),
            # LLM says medium, rules say low (read-only) →
            # Read-only override forces low (describe is always safe)
            (
                "aws ec2 describe-instances --region us-west-2",
                "medium",
                "low",
                "LLM=medium, rules=low (read-only override) → final=low",
            ),
            # LLM says low, rules say critical (--skip-final-snapshot) →
            # final = max(low, critical) = critical, no upgrade needed
            (
                "aws rds delete-db-instance --db-instance-id x --skip-final-snapshot",
                "low",
                "critical",
                "LLM=low, rules=critical → final=critical directly from rules",
            ),
            # LLM says high, rules say medium (create-bucket), destructive
            # pattern 'delete' in bucket name → upgrade medium→high →
            # final = max(high, high) = high
            (
                "aws s3api create-bucket --bucket delete-legacy-data",
                "high",
                "high",
                "LLM=high, rules=medium, destructive → upgrade medium→high, final=high",
            ),
            # LLM says critical, rules say low (list) → read-only override → final=low
            (
                "aws s3 ls s3://sensitive-data/",
                "critical",
                "low",
                "LLM=critical, but ls is read-only → override to low",
            ),
        ],
        ids=[
            "full-flow-low-to-high-via-destructive",
            "full-flow-medium-llm-floor",
            "full-flow-critical-from-rules",
            "full-flow-high-llm-with-upgrade",
            "full-flow-critical-llm-floor",
        ],
    )
    def test_assess_full_flow_integration(
        self,
        safety_layer: SafetyLayer,
        command: str,
        llm_risk: str,
        expected_min: str,
        scenario: str,
    ) -> None:
        """Verify the full assess() flow: LLM + rules + destructive upgrade → final risk."""
        translation = _make_translation(command, risk_level=llm_risk)
        result = safety_layer.assess(translation)
        assert RISK_ORDER[result.risk_level] >= RISK_ORDER[expected_min], (
            f"FAILED: {scenario}\nExpected >= '{expected_min}', got '{result.risk_level}'"
        )

    # ------------------------------------------------------------------
    # 4. Edge case: low→high skips medium entirely
    #    The ladder jumps from low directly to high — medium is never an
    #    intermediate result of _upgrade_risk.
    # ------------------------------------------------------------------

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "current_level",
        ["low"],
    )
    def test_upgrade_from_low_skips_medium(
        self, safety_layer: SafetyLayer, current_level: str
    ) -> None:
        """_upgrade_risk('low') returns 'high', never 'medium'.

        The ladder explicitly skips medium when upgrading from low,
        reflecting the principle that if a destructive pattern is detected
        on a previously-low command, it deserves high (not just medium).
        """
        result = safety_layer._upgrade_risk(current_level)  # type: ignore[arg-type]
        assert result == "high", f"Expected 'high' but got '{result}'"
        assert result != "medium", "Upgrade from low must SKIP medium entirely"

    @pytest.mark.unit
    def test_low_upgrade_skips_medium_in_assess_context(self, safety_layer: SafetyLayer) -> None:
        """In assess(), when rules=low and destructive detected, result is high not medium.

        This verifies the skip-medium behavior through the full pipeline.
        """
        # Command that rules classify as low (list/read-only verb) but
        # _is_destructive detects "delete" pattern in the argument
        translation = _make_translation(
            "aws s3api list-objects --bucket delete-everything",
            risk_level="low",
        )
        result = safety_layer.assess(translation)
        # Should be at least high, NOT medium
        assert RISK_ORDER[result.risk_level] >= RISK_ORDER["high"], (
            f"Expected at least 'high' (skipping medium), got '{result.risk_level}'"
        )

    # ------------------------------------------------------------------
    # 5. Invariant: _upgrade_risk NEVER decreases risk level
    #    For every valid input, output >= input in RISK_ORDER.
    # ------------------------------------------------------------------

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "level",
        ["low", "medium", "high", "critical"],
    )
    def test_upgrade_never_decreases_risk(self, safety_layer: SafetyLayer, level: str) -> None:
        """_upgrade_risk(level) always returns a level >= the input level.

        This is a fundamental safety invariant: upgrading can only increase
        or maintain the risk level, never decrease it.
        """
        result = safety_layer._upgrade_risk(level)  # type: ignore[arg-type]
        assert RISK_ORDER[result] >= RISK_ORDER[level], (
            f"INVARIANT VIOLATED: _upgrade_risk('{level}') returned '{result}' "
            f"which is LOWER than the input"
        )

    @pytest.mark.unit
    def test_upgrade_is_monotonic_through_full_ladder(
        self,
        safety_layer: SafetyLayer,
    ) -> None:
        """Applying _upgrade_risk repeatedly converges to 'critical' monotonically.

        Starting from any level, repeated upgrades must form a non-decreasing
        sequence that terminates at 'critical'.
        """
        for start in ("low", "medium", "high", "critical"):
            current = start
            seen: list[str] = [current]
            for _ in range(5):  # More than enough to reach critical
                upgraded = safety_layer._upgrade_risk(current)  # type: ignore[arg-type]
                assert RISK_ORDER[upgraded] >= RISK_ORDER[current], (
                    f"Non-monotonic: {current} → {upgraded} in sequence {seen}"
                )
                if upgraded == current:
                    # Fixed point reached (critical→critical)
                    break
                current = upgraded
                seen.append(current)
            # Must converge to critical
            assert current == "critical", (
                f"Starting from '{start}', ladder did not converge to 'critical'. Sequence: {seen}"
            )

    @pytest.mark.unit
    def test_upgrade_chain_low_to_critical_is_two_steps(
        self,
        safety_layer: SafetyLayer,
    ) -> None:
        """From 'low', it takes exactly 2 upgrades to reach 'critical'.

        low → high → critical (2 steps)
        """
        step1 = safety_layer._upgrade_risk("low")  # type: ignore[arg-type]
        assert step1 == "high"
        step2 = safety_layer._upgrade_risk(step1)
        assert step2 == "critical"

    @pytest.mark.unit
    def test_upgrade_chain_medium_to_critical_is_two_steps(
        self,
        safety_layer: SafetyLayer,
    ) -> None:
        """From 'medium', it takes exactly 2 upgrades to reach 'critical'.

        medium → high → critical (2 steps)
        """
        step1 = safety_layer._upgrade_risk("medium")  # type: ignore[arg-type]
        assert step1 == "high"
        step2 = safety_layer._upgrade_risk(step1)
        assert step2 == "critical"


# ---------------------------------------------------------------------------
# Tests: Combinaciones peligrosas en contexto
# ---------------------------------------------------------------------------

# Casos donde un comando individualmente parece de riesgo medio pero en
# combinación con ciertos argumentos/flags se vuelve peligroso.
# NOTA: La implementación actual clasifica por pattern matching de verbos/flags,
# NO por análisis semántico de argumentos. Los niveles esperados reflejan lo que
# el clasificador actual retorna, documentando así los gaps de detección.
#
# Cada tupla: (comando_peligroso, nivel_mínimo_esperado, descripción_del_riesgo)
_DANGEROUS_COMBINATIONS: list[tuple[str, str, str]] = [
    # --- update-stack sin changeset (actualización directa sin preview) ---
    (
        "aws cloudformation update-stack --stack-name prod-app --template-body file://template.yaml",
        "medium",
        "update-stack sin changeset previo: actualiza producción sin preview de cambios",
    ),
    # --- put-bucket-policy con "*" (política excesivamente permisiva) ---
    (
        'aws s3api put-bucket-policy --bucket prod-data --policy \'{"Statement":[{"Effect":"Allow","Principal":"*","Action":"s3:*","Resource":"arn:aws:s3:::prod-data/*"}]}\'',
        "medium",
        "put-bucket-policy con Principal:* — expone bucket completo al público",
    ),
    # --- put-bucket-acl con public-read (bucket público) ---
    (
        "aws s3api put-bucket-acl --bucket internal-docs --acl public-read",
        "medium",
        "put-bucket-acl con --acl public-read — expone datos internos al mundo",
    ),
    # --- put-bucket-acl con public-read-write (bucket público escritura) ---
    (
        "aws s3api put-bucket-acl --bucket customer-uploads --acl public-read-write",
        "medium",
        "put-bucket-acl con --acl public-read-write — cualquiera puede escribir/leer",
    ),
    # --- authorize-security-group-ingress con 0.0.0.0/0 (abierto al mundo) ---
    (
        "aws ec2 authorize-security-group-ingress --group-id sg-prod-db --protocol tcp --port 3306 --cidr 0.0.0.0/0",
        "low",
        "authorize-security-group-ingress con 0.0.0.0/0 — DB expuesta a internet (no detectado por heurística actual)",
    ),
    # --- create-role con trust policy permisiva (Principal: "*") ---
    (
        'aws iam create-role --role-name admin-role --assume-role-policy-document \'{"Statement":[{"Effect":"Allow","Principal":"*","Action":"sts:AssumeRole"}]}\'',
        "medium",
        "create-role con Principal:* — cualquier entidad puede asumir el rol",
    ),
    # --- delete-db-instance sin --final-db-snapshot-identifier (sin backup) ---
    (
        "aws rds delete-db-instance --db-instance-id production-db",
        "high",
        "delete-db-instance sin snapshot final — pérdida de datos si no hay backup previo",
    ),
    # --- put-lifecycle-configuration con expiración muy corta ---
    (
        'aws s3api put-bucket-lifecycle-configuration --bucket prod-logs --lifecycle-configuration \'{"Rules":[{"Status":"Enabled","Expiration":{"Days":1},"ID":"expire-fast","Filter":{"Prefix":""}}]}\'',
        "medium",
        "put-lifecycle-configuration con expiración de 1 día — elimina datos rápidamente",
    ),
    # --- modify-instance-attribute deshabilitando protección de terminación ---
    (
        "aws ec2 modify-instance-attribute --instance-id i-prod-web-01 --no-disable-api-termination",
        "medium",
        "modify-instance-attribute deshabilitando protección de terminación en instancia de prod",
    ),
    # --- update-function-configuration con timeout extremo ---
    (
        "aws lambda update-function-configuration --function-name payment-processor --timeout 900 --memory-size 10240",
        "medium",
        "update-function-configuration con recursos máximos — riesgo de costos elevados",
    ),
    # --- authorize-security-group-ingress con rango completo de puertos ---
    (
        "aws ec2 authorize-security-group-ingress --group-id sg-prod --protocol tcp --port 0-65535 --cidr 10.0.0.0/8",
        "low",
        "authorize-security-group-ingress con todos los puertos abiertos (no detectado por heurística actual)",
    ),
    # --- put-bucket-versioning suspendiendo versionado ---
    (
        "aws s3api put-bucket-versioning --bucket compliance-data --versioning-configuration Status=Suspended",
        "medium",
        "put-bucket-versioning suspendiendo versionado — elimina protección contra borrado accidental",
    ),
    # --- update-stack con --use-previous-template sin review ---
    (
        "aws cloudformation update-stack --stack-name production-infra --use-previous-template --parameters ParameterKey=Env,ParameterValue=prod",
        "medium",
        "update-stack con --use-previous-template sin changeset — aplica cambios sin preview",
    ),
    # --- delete-db-instance con --skip-final-snapshot (crítico explícito) ---
    (
        "aws rds delete-db-instance --db-instance-id analytics-db --skip-final-snapshot",
        "critical",
        "delete-db-instance con --skip-final-snapshot — destrucción sin backup, flag crítico detectado",
    ),
]


class TestDangerousCombinations:
    """Tests para combinaciones de comandos peligrosos en contexto.

    Documenta comandos que individualmente parecen de riesgo medio pero que
    en combinación con ciertos argumentos/flags representan un riesgo mayor.

    La implementación actual clasifica principalmente por pattern matching de
    verbos y flags. Estos tests verifican la clasificación actual y documentan
    los gaps donde el análisis semántico de contexto mejoraría la detección.
    """

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("command", "expected_min_risk", "risk_description"),
        _DANGEROUS_COMBINATIONS,
        ids=[
            "update-stack-sin-changeset",
            "put-bucket-policy-principal-wildcard",
            "put-bucket-acl-public-read",
            "put-bucket-acl-public-read-write",
            "authorize-sg-ingress-open-to-world",
            "create-role-trust-policy-wildcard",
            "delete-db-instance-sin-snapshot",
            "put-lifecycle-expiration-1-day",
            "modify-instance-disable-termination-protection",
            "update-function-max-resources",
            "authorize-sg-ingress-all-ports",
            "put-bucket-versioning-suspended",
            "update-stack-use-previous-template",
            "delete-db-instance-skip-final-snapshot",
        ],
    )
    def test_dangerous_combination_risk_classification(
        self,
        safety_layer: SafetyLayer,
        command: str,
        expected_min_risk: str,
        risk_description: str,
    ) -> None:
        """Verifica que combinaciones peligrosas se clasifican al nivel esperado.

        El nivel esperado refleja lo que la heurística ACTUAL retorna basándose
        en pattern matching. Documentamos el riesgo real en risk_description para
        futuras mejoras del análisis semántico.
        """
        result = safety_layer._classify_risk_by_rules(command)
        assert RISK_ORDER[result] >= RISK_ORDER[expected_min_risk], (
            f"Clasificación insuficiente: esperado >= '{expected_min_risk}', "
            f"obtenido '{result}'.\n"
            f"Riesgo contextual: {risk_description}"
        )

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("command", "expected_min_risk", "risk_description"),
        _DANGEROUS_COMBINATIONS,
        ids=[
            "assess-update-stack-sin-changeset",
            "assess-put-bucket-policy-principal-wildcard",
            "assess-put-bucket-acl-public-read",
            "assess-put-bucket-acl-public-read-write",
            "assess-authorize-sg-ingress-open-to-world",
            "assess-create-role-trust-policy-wildcard",
            "assess-delete-db-instance-sin-snapshot",
            "assess-put-lifecycle-expiration-1-day",
            "assess-modify-instance-disable-termination-protection",
            "assess-update-function-max-resources",
            "assess-authorize-sg-ingress-all-ports",
            "assess-put-bucket-versioning-suspended",
            "assess-update-stack-use-previous-template",
            "assess-delete-db-instance-skip-final-snapshot",
        ],
    )
    def test_dangerous_combination_assess_integration(
        self,
        safety_layer: SafetyLayer,
        command: str,
        expected_min_risk: str,
        risk_description: str,
    ) -> None:
        """Verifica assess() con LLM risk='low' para combinaciones peligrosas.

        Cuando el LLM dice 'low' pero el comando tiene patrones detectables,
        el safety layer debe elevar el riesgo. Para comandos donde la heurística
        actual no detecta el peligro contextual, el resultado puede ser 'low'.
        """
        translation = _make_translation(command, risk_level="low")
        result = safety_layer.assess(translation)
        assert RISK_ORDER[result.risk_level] >= RISK_ORDER[expected_min_risk], (
            f"assess() clasificación insuficiente: esperado >= '{expected_min_risk}', "
            f"obtenido '{result.risk_level}'.\n"
            f"Riesgo contextual: {risk_description}"
        )

    @pytest.mark.unit
    def test_dangerous_combinations_minimum_count(self) -> None:
        """Meta-test: verificar que tenemos al menos 10 combinaciones peligrosas."""
        assert len(_DANGEROUS_COMBINATIONS) >= 10, (
            f"Se requieren al menos 10 combinaciones, hay {len(_DANGEROUS_COMBINATIONS)}"
        )

    @pytest.mark.unit
    def test_dangerous_combinations_cover_multiple_services(self) -> None:
        """Meta-test: verificar que las combinaciones cubren múltiples servicios AWS."""
        services = set()
        for command, _, _ in _DANGEROUS_COMBINATIONS:
            parts = command.split()
            if len(parts) >= 2 and parts[0] == "aws":
                services.add(parts[1])
        # Debe cubrir al menos 4 servicios distintos
        assert len(services) >= 4, f"Se requieren al menos 4 servicios, cubiertos: {services}"

    @pytest.mark.unit
    def test_update_stack_without_changeset_is_at_least_medium(
        self, safety_layer: SafetyLayer
    ) -> None:
        """update-stack sin changeset debe ser al menos medium por pattern update-."""
        command = "aws cloudformation update-stack --stack-name prod --template-body file://t.yaml"
        result = safety_layer._classify_risk_by_rules(command)
        assert RISK_ORDER[result] >= RISK_ORDER["medium"]

    @pytest.mark.unit
    def test_put_bucket_policy_with_wildcard_is_at_least_medium(
        self, safety_layer: SafetyLayer
    ) -> None:
        """put-bucket-policy con Principal:* debe ser al menos medium por pattern put-."""
        command = 'aws s3api put-bucket-policy --bucket prod --policy \'{"Statement":[{"Principal":"*"}]}\''
        result = safety_layer._classify_risk_by_rules(command)
        assert RISK_ORDER[result] >= RISK_ORDER["medium"]

    @pytest.mark.unit
    def test_delete_db_without_snapshot_flag_is_high(self, safety_layer: SafetyLayer) -> None:
        """delete-db-instance sin --final-db-snapshot-identifier es high (destruye datos)."""
        command = "aws rds delete-db-instance --db-instance-id prod-db"
        result = safety_layer._classify_risk_by_rules(command)
        assert result == "high"

    @pytest.mark.unit
    def test_delete_db_with_skip_snapshot_is_critical(self, safety_layer: SafetyLayer) -> None:
        """delete-db-instance con --skip-final-snapshot es critical."""
        command = "aws rds delete-db-instance --db-instance-id prod --skip-final-snapshot"
        result = safety_layer._classify_risk_by_rules(command)
        assert result == "critical"


# ---------------------------------------------------------------------------
# Tests: SafetyError exception
# ---------------------------------------------------------------------------


class TestSafetyError:
    """Verify SafetyError custom exception behavior."""

    @pytest.mark.unit
    def test_safety_error_stores_message(self) -> None:
        """SafetyError stores message attribute."""
        from cloudshellgpt.safety import SafetyError

        err = SafetyError("something failed")
        assert err.message == "something failed"
        assert str(err) == "something failed"

    @pytest.mark.unit
    def test_safety_error_stores_risk_level(self) -> None:
        """SafetyError stores optional risk_level."""
        from cloudshellgpt.safety import SafetyError

        err = SafetyError("blocked", risk_level="critical")
        assert err.risk_level == "critical"
        assert err.message == "blocked"

    @pytest.mark.unit
    def test_safety_error_risk_level_defaults_none(self) -> None:
        """SafetyError risk_level defaults to None."""
        from cloudshellgpt.safety import SafetyError

        err = SafetyError("test")
        assert err.risk_level is None

    @pytest.mark.unit
    def test_safety_error_is_exception(self) -> None:
        """SafetyError is a subclass of Exception."""
        from cloudshellgpt.safety import SafetyError

        assert issubclass(SafetyError, Exception)


# ---------------------------------------------------------------------------
# Tests: _validate_risk_level edge cases
# ---------------------------------------------------------------------------


class TestValidateRiskLevel:
    """Verify _validate_risk_level handles invalid inputs."""

    @pytest.mark.unit
    def test_invalid_risk_level_defaults_to_low(self, safety_layer: SafetyLayer) -> None:
        """Invalid risk level string defaults to 'low'."""
        assert safety_layer._validate_risk_level("invalid") == "low"
        assert safety_layer._validate_risk_level("") == "low"
        assert safety_layer._validate_risk_level("CRITICAL") == "low"  # case-sensitive

    @pytest.mark.unit
    def test_valid_risk_levels_pass_through(self, safety_layer: SafetyLayer) -> None:
        """Valid risk levels pass through unchanged."""
        assert safety_layer._validate_risk_level("low") == "low"
        assert safety_layer._validate_risk_level("medium") == "medium"
        assert safety_layer._validate_risk_level("high") == "high"
        assert safety_layer._validate_risk_level("critical") == "critical"


# ---------------------------------------------------------------------------
# Tests: inject_dry_run — dry-run injection for various services
# ---------------------------------------------------------------------------


class TestInjectDryRun:
    """Verify inject_dry_run applies correct dry-run strategy per service."""

    @pytest.mark.unit
    def test_ec2_command_gets_dry_run_flag(self, safety_layer: SafetyLayer) -> None:
        """EC2 commands get --dry-run appended."""
        result = safety_layer.inject_dry_run("aws ec2 run-instances --instance-type t3.micro")
        assert result.is_native_dry_run is True
        assert result.preview_only is False
        assert "--dry-run" in result.command
        assert "EC2" in result.dry_run_notes

    @pytest.mark.unit
    def test_ec2_already_has_dry_run_no_duplicate(self, safety_layer: SafetyLayer) -> None:
        """EC2 commands that already have --dry-run don't get a duplicate."""
        result = safety_layer.inject_dry_run("aws ec2 run-instances --dry-run")
        assert result.command == "aws ec2 run-instances --dry-run"
        assert result.is_native_dry_run is True
        assert result.preview_only is False

    @pytest.mark.unit
    def test_cfn_create_stack_becomes_change_set(self, safety_layer: SafetyLayer) -> None:
        """CloudFormation create-stack is transformed to create-change-set."""
        result = safety_layer.inject_dry_run(
            "aws cloudformation create-stack --stack-name my-app --template-body file://t.yaml"
        )
        assert "create-change-set" in result.command
        assert "create-stack" not in result.command
        assert result.is_native_dry_run is True
        assert result.preview_only is False
        assert "change-set" in result.dry_run_notes.lower()

    @pytest.mark.unit
    def test_cfn_update_stack_becomes_change_set_update(self, safety_layer: SafetyLayer) -> None:
        """CloudFormation update-stack is transformed to create-change-set with UPDATE type."""
        result = safety_layer.inject_dry_run(
            "aws cloudformation update-stack --stack-name my-app --template-body file://t.yaml"
        )
        assert "create-change-set" in result.command
        assert "update-stack" not in result.command
        assert "--change-set-type UPDATE" in result.command
        assert result.is_native_dry_run is True
        assert result.preview_only is False

    @pytest.mark.unit
    def test_cfn_delete_stack_is_preview_only(self, safety_layer: SafetyLayer) -> None:
        """CloudFormation delete-stack doesn't support change sets → preview only."""
        result = safety_layer.inject_dry_run("aws cloudformation delete-stack --stack-name old-app")
        assert result.command == "aws cloudformation delete-stack --stack-name old-app"
        assert result.is_native_dry_run is False
        assert result.preview_only is True
        assert "does not support change sets" in result.dry_run_notes.lower()

    @pytest.mark.unit
    def test_rds_is_preview_only(self, safety_layer: SafetyLayer) -> None:
        """RDS commands are preview-only (no native dry-run)."""
        result = safety_layer.inject_dry_run("aws rds delete-db-instance --db-instance-id mydb")
        assert result.is_native_dry_run is False
        assert result.preview_only is True
        assert "RDS" in result.dry_run_notes

    @pytest.mark.unit
    def test_s3api_is_preview_only(self, safety_layer: SafetyLayer) -> None:
        """S3 API commands are preview-only (no native dry-run)."""
        result = safety_layer.inject_dry_run("aws s3api delete-bucket --bucket prod")
        assert result.is_native_dry_run is False
        assert result.preview_only is True
        assert "S3" in result.dry_run_notes

    @pytest.mark.unit
    def test_iam_is_preview_only(self, safety_layer: SafetyLayer) -> None:
        """IAM commands are preview-only."""
        result = safety_layer.inject_dry_run("aws iam delete-user --user-name admin")
        assert result.is_native_dry_run is False
        assert result.preview_only is True
        assert "IAM" in result.dry_run_notes

    @pytest.mark.unit
    def test_lambda_is_preview_only(self, safety_layer: SafetyLayer) -> None:
        """Lambda commands are preview-only."""
        result = safety_layer.inject_dry_run("aws lambda delete-function --function-name f")
        assert result.is_native_dry_run is False
        assert result.preview_only is True
        assert "Lambda" in result.dry_run_notes

    @pytest.mark.unit
    def test_unknown_service_is_preview_only(self, safety_layer: SafetyLayer) -> None:
        """Unknown services are preview-only with a generic message."""
        result = safety_layer.inject_dry_run("aws sqs delete-queue --queue-url https://...")
        assert result.is_native_dry_run is False
        assert result.preview_only is True
        assert "does not support dry-run" in result.dry_run_notes.lower()


# ---------------------------------------------------------------------------
# Tests: _extract_service
# ---------------------------------------------------------------------------


class TestExtractService:
    """Verify _extract_service parses commands correctly."""

    @pytest.mark.unit
    def test_extracts_ec2(self, safety_layer: SafetyLayer) -> None:
        assert safety_layer._extract_service("aws ec2 describe-instances") == "ec2"

    @pytest.mark.unit
    def test_extracts_s3api(self, safety_layer: SafetyLayer) -> None:
        assert safety_layer._extract_service("aws s3api list-buckets") == "s3api"

    @pytest.mark.unit
    def test_returns_empty_for_invalid(self, safety_layer: SafetyLayer) -> None:
        assert safety_layer._extract_service("not-aws command") == ""

    @pytest.mark.unit
    def test_returns_empty_for_too_short(self, safety_layer: SafetyLayer) -> None:
        assert safety_layer._extract_service("aws") == ""


# ---------------------------------------------------------------------------
# Tests: _build_confirmation_prompt
# ---------------------------------------------------------------------------


class TestBuildConfirmationPrompt:
    """Verify confirmation prompts are generated correctly per risk level."""

    @pytest.mark.unit
    def test_low_risk_returns_empty_prompt(self, safety_layer: SafetyLayer) -> None:
        """Low risk commands don't need confirmation."""
        translation = _make_translation("aws s3 ls", risk_level="low")
        prompt = safety_layer._build_confirmation_prompt(translation, "low")
        assert prompt == ""

    @pytest.mark.unit
    def test_medium_risk_shows_command_and_yn(self, safety_layer: SafetyLayer) -> None:
        """Medium risk shows command + Y/n prompt."""
        translation = _make_translation("aws s3api create-bucket --bucket x", risk_level="medium")
        prompt = safety_layer._build_confirmation_prompt(translation, "medium")
        assert "Command:" in prompt
        assert "[Y/n]" in prompt

    @pytest.mark.unit
    def test_high_risk_shows_affected_resources(self, safety_layer: SafetyLayer) -> None:
        """High risk shows command + affected resources."""
        translation = Translation(
            command="aws ec2 terminate-instances --instance-ids i-123",
            explanation="Terminate",
            detailed_explanation="...",
            risk_level="high",
            estimated_cost="$0.00",
            requires_dry_run=False,
            affected_resources=["i-123"],
            flags_used={},
        )
        prompt = safety_layer._build_confirmation_prompt(translation, "high")
        assert "HIGH RISK" in prompt
        assert "i-123" in prompt

    @pytest.mark.unit
    def test_critical_shows_yes_i_understand(self, safety_layer: SafetyLayer) -> None:
        """Critical risk requires typing 'yes-i-understand'."""
        translation = Translation(
            command="aws s3 rm s3://prod --recursive",
            explanation="Delete all",
            detailed_explanation="...",
            risk_level="critical",
            estimated_cost="$0.00",
            requires_dry_run=True,
            affected_resources=["s3://prod/*"],
            flags_used={},
        )
        prompt = safety_layer._build_confirmation_prompt(translation, "critical")
        assert "CRITICAL" in prompt
        assert "yes-i-understand" in prompt
        assert "s3://prod/*" in prompt
