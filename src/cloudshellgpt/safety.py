"""Safety layer — risk assessment, cost preview, confirmation flow, and dry-run support."""

from __future__ import annotations

from typing import Literal

import boto3
from pydantic import BaseModel, Field

from cloudshellgpt.bedrock_translator import Translation
from cloudshellgpt.cost import CostEstimate

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


class DryRunResult(BaseModel):
    """Result of dry-run injection for a command.

    Encapsulates the (possibly modified) command along with metadata
    indicating whether native dry-run is supported or if the command
    should only be shown as a preview without execution.

    Attributes:
        command: The (possibly modified) AWS CLI command.
        is_native_dry_run: True if the service supports native dry-run
            (EC2 via --dry-run, CloudFormation via change sets).
        preview_only: True if the command cannot be dry-run natively and
            should only be displayed without executing.
        dry_run_notes: Human-readable explanation of what dry-run mode
            does for this particular service.
    """

    command: str = Field(description="The (possibly modified) AWS CLI command")
    is_native_dry_run: bool = Field(
        description="True if the service supports native dry-run mechanism"
    )
    preview_only: bool = Field(description="True if command should be shown without executing")
    dry_run_notes: str = Field(description="Explanation of what dry-run mode does for this service")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RISK_ORDER: dict[str, int] = {
    "low": 0,
    "medium": 1,
    "high": 2,
    "critical": 3,
}

READ_ONLY_PATTERNS: list[str] = [
    "list",
    "describe",
    "get",
    "head",
    "wait",
    "show",
    "ls",
]

# ---------------------------------------------------------------------------
# Reversible operations — pairs where the operation has a direct inverse.
# Key = prefix of the "forward" operation, Value = prefix of its inverse.
# If a command matches a reversible prefix AND does NOT destroy data, it's medium.
# ---------------------------------------------------------------------------

REVERSIBLE_OPERATIONS: dict[str, str] = {
    "create-": "delete-",
    "attach-": "detach-",
    "enable-": "disable-",
    "register-": "deregister-",
    "add-": "remove-",
    "tag-resource": "untag-resource",
    "put-": "delete-",
    "associate-": "disassociate-",
    "start-": "stop-",
    "update-": "revert/re-apply",
}

# ---------------------------------------------------------------------------
# Data-destroying patterns — operations that eliminate data or access and
# require manual recreation. These always classify as high risk.
# ---------------------------------------------------------------------------

DATA_DESTROYING_PATTERNS: list[str] = [
    "delete-bucket",
    "delete-object",
    "terminate-instances",
    "delete-table",
    "delete-db-instance",
    "delete-db-cluster",
    "remove-permission",
    "revoke-security-group",
    "delete-volume",
    "delete-snapshot",
    "empty-bucket",
    "purge-queue",
    "delete-stack",
    "delete-user",
    "delete-role",
    "delete-policy",
    "delete-function",
    "delete-queue",
    "delete-topic",
    "delete-distribution",
    "release-address",
]

# ---------------------------------------------------------------------------
# Mutation verbs — verbs that suggest state-changing operations.
# If a command contains one of these but isn't in any known list, it should
# be upgraded to medium (never left at low when there's doubt).
# ---------------------------------------------------------------------------

MUTATION_VERBS: list[str] = [
    "create",
    "delete",
    "update",
    "put",
    "remove",
    "modify",
    "replace",
    "set",
    "reset",
    "import",
    "export",
    "invoke",
    "execute",
    "run",
    "send",
    "publish",
    "cancel",
    "stop",
    "start",
    "reboot",
    "restore",
]

# Legacy medium/high patterns kept for backward compatibility reference.
# The new heuristic uses REVERSIBLE_OPERATIONS and DATA_DESTROYING_PATTERNS instead.

MEDIUM_PATTERNS: list[str] = [
    "create-bucket",
    "tag-resource",
    "put-metric-alarm",
    "enable-",
    "create-snapshot",
    "put-",
    "add-",
    "attach-",
    "register-",
    "create-",
    "update-",
]

HIGH_PATTERNS: list[str] = [
    "delete-bucket",
    "terminate-instances",
    "revoke-security-group-ingress",
    "detach-volume",
    "remove-",
    "deregister-",
    "delete-",
    "terminate-",
    "revoke-",
    "detach-",
    "disable-",
    "release-",
]

CRITICAL_PATTERNS: list[str] = [
    "--force-delete",
    "--skip-final-snapshot",
    "--no-preserve-root",
    "--bypass-governance-retention",
    "--delete-all-versions",
    "--force-destroy",
    "--permanently-delete",
    "--no-undo",
    "empty-bucket",
]

# Destructive verbs that become critical when combined with --recursive
_RECURSIVE_DESTRUCTIVE_VERBS: list[str] = [
    "delete",
    "rm",
    "remove",
]

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

# Services that support native --dry-run flag (EC2 is the only one with broad support)
_NATIVE_DRY_RUN_SERVICES: frozenset[str] = frozenset({"ec2"})

# CloudFormation commands that can be transformed to change sets
_CFN_CREATE_PATTERN: str = "create-stack"
_CFN_UPDATE_PATTERN: str = "update-stack"


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

    def __init__(self, region: str = "us-east-1", max_cost_alert: int = 100) -> None:
        """Initialize the safety layer.

        Args:
            region: AWS region for Cost Explorer API calls.
            max_cost_alert: USD threshold above which a cost warning is added.
        """
        self.ce_client = boto3.client("ce", region_name=region)
        self.region = region
        self.max_cost_alert = max_cost_alert

    def assess(
        self,
        translation: Translation,
        cost_estimate: CostEstimate | None = None,
    ) -> SafetyCheck:
        """Run a full safety assessment on a translated command.

        Combines rule-based classification with LLM assessment, applying
        the upgrade ladder when destructive patterns are detected.

        When a CostEstimate is provided, integrates cost data into the
        safety check: propagates warnings, checks against max_cost_alert,
        and populates cost_breakdown from the estimate.

        **Independence guarantee:** The rule-based classifier works
        independently of the LLM's risk assessment. The final risk is
        ALWAYS >= the LLM's suggested risk (never downgrade). When the
        LLM says "low" but the command contains destructive patterns
        (delete, terminate, --force, etc.), the rule-based system
        overrides upward via the _upgrade_risk ladder.

        Algorithm:
            1. Get llm_risk from translation.risk_level
            2. Get rule_risk from _classify_risk_by_rules (independent)
            3. If the command has destructive patterns AND rule_risk is
               still below "high", apply _upgrade_risk to escalate
            4. Final risk = max(llm_risk, upgraded_rule_risk)
               → NEVER below llm_risk

        Args:
            translation: The Bedrock-generated translation to assess.
            cost_estimate: Optional CostEstimate from CostEstimator. When
                provided, cost data is integrated into the SafetyCheck.

        Returns:
            SafetyCheck with all risk, cost, and confirmation information.

        Raises:
            SafetyError: If the assessment cannot be completed.
        """
        # --- Independent assessments ---
        # LLM assessment (from Bedrock translation)
        llm_risk = self._validate_risk_level(translation.risk_level)

        # Rule-based assessment (independent of LLM, pattern-matching only)
        rule_risk = self._classify_risk_by_rules(translation.command)

        # --- Read-only override ---
        # If the command is read-only (list, describe, get, head, wait, show, ls),
        # force low regardless of LLM assessment or rule classification.
        # A read-only command can NEVER be destructive.
        if self._is_read_only(translation.command.lower()):
            risk_level: RiskLevel = "low"
        else:
            # --- Destructive pattern upgrade ---
            # If the command contains destructive patterns (broader than what
            # _classify_risk_by_rules may catch) and rule_risk hasn't already
            # escalated to "high" or above, apply the upgrade ladder.
            if (
                self._is_destructive(translation.command)
                and RISK_ORDER[rule_risk] < RISK_ORDER["high"]
            ):
                rule_risk = self._upgrade_risk(rule_risk)

            # Final risk = max of both assessments.
            # Invariant: result >= llm_risk (never downgrade below LLM suggestion)
            risk_level = self._max_risk(llm_risk, rule_risk)

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

        # --- Integrate CostEstimate when provided ---
        warnings: list[str] = list(translation.affected_resources)
        estimated_cost = translation.estimated_cost

        if cost_estimate is not None:
            # Propagate CostEstimate warnings into SafetyCheck warnings
            warnings.extend(cost_estimate.warnings)

            if cost_estimate.status == "unknown":
                warnings.append("Cost estimation unavailable — proceed with caution")
            elif cost_estimate.estimated_monthly_cost > self.max_cost_alert:
                warnings.append(
                    f"Estimated cost ${cost_estimate.estimated_monthly_cost:.2f}/month "
                    f"exceeds max_cost_alert threshold (${self.max_cost_alert})"
                )

            # Use CostEstimate breakdown (convert float values to strings)
            cost_breakdown = {k: f"${v:.2f}" for k, v in cost_estimate.cost_breakdown.items()}

            # Update estimated_cost with formatted value from CostEstimate
            if cost_estimate.status == "estimated" and cost_estimate.estimated_monthly_cost > 0:
                estimated_cost = f"${cost_estimate.estimated_monthly_cost:.2f}/month"

        return SafetyCheck(
            risk_level=risk_level,
            requires_confirmation=requires_confirmation,
            requires_dry_run=requires_dry_run,
            estimated_cost=estimated_cost,
            confirmation_prompt=confirmation_prompt,
            warnings=warnings,
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

    def _classify_risk_by_rules(self, command: str) -> RiskLevel:
        """Classify risk independently using pattern matching rules.

        Applies the heuristic in strict priority order:
        1. Critical: force/recursive/skip-safety flags
        2. High: operations that destroy data or access
        3. Medium: operations with a direct inverse that don't destroy data
        4. Ambiguity resolution: if both reversible AND destructive → high (upgrade)
        5. Low: read-only operations
        6. Default: if mutation verb detected but no known pattern → medium (doubt → upgrade)

        Works INDEPENDENTLY of the LLM's assessment.

        Args:
            command: The AWS CLI command string to classify.

        Returns:
            Rule-based risk level classification.
        """
        cmd_lower = command.lower()

        # 1. Critical: force/recursive/skip-safety flags (highest priority)
        if self._is_critical(cmd_lower):
            return "critical"

        # 2. Check data destruction and reversibility
        destroys = self._destroys_data(cmd_lower)
        has_inverse = self._has_direct_inverse(cmd_lower)

        # 3. Ambiguity resolution: if BOTH reversible AND destructive → upgrade to high
        # (doubt → always upgrade)
        if destroys and has_inverse:
            return "high"

        # 4. If destroys data → high
        if destroys:
            return "high"

        # 5. Legacy high patterns (backward compat for patterns not in DATA_DESTROYING)
        if self._is_high(cmd_lower):
            return "high"

        # 6. If has direct inverse and doesn't destroy data → medium
        if has_inverse:
            return "medium"

        # 7. Legacy medium patterns (backward compat)
        if self._is_medium(cmd_lower):
            return "medium"

        # 8. Read-only → low
        if self._is_read_only(cmd_lower):
            return "low"

        # 9. Doubt → upgrade: if the command contains mutation verbs but didn't
        # match any known pattern, classify as medium (never leave at low if in doubt)
        if self._has_mutation_verb(cmd_lower):
            return "medium"

        # 10. Truly read-only or unrecognized → low
        return "low"

    def _is_critical(self, cmd_lower: str) -> bool:
        """Check if the command matches critical-level patterns.

        Critical means: recursive/batch delete, force operations, or
        flags that skip safety nets.

        Args:
            cmd_lower: Lowercased command string.

        Returns:
            True if the command matches critical patterns.
        """
        # Check explicit critical patterns (force flags, skip-safety-net)
        for pattern in CRITICAL_PATTERNS:
            if pattern in cmd_lower:
                return True

        # Check --recursive combined with destructive verbs
        if "--recursive" in cmd_lower:
            for verb in _RECURSIVE_DESTRUCTIVE_VERBS:
                if verb in cmd_lower:
                    return True

        return False

    def _is_high(self, cmd_lower: str) -> bool:
        """Check if the command matches high-level patterns.

        High means: delete/terminate/revoke on single resources that
        eliminate data or access and require manual recreation.

        Args:
            cmd_lower: Lowercased command string.

        Returns:
            True if the command matches high-risk patterns.
        """
        return any(pattern in cmd_lower for pattern in HIGH_PATTERNS)

    def _is_medium(self, cmd_lower: str) -> bool:
        """Check if the command matches medium-level patterns.

        Medium means: create/update operations with easy rollback
        (operation has a direct inverse and doesn't destroy data).

        Args:
            cmd_lower: Lowercased command string.

        Returns:
            True if the command matches medium-risk patterns.
        """
        return any(pattern in cmd_lower for pattern in MEDIUM_PATTERNS)

    def _is_read_only(self, cmd_lower: str) -> bool:
        """Check if the command matches read-only (low) patterns.

        Read-only operations: list, describe, get, head, wait, show, ls.

        Args:
            cmd_lower: Lowercased command string.

        Returns:
            True if the command matches read-only patterns.
        """
        return any(pattern in cmd_lower for pattern in READ_ONLY_PATTERNS)

    def _has_direct_inverse(self, cmd_lower: str) -> bool:
        """Check if the command corresponds to an operation with a direct inverse.

        Operations with a direct inverse are easily reversible (e.g., create → delete,
        attach → detach, enable → disable). These are classified as medium risk when
        they don't also destroy data.

        Args:
            cmd_lower: Lowercased command string.

        Returns:
            True if the command matches a reversible operation prefix.
        """
        return any(prefix in cmd_lower for prefix in REVERSIBLE_OPERATIONS)

    def _destroys_data(self, cmd_lower: str) -> bool:
        """Check if the command destroys data or access.

        Operations that eliminate data or access require manual recreation and
        are always classified as high risk. This includes deleting storage,
        terminating instances, revoking security group rules, etc.

        Args:
            cmd_lower: Lowercased command string.

        Returns:
            True if the command matches a data-destroying pattern.
        """
        return any(pattern in cmd_lower for pattern in DATA_DESTROYING_PATTERNS)

    def _has_mutation_verb(self, cmd_lower: str) -> bool:
        """Check if the command contains verbs that suggest state mutation.

        Used as a fallback when no specific pattern matches: if a command has
        a mutation verb, it should NOT be classified as low (doubt → upgrade).

        Args:
            cmd_lower: Lowercased command string.

        Returns:
            True if the command contains any mutation verb.
        """
        return any(verb in cmd_lower for verb in MUTATION_VERBS)

    def _max_risk(self, *levels: RiskLevel) -> RiskLevel:
        """Return the highest risk level from the given levels.

        Uses RISK_ORDER to compare levels numerically.

        Args:
            *levels: One or more risk levels to compare.

        Returns:
            The highest risk level among the inputs.
        """
        return max(levels, key=lambda lvl: RISK_ORDER.get(lvl, 0))

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

    # ------------------------------------------------------------------
    # Dry-run injection
    # ------------------------------------------------------------------

    def inject_dry_run(self, command: str) -> DryRunResult:
        """Inject the appropriate dry-run mechanism for the given command.

        Determines the AWS service from the command and applies the correct
        dry-run strategy:
        - EC2: Appends ``--dry-run`` flag (native support).
        - CloudFormation: Transforms ``create-stack`` to ``create-change-set``
          and ``update-stack`` to ``create-change-set --change-set-type UPDATE``.
        - RDS, S3API, IAM, Lambda: No native dry-run — marks as preview_only.
        - Unknown/unsupported services: Also marked as preview_only.

        Args:
            command: The AWS CLI command string to inject dry-run into.

        Returns:
            DryRunResult with the modified command and metadata.
        """
        service = self._extract_service(command)

        if service == "ec2":
            return self._inject_ec2_dry_run(command)

        if service == "cloudformation":
            return self._inject_cfn_dry_run(command)

        # Services in DRY_RUN_SERVICES but without native dry-run
        # (rds, s3api, iam, lambda) → preview only
        if service in DRY_RUN_SERVICES:
            notes = self._get_preview_notes(service)
            return DryRunResult(
                command=command,
                is_native_dry_run=False,
                preview_only=True,
                dry_run_notes=notes,
            )

        # Service not in DRY_RUN_SERVICES → preview only
        return DryRunResult(
            command=command,
            is_native_dry_run=False,
            preview_only=True,
            dry_run_notes=(
                f"Service '{service}' does not support dry-run. "
                "Command shown for review only — will NOT be executed."
            ),
        )

    def _extract_service(self, command: str) -> str:
        """Extract the AWS service name from a command string.

        Expects commands in the format ``aws <service> <action> ...``.

        Args:
            command: The AWS CLI command string.

        Returns:
            The service name (e.g. "ec2", "s3api"), or empty string if
            the command cannot be parsed.
        """
        parts = command.strip().split()
        # Expected: ["aws", "<service>", ...]
        if len(parts) >= 2 and parts[0].lower() == "aws":
            return parts[1].lower()
        return ""

    def _inject_ec2_dry_run(self, command: str) -> DryRunResult:
        """Inject --dry-run flag for EC2 commands.

        EC2 supports native --dry-run for most mutating operations. The
        flag causes the API to validate the request without making changes.

        Args:
            command: The EC2 AWS CLI command.

        Returns:
            DryRunResult with --dry-run appended.
        """
        # Avoid duplicate injection if --dry-run already present
        if "--dry-run" in command:
            return DryRunResult(
                command=command,
                is_native_dry_run=True,
                preview_only=False,
                dry_run_notes=(
                    "EC2 --dry-run: validates permissions and parameters without making changes."
                ),
            )

        modified_command = f"{command} --dry-run"
        return DryRunResult(
            command=modified_command,
            is_native_dry_run=True,
            preview_only=False,
            dry_run_notes=(
                "EC2 --dry-run: validates permissions and parameters without making changes."
            ),
        )

    def _inject_cfn_dry_run(self, command: str) -> DryRunResult:
        """Inject change set mechanism for CloudFormation commands.

        CloudFormation uses change sets as the dry-run mechanism:
        - ``create-stack`` is transformed to ``create-change-set``
        - ``update-stack`` is transformed to
          ``create-change-set --change-set-type UPDATE``

        For other CloudFormation commands, preview-only mode is used.

        Args:
            command: The CloudFormation AWS CLI command.

        Returns:
            DryRunResult with the appropriate change set transformation.
        """
        cmd_lower = command.lower()

        if _CFN_CREATE_PATTERN in cmd_lower:
            modified = command.replace("create-stack", "create-change-set")
            return DryRunResult(
                command=modified,
                is_native_dry_run=True,
                preview_only=False,
                dry_run_notes=(
                    "CloudFormation: transformed create-stack to create-change-set. "
                    "Review the change set before executing."
                ),
            )

        if _CFN_UPDATE_PATTERN in cmd_lower:
            modified = command.replace("update-stack", "create-change-set")
            modified = f"{modified} --change-set-type UPDATE"
            return DryRunResult(
                command=modified,
                is_native_dry_run=True,
                preview_only=False,
                dry_run_notes=(
                    "CloudFormation: transformed update-stack to "
                    "create-change-set --change-set-type UPDATE. "
                    "Review the change set before executing."
                ),
            )

        # Other CloudFormation commands (delete-stack, etc.) → preview only
        return DryRunResult(
            command=command,
            is_native_dry_run=False,
            preview_only=True,
            dry_run_notes=(
                "CloudFormation: this operation does not support change sets. "
                "Command shown for review only — will NOT be executed."
            ),
        )

    def _get_preview_notes(self, service: str) -> str:
        """Get human-readable preview notes for services without native dry-run.

        Args:
            service: The AWS service name (e.g. "rds", "iam").

        Returns:
            Explanation string for the user.
        """
        notes_map: dict[str, str] = {
            "rds": (
                "RDS does not support --dry-run. "
                "Command shown for review only — will NOT be executed."
            ),
            "s3api": (
                "S3 API does not support --dry-run. "
                "Command shown for review only — will NOT be executed."
            ),
            "iam": (
                "IAM does not support --dry-run. "
                "Command shown for review only — will NOT be executed."
            ),
            "lambda": (
                "Lambda does not support --dry-run. "
                "Command shown for review only — will NOT be executed."
            ),
        }
        return notes_map.get(
            service,
            f"Service '{service}' does not support dry-run. "
            "Command shown for review only — will NOT be executed.",
        )
