"""Unit tests for SafetyLayer — LLM independence and upgrade risk ladder."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from cloudshellgpt.bedrock_translator import Translation
from cloudshellgpt.cost import CostEstimate
from cloudshellgpt.safety import RISK_ORDER, SafetyLayer

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
        """Even for a read-only command, risk >= llm_risk."""
        translation = _make_translation("aws s3api list-buckets", risk_level=llm_risk)
        result = safety_layer.assess(translation)
        assert RISK_ORDER[result.risk_level] >= RISK_ORDER[llm_risk]

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
        """If LLM says high but command is read-only, result is still high.

        We never downgrade below LLM.
        """
        translation = _make_translation("aws s3api list-buckets", risk_level="high")
        result = safety_layer.assess(translation)
        assert result.risk_level == "high"


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
        """LLM says high, rules say low → final is high (LLM floor)."""
        translation = _make_translation("aws s3 ls", risk_level="high")
        result = safety_layer.assess(translation)
        assert result.risk_level == "high"

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
