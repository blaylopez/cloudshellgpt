"""Shared fixtures and pytest configuration for CloudShellGPT tests."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any

import boto3
import pytest
from moto import mock_aws

from cloudshellgpt.audit import AuditLogger
from cloudshellgpt.bedrock_translator import Translation
from cloudshellgpt.config import ConfigManager
from cloudshellgpt.cost import CostTracker
from cloudshellgpt.executor import ExecutionResult
from cloudshellgpt.intent import Intent


def pytest_configure(config: Any) -> None:
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: unit tests (fast, no AWS)")
    config.addinivalue_line("markers", "integration: integration tests (sandbox AWS)")
    config.addinivalue_line("markers", "eval: eval set precision tests")
    config.addinivalue_line("markers", "invariant: property-based invariant tests")
    config.addinivalue_line("markers", "slow: tests that take > 5s")
    config.addinivalue_line("markers", "persona1: owned by Persona 1 (Core + Tests)")
    config.addinivalue_line("markers", "persona2: owned by Persona 2 (Infra + CI)")
    config.addinivalue_line("markers", "persona3: owned by Persona 3 (UX + Safety)")
    config.addinivalue_line("markers", "persona4: owned by Persona 4 (Docs + Eval)")


# ---------------------------------------------------------------------------
# AWS credential fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def aws_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set dummy AWS credentials for moto."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture
def mock_aws_env(aws_credentials: None) -> Generator[None, None, None]:
    """Activate moto's mock_aws context for a test."""
    with mock_aws():
        yield


# ---------------------------------------------------------------------------
# Mocked boto3 client fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def s3_client(mock_aws_env: None) -> Any:
    """Provide a mocked S3 client."""
    return boto3.client("s3", region_name="us-east-1")


@pytest.fixture
def ec2_client(mock_aws_env: None) -> Any:
    """Provide a mocked EC2 client."""
    return boto3.client("ec2", region_name="us-east-1")


@pytest.fixture
def bedrock_runtime_client(mock_aws_env: None) -> Any:
    """Provide a mocked Bedrock Runtime client."""
    return boto3.client("bedrock-runtime", region_name="us-east-1")


@pytest.fixture
def cost_explorer_client(mock_aws_env: None) -> Any:
    """Provide a mocked Cost Explorer client."""
    return boto3.client("ce", region_name="us-east-1")


@pytest.fixture
def iam_client(mock_aws_env: None) -> Any:
    """Provide a mocked IAM client."""
    return boto3.client("iam", region_name="us-east-1")


# ---------------------------------------------------------------------------
# Domain model fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_intent() -> Intent:
    """Provide a sample Intent for testing.

    Returns:
        An Intent representing a Spanish S3 list-buckets request.
    """
    return Intent(
        action="list",
        service="s3",
        confidence=0.9,
        raw_input="lista los buckets de S3",
        detected_language="es",
    )


@pytest.fixture
def sample_translation() -> Translation:
    """Provide a sample low-risk Translation for testing.

    Returns:
        A Translation representing a safe, read-only S3 list-buckets command.
    """
    return Translation(
        command="aws s3api list-buckets",
        explanation="Lista los buckets de S3",
        detailed_explanation=(
            "Usa s3api para listar todos los buckets disponibles en la cuenta. "
            "Operación read-only sin costo adicional."
        ),
        risk_level="low",
        estimated_cost="$0.00",
        requires_dry_run=False,
        affected_resources=[],
        flags_used={},
    )


@pytest.fixture
def sample_translation_destructive() -> Translation:
    """Provide a destructive high-risk Translation for testing.

    Returns:
        A Translation representing a recursive S3 delete command.
    """
    return Translation(
        command="aws s3 rm s3://prod-bucket --recursive",
        explanation="Delete all objects in prod-bucket",
        detailed_explanation=(
            "Elimina recursivamente TODOS los objetos del bucket prod-bucket. "
            "Esta acción es irreversible."
        ),
        risk_level="high",
        estimated_cost="$0.00",
        requires_dry_run=True,
        affected_resources=["s3://prod-bucket/*"],
        flags_used={"--recursive": "Delete all objects recursively"},
    )


@pytest.fixture
def sample_execution_result() -> ExecutionResult:
    """Provide a successful ExecutionResult for testing.

    Returns:
        An ExecutionResult representing a successful S3 list-buckets call.
    """
    return ExecutionResult(
        command="aws s3api list-buckets",
        stdout='{"Buckets": []}',
        stderr="",
        exit_code=0,
        duration_ms=150,
        dry_run=False,
    )


@pytest.fixture
def sample_execution_result_error() -> ExecutionResult:
    """Provide a failed ExecutionResult for testing.

    Returns:
        An ExecutionResult representing an AccessDenied error.
    """
    return ExecutionResult(
        command="aws s3 rm s3://prod",
        stdout="",
        stderr="An error occurred (AccessDenied)",
        exit_code=1,
        duration_ms=200,
        dry_run=False,
        error="AccessDenied",
    )


# ---------------------------------------------------------------------------
# File-based fixtures (use tmp_path)
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_config(tmp_path: Path) -> ConfigManager:
    """Provide a ConfigManager backed by a temporary config file.

    Returns:
        A ConfigManager instance using a temp directory for storage.
    """
    return ConfigManager(config_path=tmp_path / "config.yaml")


@pytest.fixture
def tmp_audit_log(tmp_path: Path) -> AuditLogger:
    """Provide an AuditLogger backed by a temporary log file.

    Returns:
        An AuditLogger instance writing to a temp directory.
    """
    return AuditLogger(log_path=tmp_path / "audit.log")


@pytest.fixture
def tmp_cost_tracker(tmp_path: Path) -> CostTracker:
    """Provide a CostTracker backed by a temporary session file.

    Returns:
        A CostTracker instance writing to a temp directory.
    """
    return CostTracker(session_path=tmp_path / "costs.yaml")


# ---------------------------------------------------------------------------
# Mock Bedrock response factory
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_bedrock_response() -> Any:
    """Provide a factory for mock Bedrock converse() responses.

    Returns:
        A callable that accepts a JSON string and returns a dict
        matching the Bedrock Converse API response structure.
    """

    def _factory(response_text: str) -> dict[str, Any]:
        """Build a mock Bedrock converse() response.

        Args:
            response_text: The text content to include in the response.

        Returns:
            A dict mimicking the Bedrock Converse API response shape.
        """
        return {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [{"text": response_text}],
                }
            },
            "usage": {
                "inputTokens": 150,
                "outputTokens": 80,
                "totalTokens": 230,
            },
            "stopReason": "end_turn",
            "metrics": {"latencyMs": 450},
        }

    return _factory
