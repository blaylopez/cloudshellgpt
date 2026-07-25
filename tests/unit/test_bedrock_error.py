"""Unit tests for BedrockError handling in bedrock_translator and CLI."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError, ReadTimeoutError

from cloudshellgpt.bedrock_translator import (
    BedrockError,
    BedrockErrorType,
    BedrockTranslator,
)
from cloudshellgpt.intent import Intent


@pytest.fixture
def sample_intent() -> Intent:
    """Provide a sample Intent for translation tests."""
    return Intent(
        action="list",
        service="s3",
        confidence=0.9,
        raw_input="lista los buckets de S3",
        detected_language="es",
    )


@pytest.fixture
def translator() -> BedrockTranslator:
    """Provide a BedrockTranslator with a mocked boto3 client."""
    with patch("boto3.client"):
        t = BedrockTranslator()
    return t


# ---------------------------------------------------------------------------
# BedrockError construction tests
# ---------------------------------------------------------------------------


class TestBedrockErrorStructure:
    """Verify BedrockError carries structured info correctly."""

    def test_default_error_type_is_generic(self) -> None:
        err = BedrockError("Something failed")
        assert err.error_type == BedrockErrorType.GENERIC
        assert err.user_message == "Something failed"
        assert err.suggestion == ""
        assert err.technical_detail == ""

    def test_error_with_all_fields(self) -> None:
        err = BedrockError(
            "Access denied",
            error_type=BedrockErrorType.CREDENTIALS,
            suggestion="Check IAM permissions",
            technical_detail="AccessDeniedException: User is not authorized",
        )
        assert err.error_type == BedrockErrorType.CREDENTIALS
        assert err.user_message == "Access denied"
        assert err.suggestion == "Check IAM permissions"
        assert err.technical_detail == "AccessDeniedException: User is not authorized"

    def test_str_representation_is_user_message(self) -> None:
        err = BedrockError("Timeout occurred", error_type=BedrockErrorType.TIMEOUT)
        assert str(err) == "Timeout occurred"

    def test_error_type_enum_values(self) -> None:
        assert BedrockErrorType.CREDENTIALS == "credentials"
        assert BedrockErrorType.THROTTLING == "throttling"
        assert BedrockErrorType.TIMEOUT == "timeout"
        assert BedrockErrorType.MODEL_NOT_AVAILABLE == "model_not_available"
        assert BedrockErrorType.INVALID_RESPONSE == "invalid_response"
        assert BedrockErrorType.GENERIC == "generic"


# ---------------------------------------------------------------------------
# translate() error handling tests
# ---------------------------------------------------------------------------


class TestTranslateErrorHandling:
    """Verify translate() maps exceptions to structured BedrockErrors."""

    @pytest.mark.parametrize(
        ("error_code", "expected_type"),
        [
            ("AccessDeniedException", BedrockErrorType.CREDENTIALS),
            ("UnrecognizedClientException", BedrockErrorType.CREDENTIALS),
            ("ExpiredTokenException", BedrockErrorType.CREDENTIALS),
            ("ThrottlingException", BedrockErrorType.THROTTLING),
            ("ServiceQuotaExceededException", BedrockErrorType.THROTTLING),
            ("ModelTimeoutException", BedrockErrorType.TIMEOUT),
            ("ModelNotReadyException", BedrockErrorType.MODEL_NOT_AVAILABLE),
            ("ResourceNotFoundException", BedrockErrorType.MODEL_NOT_AVAILABLE),
            ("ValidationException", BedrockErrorType.INVALID_RESPONSE),
        ],
    )
    def test_client_error_maps_to_correct_type(
        self,
        error_code: str,
        expected_type: BedrockErrorType,
        sample_intent: Intent,
    ) -> None:
        """Each ClientError code maps to the expected BedrockErrorType."""
        client_error = ClientError(
            {"Error": {"Code": error_code, "Message": "test error"}},
            "Converse",
        )

        with patch("boto3.client"):
            translator = BedrockTranslator(max_retries=0)
            translator.client.converse = MagicMock(side_effect=client_error)

            with pytest.raises(BedrockError) as exc_info:
                translator.translate(sample_intent)

            assert exc_info.value.error_type == expected_type
            assert exc_info.value.suggestion != ""
            assert exc_info.value.technical_detail != ""

    def test_unknown_client_error_maps_to_generic(self, sample_intent: Intent) -> None:
        """Unknown ClientError codes get GENERIC type."""
        client_error = ClientError(
            {"Error": {"Code": "SomeNewException", "Message": "unexpected"}},
            "Converse",
        )

        with patch("boto3.client"):
            translator = BedrockTranslator(max_retries=0)
            translator.client.converse = MagicMock(side_effect=client_error)

            with pytest.raises(BedrockError) as exc_info:
                translator.translate(sample_intent)

            assert exc_info.value.error_type == BedrockErrorType.GENERIC
            assert "SomeNewException" in exc_info.value.user_message

    def test_read_timeout_maps_to_timeout(self, sample_intent: Intent) -> None:
        """ReadTimeoutError maps to TIMEOUT type."""
        timeout_error = ReadTimeoutError(endpoint_url="https://bedrock.us-east-1.amazonaws.com")

        with patch("boto3.client"):
            translator = BedrockTranslator(max_retries=0)
            translator.client.converse = MagicMock(side_effect=timeout_error)

            with pytest.raises(BedrockError) as exc_info:
                translator.translate(sample_intent)

            assert exc_info.value.error_type == BedrockErrorType.TIMEOUT
            assert "timed out" in exc_info.value.user_message

    def test_generic_exception_maps_to_generic(self, sample_intent: Intent) -> None:
        """Unexpected exceptions map to GENERIC type."""
        with patch("boto3.client"):
            translator = BedrockTranslator(max_retries=0)
            translator.client.converse = MagicMock(side_effect=RuntimeError("network unreachable"))

            with pytest.raises(BedrockError) as exc_info:
                translator.translate(sample_intent)

            assert exc_info.value.error_type == BedrockErrorType.GENERIC
            assert "Unexpected error" in exc_info.value.user_message

    def test_invalid_json_response_maps_to_invalid_response(
        self, sample_intent: Intent, mock_bedrock_response: Any
    ) -> None:
        """Invalid JSON from the model maps to INVALID_RESPONSE type."""
        bad_response = mock_bedrock_response("This is not JSON at all")

        with patch("boto3.client"):
            translator = BedrockTranslator(max_retries=0)
            translator.client.converse = MagicMock(return_value=bad_response)

            with pytest.raises(BedrockError) as exc_info:
                translator.translate(sample_intent)

            assert exc_info.value.error_type == BedrockErrorType.INVALID_RESPONSE
            assert "invalid JSON" in exc_info.value.user_message

    def test_malformed_response_structure_maps_to_invalid_response(
        self, sample_intent: Intent
    ) -> None:
        """Missing keys in response structure maps to INVALID_RESPONSE."""
        malformed_response: dict[str, Any] = {"output": {"message": {}}}

        with patch("boto3.client"):
            translator = BedrockTranslator(max_retries=0)
            translator.client.converse = MagicMock(return_value=malformed_response)

            with pytest.raises(BedrockError) as exc_info:
                translator.translate(sample_intent)

            assert exc_info.value.error_type == BedrockErrorType.INVALID_RESPONSE
            assert "empty or malformed" in exc_info.value.user_message

    def test_successful_translation_does_not_raise(
        self, sample_intent: Intent, mock_bedrock_response: Any
    ) -> None:
        """Successful translation returns a Translation object."""
        valid_json = json.dumps(
            {
                "command": "aws s3api list-buckets",
                "explanation": "Lista buckets",
                "detailed_explanation": "Detalle",
                "risk_level": "low",
                "estimated_cost": "$0.00",
                "requires_dry_run": False,
                "affected_resources": [],
                "flags_used": {},
            }
        )
        response = mock_bedrock_response(valid_json)

        with patch("boto3.client"):
            translator = BedrockTranslator(max_retries=0)
            translator.client.converse = MagicMock(return_value=response)
            result = translator.translate(sample_intent)

        assert result.command == "aws s3api list-buckets"
        assert result.risk_level == "low"


# ---------------------------------------------------------------------------
# CLI error display tests
# ---------------------------------------------------------------------------


class TestCLIBedrockErrorDisplay:
    """Verify the CLI displays BedrockError gracefully."""

    def test_show_bedrock_error_renders_panel(self) -> None:
        """_show_bedrock_error prints a Rich panel without raising."""
        from cloudshellgpt.cli import _show_bedrock_error

        err = BedrockError(
            "Access denied",
            error_type=BedrockErrorType.CREDENTIALS,
            suggestion="Check IAM permissions",
            technical_detail="AccessDeniedException: not authorized",
        )

        # Should not raise — just prints to console
        with patch("cloudshellgpt.cli.console") as mock_console:
            _show_bedrock_error(err)
            mock_console.print.assert_called_once()
            call_args = mock_console.print.call_args
            panel = call_args[0][0]
            # Verify it's a Rich Panel
            from rich.panel import Panel

            assert isinstance(panel, Panel)

    def test_show_bedrock_error_includes_suggestion(self) -> None:
        """Panel content includes the suggestion field."""
        from cloudshellgpt.cli import _show_bedrock_error

        err = BedrockError(
            "Throttled",
            error_type=BedrockErrorType.THROTTLING,
            suggestion="Try again in a few seconds",
        )

        with patch("cloudshellgpt.cli.console") as mock_console:
            _show_bedrock_error(err)
            panel = mock_console.print.call_args[0][0]
            # Panel renderable contains the suggestion text
            assert "Try again in a few seconds" in panel.renderable

    def test_show_bedrock_error_without_optional_fields(self) -> None:
        """Panel renders cleanly even without suggestion/detail."""
        from cloudshellgpt.cli import _show_bedrock_error

        err = BedrockError("Generic failure")

        with patch("cloudshellgpt.cli.console") as mock_console:
            _show_bedrock_error(err)
            panel = mock_console.print.call_args[0][0]
            assert "Generic failure" in panel.renderable


# ---------------------------------------------------------------------------
# Error suggestion content quality
# ---------------------------------------------------------------------------


class TestErrorSuggestions:
    """Verify each error type provides actionable suggestions."""

    @pytest.mark.parametrize(
        "error_code",
        [
            "AccessDeniedException",
            "UnrecognizedClientException",
            "ExpiredTokenException",
            "ThrottlingException",
            "ServiceQuotaExceededException",
            "ModelTimeoutException",
            "ModelNotReadyException",
            "ResourceNotFoundException",
            "ValidationException",
        ],
    )
    def test_all_mapped_errors_have_non_empty_suggestions(self, error_code: str) -> None:
        """Every mapped ClientError provides a non-empty suggestion."""
        with patch("boto3.client"):
            translator = BedrockTranslator()
            exc = ClientError(
                {"Error": {"Code": error_code, "Message": "test"}},
                "Converse",
            )
            bedrock_err = translator._map_client_error(error_code, exc)

            assert bedrock_err.suggestion != ""
            assert len(bedrock_err.suggestion) > 10  # Actionable, not just "..."


# ---------------------------------------------------------------------------
# Exponential backoff retry tests
# ---------------------------------------------------------------------------


class TestExponentialBackoffRetry:
    """Verify retry logic with exponential backoff for transient errors."""

    def test_throttling_retries_then_succeeds(
        self, sample_intent: Intent, mock_bedrock_response: Any
    ) -> None:
        """Throttling errors are retried, and success on later attempt works."""
        throttle_error = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "Converse",
        )
        valid_json = json.dumps(
            {
                "command": "aws s3api list-buckets",
                "explanation": "Lista buckets",
                "detailed_explanation": "Detalle",
                "risk_level": "low",
                "estimated_cost": "$0.00",
                "requires_dry_run": False,
                "affected_resources": [],
                "flags_used": {},
            }
        )
        success_response = mock_bedrock_response(valid_json)

        with patch("boto3.client"):
            translator = BedrockTranslator(max_retries=2, base_delay=0.01)
            # Fail twice, succeed on third attempt
            translator.client.converse = MagicMock(
                side_effect=[throttle_error, throttle_error, success_response]
            )

            with patch("time.sleep"):
                result = translator.translate(sample_intent)

        assert result.command == "aws s3api list-buckets"
        assert translator.client.converse.call_count == 3

    def test_timeout_retries_then_succeeds(
        self, sample_intent: Intent, mock_bedrock_response: Any
    ) -> None:
        """ReadTimeoutError is retried, and success on later attempt works."""
        timeout_error = ReadTimeoutError(endpoint_url="https://bedrock.us-east-1.amazonaws.com")
        valid_json = json.dumps(
            {
                "command": "aws s3api list-buckets",
                "explanation": "Lista buckets",
                "detailed_explanation": "Detalle",
                "risk_level": "low",
                "estimated_cost": "$0.00",
                "requires_dry_run": False,
                "affected_resources": [],
                "flags_used": {},
            }
        )
        success_response = mock_bedrock_response(valid_json)

        with patch("boto3.client"):
            translator = BedrockTranslator(max_retries=2, base_delay=0.01)
            translator.client.converse = MagicMock(side_effect=[timeout_error, success_response])

            with patch("time.sleep"):
                result = translator.translate(sample_intent)

        assert result.command == "aws s3api list-buckets"
        assert translator.client.converse.call_count == 2

    def test_throttling_exhausts_retries_then_raises(self, sample_intent: Intent) -> None:
        """After exhausting retries, the last BedrockError is raised."""
        throttle_error = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "Converse",
        )

        with patch("boto3.client"):
            translator = BedrockTranslator(max_retries=2, base_delay=0.01)
            translator.client.converse = MagicMock(side_effect=throttle_error)

            with patch("time.sleep") as mock_sleep:
                with pytest.raises(BedrockError) as exc_info:
                    translator.translate(sample_intent)

        assert exc_info.value.error_type == BedrockErrorType.THROTTLING
        # 3 attempts total: initial + 2 retries
        assert translator.client.converse.call_count == 3
        # sleep called twice (before retry 2 and 3)
        assert mock_sleep.call_count == 2

    def test_non_retryable_error_fails_immediately(self, sample_intent: Intent) -> None:
        """Non-transient errors (credentials) are NOT retried."""
        access_denied = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Denied"}},
            "Converse",
        )

        with patch("boto3.client"):
            translator = BedrockTranslator(max_retries=3, base_delay=0.01)
            translator.client.converse = MagicMock(side_effect=access_denied)

            with patch("time.sleep") as mock_sleep:
                with pytest.raises(BedrockError) as exc_info:
                    translator.translate(sample_intent)

        assert exc_info.value.error_type == BedrockErrorType.CREDENTIALS
        # Only 1 attempt — no retries for non-transient errors
        assert translator.client.converse.call_count == 1
        mock_sleep.assert_not_called()

    def test_exponential_backoff_delays_increase(self, sample_intent: Intent) -> None:
        """Backoff delays increase exponentially between retries."""
        throttle_error = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "Converse",
        )

        with patch("boto3.client"):
            translator = BedrockTranslator(max_retries=3, base_delay=1.0)
            translator.client.converse = MagicMock(side_effect=throttle_error)

            with patch("time.sleep") as mock_sleep:
                with patch("random.uniform", return_value=0.0):
                    with pytest.raises(BedrockError):
                        translator.translate(sample_intent)

        # With jitter=0: delays are 1.0, 2.0, 4.0
        delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert delays == [1.0, 2.0, 4.0]

    def test_backoff_includes_jitter(self, sample_intent: Intent) -> None:
        """Backoff delay includes random jitter component."""
        throttle_error = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "Converse",
        )

        with patch("boto3.client"):
            translator = BedrockTranslator(max_retries=1, base_delay=1.0)
            translator.client.converse = MagicMock(side_effect=throttle_error)

            with patch("time.sleep") as mock_sleep:
                with patch("random.uniform", return_value=0.25):
                    with pytest.raises(BedrockError):
                        translator.translate(sample_intent)

        # base_delay * 2^0 + jitter = 1.0 + 0.25 = 1.25
        delay = mock_sleep.call_args_list[0].args[0]
        assert delay == 1.25

    def test_is_retryable_property_throttling(self) -> None:
        """BedrockError.is_retryable returns True for throttling errors."""
        err = BedrockError("Throttled", error_type=BedrockErrorType.THROTTLING)
        assert err.is_retryable is True

    def test_is_retryable_property_timeout(self) -> None:
        """BedrockError.is_retryable returns True for timeout errors."""
        err = BedrockError("Timed out", error_type=BedrockErrorType.TIMEOUT)
        assert err.is_retryable is True

    def test_is_retryable_property_credentials(self) -> None:
        """BedrockError.is_retryable returns False for credential errors."""
        err = BedrockError("Access denied", error_type=BedrockErrorType.CREDENTIALS)
        assert err.is_retryable is False

    def test_is_retryable_property_generic(self) -> None:
        """BedrockError.is_retryable returns False for generic errors."""
        err = BedrockError("Generic failure")
        assert err.is_retryable is False

    def test_max_retries_zero_means_no_retry(self, sample_intent: Intent) -> None:
        """With max_retries=0, transient errors fail on first attempt."""
        throttle_error = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "Converse",
        )

        with patch("boto3.client"):
            translator = BedrockTranslator(max_retries=0)
            translator.client.converse = MagicMock(side_effect=throttle_error)

            with patch("time.sleep") as mock_sleep:
                with pytest.raises(BedrockError) as exc_info:
                    translator.translate(sample_intent)

        assert exc_info.value.error_type == BedrockErrorType.THROTTLING
        assert translator.client.converse.call_count == 1
        mock_sleep.assert_not_called()

    def test_model_timeout_retries(self, sample_intent: Intent) -> None:
        """ModelTimeoutException (ClientError) is retried as transient."""
        model_timeout = ClientError(
            {"Error": {"Code": "ModelTimeoutException", "Message": "Timeout"}},
            "Converse",
        )

        with patch("boto3.client"):
            translator = BedrockTranslator(max_retries=2, base_delay=0.01)
            translator.client.converse = MagicMock(side_effect=model_timeout)

            with patch("time.sleep"):
                with pytest.raises(BedrockError) as exc_info:
                    translator.translate(sample_intent)

        assert exc_info.value.error_type == BedrockErrorType.TIMEOUT
        assert translator.client.converse.call_count == 3

    def test_generic_exception_not_retried(self, sample_intent: Intent) -> None:
        """Unexpected exceptions (non-ClientError, non-ReadTimeout) are not retried."""
        with patch("boto3.client"):
            translator = BedrockTranslator(max_retries=3, base_delay=0.01)
            translator.client.converse = MagicMock(side_effect=RuntimeError("connection reset"))

            with patch("time.sleep") as mock_sleep:
                with pytest.raises(BedrockError) as exc_info:
                    translator.translate(sample_intent)

        assert exc_info.value.error_type == BedrockErrorType.GENERIC
        assert translator.client.converse.call_count == 1
        mock_sleep.assert_not_called()
