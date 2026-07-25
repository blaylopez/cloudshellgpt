"""Unit tests for BedrockTranslator response parsing and JSON extraction."""

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
    Translation,
)
from cloudshellgpt.intent import Intent

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


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
        t = BedrockTranslator(max_retries=0)
    return t


@pytest.fixture
def full_valid_json() -> dict[str, Any]:
    """Provide a complete valid translation JSON with all 8 fields."""
    return {
        "command": "aws s3api list-buckets --output table",
        "explanation": "Lista todos los buckets de S3",
        "detailed_explanation": "Usa s3api para listar todos los buckets disponibles.",
        "risk_level": "low",
        "estimated_cost": "$0.00",
        "requires_dry_run": False,
        "affected_resources": ["s3://my-bucket", "s3://other-bucket"],
        "flags_used": {"--output": "table format", "--query": "JMESPath filter"},
    }


# ---------------------------------------------------------------------------
# TestResponseParsing
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResponseParsing:
    """Verify _parse_response produces correct Translation objects from valid JSON."""

    def test_parse_response_valid_json_all_fields(
        self,
        translator: BedrockTranslator,
        mock_bedrock_response: Any,
        full_valid_json: dict[str, Any],
    ) -> None:
        """Full valid JSON with all 8 fields returns Translation with correct values."""
        response = mock_bedrock_response(json.dumps(full_valid_json))
        result = translator._parse_response(response)

        assert result.command == full_valid_json["command"]
        assert result.explanation == full_valid_json["explanation"]
        assert result.detailed_explanation == full_valid_json["detailed_explanation"]
        assert result.risk_level == full_valid_json["risk_level"]
        assert result.estimated_cost == full_valid_json["estimated_cost"]
        assert result.requires_dry_run == full_valid_json["requires_dry_run"]
        assert result.affected_resources == full_valid_json["affected_resources"]
        assert result.flags_used == full_valid_json["flags_used"]

    def test_parse_response_valid_json_creates_translation_object(
        self,
        translator: BedrockTranslator,
        mock_bedrock_response: Any,
        full_valid_json: dict[str, Any],
    ) -> None:
        """Verify returned type is Translation."""
        response = mock_bedrock_response(json.dumps(full_valid_json))
        result = translator._parse_response(response)

        assert isinstance(result, Translation)

    def test_parse_response_preserves_command_exactly(
        self,
        translator: BedrockTranslator,
        mock_bedrock_response: Any,
    ) -> None:
        """Command field is preserved character-for-character."""
        command = "aws ec2 describe-instances --filters 'Name=tag:Env,Values=prod' --output json"
        data = {"command": command, "explanation": "desc", "detailed_explanation": "det"}
        response = mock_bedrock_response(json.dumps(data))
        result = translator._parse_response(response)

        assert result.command == command

    def test_parse_response_preserves_risk_level(
        self,
        translator: BedrockTranslator,
        mock_bedrock_response: Any,
    ) -> None:
        """Risk levels (low, medium, high, critical) are preserved."""
        for level in ("low", "medium", "high", "critical"):
            data = {
                "command": "aws s3 ls",
                "explanation": "x",
                "detailed_explanation": "y",
                "risk_level": level,
            }
            response = mock_bedrock_response(json.dumps(data))
            result = translator._parse_response(response)
            assert result.risk_level == level

    def test_parse_response_preserves_affected_resources_list(
        self,
        translator: BedrockTranslator,
        mock_bedrock_response: Any,
    ) -> None:
        """List of strings in affected_resources is preserved."""
        resources = ["arn:aws:s3:::prod-bucket", "arn:aws:s3:::staging-bucket/*"]
        data = {
            "command": "aws s3 rm s3://prod-bucket --recursive",
            "explanation": "del",
            "detailed_explanation": "det",
            "affected_resources": resources,
        }
        response = mock_bedrock_response(json.dumps(data))
        result = translator._parse_response(response)

        assert result.affected_resources == resources

    def test_parse_response_preserves_flags_used_dict(
        self,
        translator: BedrockTranslator,
        mock_bedrock_response: Any,
    ) -> None:
        """Dict[str, str] in flags_used is preserved."""
        flags = {"--recursive": "Delete all objects", "--force": "Skip confirmation"}
        data = {
            "command": "aws s3 rm s3://bucket --recursive --force",
            "explanation": "del",
            "detailed_explanation": "det",
            "flags_used": flags,
        }
        response = mock_bedrock_response(json.dumps(data))
        result = translator._parse_response(response)

        assert result.flags_used == flags


# ---------------------------------------------------------------------------
# TestJsonExtractionWithMarkdownFences
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestJsonExtractionWithMarkdownFences:
    """Verify _extract_json strips markdown code fences correctly."""

    def test_extract_json_with_json_fence(
        self,
        translator: BedrockTranslator,
    ) -> None:
        """```json\\n{...}\\n``` is parsed correctly."""
        data = {"command": "aws s3 ls", "explanation": "list"}
        fenced = f"```json\n{json.dumps(data)}\n```"
        result = translator._extract_json(fenced)

        assert result == data

    def test_extract_json_with_plain_fence(
        self,
        translator: BedrockTranslator,
    ) -> None:
        """```\\n{...}\\n``` (no language hint) is parsed correctly."""
        data = {"command": "aws ec2 describe-instances", "explanation": "desc"}
        fenced = f"```\n{json.dumps(data)}\n```"
        result = translator._extract_json(fenced)

        assert result == data

    def test_extract_json_with_fence_and_extra_whitespace(
        self,
        translator: BedrockTranslator,
    ) -> None:
        """Whitespace around fences is handled correctly."""
        data = {"command": "aws lambda list-functions", "explanation": "list"}
        fenced = f"  \n```json\n{json.dumps(data)}\n```\n  "
        result = translator._extract_json(fenced)

        assert result == data

    def test_extract_json_with_language_hint_fence(
        self,
        translator: BedrockTranslator,
    ) -> None:
        """```json\\n{...}\\n``` with 'json' language hint parses correctly."""
        data = {
            "command": "aws iam list-users",
            "explanation": "users",
            "detailed_explanation": "lists IAM users",
        }
        fenced = f"```json\n{json.dumps(data, indent=2)}\n```"
        result = translator._extract_json(fenced)

        assert result == data

    def test_full_translate_with_fenced_response(
        self,
        translator: BedrockTranslator,
        mock_bedrock_response: Any,
        sample_intent: Intent,
    ) -> None:
        """End-to-end: translator.translate() with fenced response works."""
        data = {
            "command": "aws s3api list-buckets",
            "explanation": "Lista buckets",
            "detailed_explanation": "Detalle completo",
            "risk_level": "low",
            "estimated_cost": "$0.00",
            "requires_dry_run": False,
            "affected_resources": [],
            "flags_used": {},
        }
        fenced_text = f"```json\n{json.dumps(data)}\n```"
        response = mock_bedrock_response(fenced_text)
        translator.client.converse = MagicMock(return_value=response)

        result = translator.translate(sample_intent)

        assert result.command == "aws s3api list-buckets"
        assert result.explanation == "Lista buckets"


# ---------------------------------------------------------------------------
# TestJsonExtractionWithoutFences
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestJsonExtractionWithoutFences:
    """Verify _extract_json parses plain JSON without fences."""

    def test_extract_json_plain_json_object(
        self,
        translator: BedrockTranslator,
    ) -> None:
        """Plain JSON without any fences is parsed correctly."""
        data = {"command": "aws s3 ls", "explanation": "list buckets"}
        result = translator._extract_json(json.dumps(data))

        assert result == data

    def test_extract_json_with_leading_trailing_whitespace(
        self,
        translator: BedrockTranslator,
    ) -> None:
        """Whitespace-padded JSON is parsed correctly."""
        data = {"command": "aws ec2 describe-instances", "explanation": "instances"}
        text = f"   \n{json.dumps(data)}\n   "
        result = translator._extract_json(text)

        assert result == data

    def test_extract_json_with_newlines_in_values(
        self,
        translator: BedrockTranslator,
    ) -> None:
        """JSON with \\n in string values is parsed correctly."""
        data = {
            "command": "aws s3 ls",
            "explanation": "line1\nline2",
            "detailed_explanation": "step1\nstep2\nstep3",
        }
        result = translator._extract_json(json.dumps(data))

        assert result["explanation"] == "line1\nline2"
        assert result["detailed_explanation"] == "step1\nstep2\nstep3"

    def test_full_translate_without_fences(
        self,
        translator: BedrockTranslator,
        mock_bedrock_response: Any,
        sample_intent: Intent,
    ) -> None:
        """End-to-end: translator.translate() with plain JSON works."""
        data = {
            "command": "aws s3api list-buckets --output json",
            "explanation": "Lista buckets en JSON",
            "detailed_explanation": "Usa output json para parsear",
            "risk_level": "low",
            "estimated_cost": "$0.00",
            "requires_dry_run": False,
            "affected_resources": [],
            "flags_used": {"--output": "json format"},
        }
        response = mock_bedrock_response(json.dumps(data))
        translator.client.converse = MagicMock(return_value=response)

        result = translator.translate(sample_intent)

        assert result.command == "aws s3api list-buckets --output json"
        assert result.flags_used == {"--output": "json format"}


# ---------------------------------------------------------------------------
# TestMissingFields
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMissingFields:
    """Verify defaults are applied when optional fields are absent."""

    def test_missing_explanation_defaults_to_empty_string(
        self,
        translator: BedrockTranslator,
        mock_bedrock_response: Any,
    ) -> None:
        """No 'explanation' key defaults to empty string."""
        data = {"command": "aws s3 ls", "detailed_explanation": "det"}
        response = mock_bedrock_response(json.dumps(data))
        result = translator._parse_response(response)

        assert result.explanation == ""

    def test_missing_detailed_explanation_defaults_to_empty_string(
        self,
        translator: BedrockTranslator,
        mock_bedrock_response: Any,
    ) -> None:
        """No 'detailed_explanation' key defaults to empty string."""
        data = {"command": "aws s3 ls", "explanation": "list"}
        response = mock_bedrock_response(json.dumps(data))
        result = translator._parse_response(response)

        assert result.detailed_explanation == ""

    def test_missing_risk_level_defaults_to_low(
        self,
        translator: BedrockTranslator,
        mock_bedrock_response: Any,
    ) -> None:
        """No 'risk_level' key defaults to 'low'."""
        data = {"command": "aws s3 ls", "explanation": "l", "detailed_explanation": "d"}
        response = mock_bedrock_response(json.dumps(data))
        result = translator._parse_response(response)

        assert result.risk_level == "low"

    def test_missing_estimated_cost_defaults_to_zero(
        self,
        translator: BedrockTranslator,
        mock_bedrock_response: Any,
    ) -> None:
        """No 'estimated_cost' key defaults to '$0.00'."""
        data = {"command": "aws s3 ls", "explanation": "l", "detailed_explanation": "d"}
        response = mock_bedrock_response(json.dumps(data))
        result = translator._parse_response(response)

        assert result.estimated_cost == "$0.00"

    def test_missing_requires_dry_run_defaults_to_false(
        self,
        translator: BedrockTranslator,
        mock_bedrock_response: Any,
    ) -> None:
        """No 'requires_dry_run' key defaults to False."""
        data = {"command": "aws s3 ls", "explanation": "l", "detailed_explanation": "d"}
        response = mock_bedrock_response(json.dumps(data))
        result = translator._parse_response(response)

        assert result.requires_dry_run is False

    def test_missing_affected_resources_defaults_to_empty_list(
        self,
        translator: BedrockTranslator,
        mock_bedrock_response: Any,
    ) -> None:
        """No 'affected_resources' key defaults to empty list."""
        data = {"command": "aws s3 ls", "explanation": "l", "detailed_explanation": "d"}
        response = mock_bedrock_response(json.dumps(data))
        result = translator._parse_response(response)

        assert result.affected_resources == []

    def test_missing_flags_used_defaults_to_empty_dict(
        self,
        translator: BedrockTranslator,
        mock_bedrock_response: Any,
    ) -> None:
        """No 'flags_used' key defaults to empty dict."""
        data = {"command": "aws s3 ls", "explanation": "l", "detailed_explanation": "d"}
        response = mock_bedrock_response(json.dumps(data))
        result = translator._parse_response(response)

        assert result.flags_used == {}

    def test_only_command_field_present(
        self,
        translator: BedrockTranslator,
        mock_bedrock_response: Any,
    ) -> None:
        """Only 'command' field present, all others get defaults."""
        data = {"command": "aws sts get-caller-identity"}
        response = mock_bedrock_response(json.dumps(data))
        result = translator._parse_response(response)

        assert result.command == "aws sts get-caller-identity"
        assert result.explanation == ""
        assert result.detailed_explanation == ""
        assert result.risk_level == "low"
        assert result.estimated_cost == "$0.00"
        assert result.requires_dry_run is False
        assert result.affected_resources == []
        assert result.flags_used == {}

    def test_missing_command_raises_error(
        self,
        translator: BedrockTranslator,
        mock_bedrock_response: Any,
    ) -> None:
        """No 'command' key raises KeyError or BedrockError."""
        data = {"explanation": "something", "risk_level": "low"}
        response = mock_bedrock_response(json.dumps(data))

        with pytest.raises((KeyError, BedrockError)):
            translator._parse_response(response)


# ---------------------------------------------------------------------------
# TestEmptyResponse
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestEmptyResponse:
    """Verify empty/malformed responses raise BedrockError with INVALID_RESPONSE."""

    def test_empty_response_dict_raises_bedrock_error(
        self,
        translator: BedrockTranslator,
    ) -> None:
        """Empty dict {} raises BedrockError."""
        with pytest.raises(BedrockError) as exc_info:
            translator._parse_response({})

        assert exc_info.value.error_type == BedrockErrorType.INVALID_RESPONSE

    def test_response_missing_output_key_raises_bedrock_error(
        self,
        translator: BedrockTranslator,
    ) -> None:
        """No 'output' key raises BedrockError."""
        with pytest.raises(BedrockError) as exc_info:
            translator._parse_response({"usage": {"inputTokens": 10}})

        assert exc_info.value.error_type == BedrockErrorType.INVALID_RESPONSE

    def test_response_missing_message_key_raises_bedrock_error(
        self,
        translator: BedrockTranslator,
    ) -> None:
        """Has 'output' but no 'message' raises BedrockError."""
        with pytest.raises(BedrockError) as exc_info:
            translator._parse_response({"output": {}})

        assert exc_info.value.error_type == BedrockErrorType.INVALID_RESPONSE

    def test_response_missing_content_key_raises_bedrock_error(
        self,
        translator: BedrockTranslator,
    ) -> None:
        """Has 'message' but no 'content' raises BedrockError."""
        with pytest.raises(BedrockError) as exc_info:
            translator._parse_response({"output": {"message": {"role": "assistant"}}})

        assert exc_info.value.error_type == BedrockErrorType.INVALID_RESPONSE

    def test_response_empty_content_list_raises_bedrock_error(
        self,
        translator: BedrockTranslator,
    ) -> None:
        """'content': [] (empty list) raises BedrockError."""
        response: dict[str, Any] = {"output": {"message": {"role": "assistant", "content": []}}}
        with pytest.raises(BedrockError) as exc_info:
            translator._parse_response(response)

        assert exc_info.value.error_type == BedrockErrorType.INVALID_RESPONSE

    def test_response_content_without_text_raises_bedrock_error(
        self,
        translator: BedrockTranslator,
    ) -> None:
        """Content has entry but no 'text' key raises BedrockError."""
        response: dict[str, Any] = {
            "output": {"message": {"role": "assistant", "content": [{"type": "image"}]}}
        }
        with pytest.raises(BedrockError) as exc_info:
            translator._parse_response(response)

        assert exc_info.value.error_type == BedrockErrorType.INVALID_RESPONSE

    def test_response_empty_text_raises_bedrock_error(
        self,
        translator: BedrockTranslator,
        mock_bedrock_response: Any,
    ) -> None:
        """'text': '' (empty string, invalid JSON) raises BedrockError."""
        response = mock_bedrock_response("")
        with pytest.raises(BedrockError) as exc_info:
            translator._parse_response(response)

        assert exc_info.value.error_type == BedrockErrorType.INVALID_RESPONSE

    def test_response_whitespace_only_text_raises_bedrock_error(
        self,
        translator: BedrockTranslator,
        mock_bedrock_response: Any,
    ) -> None:
        """'text': '   ' (whitespace only) raises BedrockError."""
        response = mock_bedrock_response("   ")
        with pytest.raises(BedrockError) as exc_info:
            translator._parse_response(response)

        assert exc_info.value.error_type == BedrockErrorType.INVALID_RESPONSE


# ---------------------------------------------------------------------------
# TestTimeoutErrorHandling
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTimeoutErrorHandling:
    """Verify timeout errors are raised as BedrockError with TIMEOUT type."""

    def test_read_timeout_raises_bedrock_error_with_timeout_type(
        self,
        translator: BedrockTranslator,
        sample_intent: Intent,
    ) -> None:
        """ReadTimeoutError from botocore raises BedrockError with error_type=TIMEOUT."""
        timeout_error = ReadTimeoutError(
            endpoint_url="https://bedrock-runtime.us-east-1.amazonaws.com"
        )
        translator.client.converse = MagicMock(side_effect=timeout_error)

        with pytest.raises(BedrockError) as exc_info:
            translator.translate(sample_intent)

        assert exc_info.value.error_type == BedrockErrorType.TIMEOUT

    def test_read_timeout_user_message_mentions_timeout(
        self,
        translator: BedrockTranslator,
        sample_intent: Intent,
    ) -> None:
        """ReadTimeoutError produces a user_message that mentions timeout."""
        timeout_error = ReadTimeoutError(
            endpoint_url="https://bedrock-runtime.us-east-1.amazonaws.com"
        )
        translator.client.converse = MagicMock(side_effect=timeout_error)

        with pytest.raises(BedrockError) as exc_info:
            translator.translate(sample_intent)

        assert "timed out" in exc_info.value.user_message.lower()

    def test_read_timeout_provides_actionable_suggestion(
        self,
        translator: BedrockTranslator,
        sample_intent: Intent,
    ) -> None:
        """ReadTimeoutError provides a non-empty actionable suggestion."""
        timeout_error = ReadTimeoutError(
            endpoint_url="https://bedrock-runtime.us-east-1.amazonaws.com"
        )
        translator.client.converse = MagicMock(side_effect=timeout_error)

        with pytest.raises(BedrockError) as exc_info:
            translator.translate(sample_intent)

        assert exc_info.value.suggestion != ""
        assert len(exc_info.value.suggestion) > 10

    def test_read_timeout_is_retryable(
        self,
        translator: BedrockTranslator,
        sample_intent: Intent,
    ) -> None:
        """ReadTimeoutError produces a BedrockError that is retryable."""
        timeout_error = ReadTimeoutError(
            endpoint_url="https://bedrock-runtime.us-east-1.amazonaws.com"
        )
        translator.client.converse = MagicMock(side_effect=timeout_error)

        with pytest.raises(BedrockError) as exc_info:
            translator.translate(sample_intent)

        assert exc_info.value.is_retryable is True

    def test_model_timeout_client_error_raises_timeout(
        self,
        translator: BedrockTranslator,
        sample_intent: Intent,
    ) -> None:
        """ClientError with code ModelTimeoutException raises TIMEOUT type."""
        client_error = ClientError(
            {"Error": {"Code": "ModelTimeoutException", "Message": "Model timeout"}},
            "Converse",
        )
        translator.client.converse = MagicMock(side_effect=client_error)

        with pytest.raises(BedrockError) as exc_info:
            translator.translate(sample_intent)

        assert exc_info.value.error_type == BedrockErrorType.TIMEOUT
        assert exc_info.value.is_retryable is True


# ---------------------------------------------------------------------------
# TestThrottlingErrorHandling
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestThrottlingErrorHandling:
    """Verify throttling errors are raised as BedrockError with THROTTLING type."""

    def test_throttling_exception_raises_bedrock_error(
        self,
        translator: BedrockTranslator,
        sample_intent: Intent,
    ) -> None:
        """ClientError with ThrottlingException raises BedrockError THROTTLING."""
        client_error = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "Converse",
        )
        translator.client.converse = MagicMock(side_effect=client_error)

        with pytest.raises(BedrockError) as exc_info:
            translator.translate(sample_intent)

        assert exc_info.value.error_type == BedrockErrorType.THROTTLING

    def test_throttling_user_message_is_meaningful(
        self,
        translator: BedrockTranslator,
        sample_intent: Intent,
    ) -> None:
        """ThrottlingException produces meaningful user_message."""
        client_error = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "Converse",
        )
        translator.client.converse = MagicMock(side_effect=client_error)

        with pytest.raises(BedrockError) as exc_info:
            translator.translate(sample_intent)

        assert "throttl" in exc_info.value.user_message.lower()

    def test_throttling_provides_actionable_suggestion(
        self,
        translator: BedrockTranslator,
        sample_intent: Intent,
    ) -> None:
        """ThrottlingException provides actionable suggestion."""
        client_error = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "Converse",
        )
        translator.client.converse = MagicMock(side_effect=client_error)

        with pytest.raises(BedrockError) as exc_info:
            translator.translate(sample_intent)

        assert exc_info.value.suggestion != ""
        assert (
            "try" in exc_info.value.suggestion.lower()
            or "wait" in exc_info.value.suggestion.lower()
        )

    def test_throttling_is_retryable(
        self,
        translator: BedrockTranslator,
        sample_intent: Intent,
    ) -> None:
        """ThrottlingException produces a retryable BedrockError."""
        client_error = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "Converse",
        )
        translator.client.converse = MagicMock(side_effect=client_error)

        with pytest.raises(BedrockError) as exc_info:
            translator.translate(sample_intent)

        assert exc_info.value.is_retryable is True

    def test_service_quota_exceeded_maps_to_throttling(
        self,
        translator: BedrockTranslator,
        sample_intent: Intent,
    ) -> None:
        """ServiceQuotaExceededException maps to THROTTLING type."""
        client_error = ClientError(
            {"Error": {"Code": "ServiceQuotaExceededException", "Message": "Quota exceeded"}},
            "Converse",
        )
        translator.client.converse = MagicMock(side_effect=client_error)

        with pytest.raises(BedrockError) as exc_info:
            translator.translate(sample_intent)

        assert exc_info.value.error_type == BedrockErrorType.THROTTLING
        assert exc_info.value.is_retryable is True


# ---------------------------------------------------------------------------
# TestInvalidJsonErrorHandling
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestInvalidJsonErrorHandling:
    """Verify invalid JSON from model raises BedrockError with INVALID_RESPONSE."""

    def test_plain_text_response_raises_invalid_response(
        self,
        translator: BedrockTranslator,
        mock_bedrock_response: Any,
        sample_intent: Intent,
    ) -> None:
        """Non-JSON plain text raises BedrockError INVALID_RESPONSE."""
        response = mock_bedrock_response("I cannot help with that request.")
        translator.client.converse = MagicMock(return_value=response)

        with pytest.raises(BedrockError) as exc_info:
            translator.translate(sample_intent)

        assert exc_info.value.error_type == BedrockErrorType.INVALID_RESPONSE

    def test_invalid_json_user_message_mentions_json(
        self,
        translator: BedrockTranslator,
        mock_bedrock_response: Any,
        sample_intent: Intent,
    ) -> None:
        """Invalid JSON response produces user_message mentioning JSON."""
        response = mock_bedrock_response("Sorry, I don't understand.")
        translator.client.converse = MagicMock(return_value=response)

        with pytest.raises(BedrockError) as exc_info:
            translator.translate(sample_intent)

        assert "json" in exc_info.value.user_message.lower()

    def test_invalid_json_provides_suggestion(
        self,
        translator: BedrockTranslator,
        mock_bedrock_response: Any,
        sample_intent: Intent,
    ) -> None:
        """Invalid JSON provides actionable suggestion."""
        response = mock_bedrock_response("Here is your command: aws s3 ls")
        translator.client.converse = MagicMock(return_value=response)

        with pytest.raises(BedrockError) as exc_info:
            translator.translate(sample_intent)

        assert exc_info.value.suggestion != ""
        assert "rephras" in exc_info.value.suggestion.lower()

    def test_invalid_json_is_not_retryable(
        self,
        translator: BedrockTranslator,
        mock_bedrock_response: Any,
        sample_intent: Intent,
    ) -> None:
        """Invalid JSON response is NOT retryable."""
        response = mock_bedrock_response("Not JSON content")
        translator.client.converse = MagicMock(return_value=response)

        with pytest.raises(BedrockError) as exc_info:
            translator.translate(sample_intent)

        assert exc_info.value.is_retryable is False

    def test_html_response_raises_invalid_response(
        self,
        translator: BedrockTranslator,
        mock_bedrock_response: Any,
        sample_intent: Intent,
    ) -> None:
        """HTML-like text raises INVALID_RESPONSE."""
        response = mock_bedrock_response("<html><body>Error</body></html>")
        translator.client.converse = MagicMock(return_value=response)

        with pytest.raises(BedrockError) as exc_info:
            translator.translate(sample_intent)

        assert exc_info.value.error_type == BedrockErrorType.INVALID_RESPONSE


# ---------------------------------------------------------------------------
# TestTruncatedResponseErrorHandling
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTruncatedResponseErrorHandling:
    """Verify truncated/incomplete JSON raises BedrockError with INVALID_RESPONSE."""

    def test_truncated_json_object_raises_invalid_response(
        self,
        translator: BedrockTranslator,
        mock_bedrock_response: Any,
        sample_intent: Intent,
    ) -> None:
        """JSON cut off mid-object raises BedrockError INVALID_RESPONSE."""
        truncated = '{"command": "aws s3 ls", "explanation": "List buck'
        response = mock_bedrock_response(truncated)
        translator.client.converse = MagicMock(return_value=response)

        with pytest.raises(BedrockError) as exc_info:
            translator.translate(sample_intent)

        assert exc_info.value.error_type == BedrockErrorType.INVALID_RESPONSE

    def test_truncated_json_missing_closing_brace(
        self,
        translator: BedrockTranslator,
        mock_bedrock_response: Any,
        sample_intent: Intent,
    ) -> None:
        """JSON missing closing brace raises INVALID_RESPONSE."""
        truncated = '{"command": "aws s3 ls", "explanation": "List buckets"'
        response = mock_bedrock_response(truncated)
        translator.client.converse = MagicMock(return_value=response)

        with pytest.raises(BedrockError) as exc_info:
            translator.translate(sample_intent)

        assert exc_info.value.error_type == BedrockErrorType.INVALID_RESPONSE

    def test_truncated_json_in_markdown_fence_raises_invalid_response(
        self,
        translator: BedrockTranslator,
        mock_bedrock_response: Any,
        sample_intent: Intent,
    ) -> None:
        """Truncated JSON inside markdown fences raises INVALID_RESPONSE."""
        truncated = '```json\n{"command": "aws s3 ls", "explanat'
        response = mock_bedrock_response(truncated)
        translator.client.converse = MagicMock(return_value=response)

        with pytest.raises(BedrockError) as exc_info:
            translator.translate(sample_intent)

        assert exc_info.value.error_type == BedrockErrorType.INVALID_RESPONSE

    def test_truncated_json_user_message_mentions_invalid(
        self,
        translator: BedrockTranslator,
        mock_bedrock_response: Any,
        sample_intent: Intent,
    ) -> None:
        """Truncated JSON produces user_message about invalid JSON."""
        truncated = '{"command": "aws ec2 describe-instances", "risk_level":'
        response = mock_bedrock_response(truncated)
        translator.client.converse = MagicMock(return_value=response)

        with pytest.raises(BedrockError) as exc_info:
            translator.translate(sample_intent)

        assert "json" in exc_info.value.user_message.lower()

    def test_truncated_json_is_not_retryable(
        self,
        translator: BedrockTranslator,
        mock_bedrock_response: Any,
        sample_intent: Intent,
    ) -> None:
        """Truncated JSON is not retryable."""
        truncated = '{"command": "aws lambda list-functions'
        response = mock_bedrock_response(truncated)
        translator.client.converse = MagicMock(return_value=response)

        with pytest.raises(BedrockError) as exc_info:
            translator.translate(sample_intent)

        assert exc_info.value.is_retryable is False


# ---------------------------------------------------------------------------
# TestRetryBehavior
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRetryBehavior:
    """Verify retry logic with exponential backoff for retryable errors."""

    def test_throttling_retries_up_to_max_retries(
        self,
        sample_intent: Intent,
    ) -> None:
        """Throttling error retries exactly max_retries times before raising."""
        throttle_error = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "Converse",
        )

        with patch("boto3.client"):
            translator = BedrockTranslator(max_retries=3, base_delay=0.01)
            translator.client.converse = MagicMock(side_effect=throttle_error)

            with patch("time.sleep") as mock_sleep:
                with pytest.raises(BedrockError) as exc_info:
                    translator.translate(sample_intent)

        assert exc_info.value.error_type == BedrockErrorType.THROTTLING
        # Initial attempt + 3 retries = 4 total calls
        assert translator.client.converse.call_count == 4
        # sleep called 3 times (before each retry)
        assert mock_sleep.call_count == 3

    def test_timeout_retries_then_succeeds(
        self,
        sample_intent: Intent,
        mock_bedrock_response: Any,
    ) -> None:
        """ReadTimeoutError retries and succeeds on a later attempt."""
        timeout_error = ReadTimeoutError(
            endpoint_url="https://bedrock-runtime.us-east-1.amazonaws.com"
        )
        valid_json = json.dumps(
            {
                "command": "aws s3api list-buckets",
                "explanation": "Lista buckets",
                "detailed_explanation": "Detalle",
            }
        )
        success_response = mock_bedrock_response(valid_json)

        with patch("boto3.client"):
            translator = BedrockTranslator(max_retries=3, base_delay=0.01)
            translator.client.converse = MagicMock(
                side_effect=[timeout_error, timeout_error, success_response]
            )

            with patch("time.sleep"):
                result = translator.translate(sample_intent)

        assert result.command == "aws s3api list-buckets"
        assert translator.client.converse.call_count == 3

    def test_exponential_backoff_delays_grow(
        self,
        sample_intent: Intent,
    ) -> None:
        """Backoff delays increase exponentially: base * 2^attempt."""
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

        # With jitter=0: delays are base*2^0=1.0, base*2^1=2.0, base*2^2=4.0
        delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert delays == [1.0, 2.0, 4.0]

    def test_non_retryable_credentials_error_fails_immediately(
        self,
        sample_intent: Intent,
    ) -> None:
        """Credentials error does NOT retry — fails on first attempt."""
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
        assert translator.client.converse.call_count == 1
        mock_sleep.assert_not_called()

    def test_non_retryable_model_not_available_fails_immediately(
        self,
        sample_intent: Intent,
    ) -> None:
        """MODEL_NOT_AVAILABLE error does NOT retry."""
        not_found = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Not found"}},
            "Converse",
        )

        with patch("boto3.client"):
            translator = BedrockTranslator(max_retries=3, base_delay=0.01)
            translator.client.converse = MagicMock(side_effect=not_found)

            with patch("time.sleep") as mock_sleep:
                with pytest.raises(BedrockError) as exc_info:
                    translator.translate(sample_intent)

        assert exc_info.value.error_type == BedrockErrorType.MODEL_NOT_AVAILABLE
        assert translator.client.converse.call_count == 1
        mock_sleep.assert_not_called()

    def test_backoff_includes_jitter_component(
        self,
        sample_intent: Intent,
    ) -> None:
        """Backoff delay includes a jitter component from random.uniform."""
        throttle_error = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "Converse",
        )

        with patch("boto3.client"):
            translator = BedrockTranslator(max_retries=1, base_delay=1.0)
            translator.client.converse = MagicMock(side_effect=throttle_error)

            with patch("time.sleep") as mock_sleep:
                with patch("random.uniform", return_value=0.3):
                    with pytest.raises(BedrockError):
                        translator.translate(sample_intent)

        # base_delay * 2^0 + jitter = 1.0 + 0.3 = 1.3
        delay = mock_sleep.call_args_list[0].args[0]
        assert delay == pytest.approx(1.3)


# ---------------------------------------------------------------------------
# TestErrorClassification
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestErrorClassification:
    """Verify _map_client_error classifies AWS error codes and is_retryable."""

    @pytest.fixture
    def _translator(self) -> BedrockTranslator:
        """Provide a translator for direct _map_client_error calls."""
        with patch("boto3.client"):
            return BedrockTranslator(max_retries=0)

    def _make_client_error(self, code: str) -> ClientError:
        """Helper to create a ClientError with given code."""
        return ClientError(
            {"Error": {"Code": code, "Message": f"test {code}"}},
            "Converse",
        )

    def test_access_denied_maps_to_credentials(self, _translator: BedrockTranslator) -> None:
        """AccessDeniedException → CREDENTIALS."""
        exc = self._make_client_error("AccessDeniedException")
        err = _translator._map_client_error("AccessDeniedException", exc)
        assert err.error_type == BedrockErrorType.CREDENTIALS
        assert err.is_retryable is False

    def test_unrecognized_client_maps_to_credentials(self, _translator: BedrockTranslator) -> None:
        """UnrecognizedClientException → CREDENTIALS."""
        exc = self._make_client_error("UnrecognizedClientException")
        err = _translator._map_client_error("UnrecognizedClientException", exc)
        assert err.error_type == BedrockErrorType.CREDENTIALS
        assert err.is_retryable is False

    def test_expired_token_maps_to_credentials(self, _translator: BedrockTranslator) -> None:
        """ExpiredTokenException → CREDENTIALS."""
        exc = self._make_client_error("ExpiredTokenException")
        err = _translator._map_client_error("ExpiredTokenException", exc)
        assert err.error_type == BedrockErrorType.CREDENTIALS
        assert err.is_retryable is False

    def test_throttling_exception_maps_to_throttling(self, _translator: BedrockTranslator) -> None:
        """ThrottlingException → THROTTLING."""
        exc = self._make_client_error("ThrottlingException")
        err = _translator._map_client_error("ThrottlingException", exc)
        assert err.error_type == BedrockErrorType.THROTTLING
        assert err.is_retryable is True

    def test_service_quota_exceeded_maps_to_throttling(
        self, _translator: BedrockTranslator
    ) -> None:
        """ServiceQuotaExceededException → THROTTLING."""
        exc = self._make_client_error("ServiceQuotaExceededException")
        err = _translator._map_client_error("ServiceQuotaExceededException", exc)
        assert err.error_type == BedrockErrorType.THROTTLING
        assert err.is_retryable is True

    def test_model_timeout_maps_to_timeout(self, _translator: BedrockTranslator) -> None:
        """ModelTimeoutException → TIMEOUT."""
        exc = self._make_client_error("ModelTimeoutException")
        err = _translator._map_client_error("ModelTimeoutException", exc)
        assert err.error_type == BedrockErrorType.TIMEOUT
        assert err.is_retryable is True

    def test_model_not_ready_maps_to_model_not_available(
        self, _translator: BedrockTranslator
    ) -> None:
        """ModelNotReadyException → MODEL_NOT_AVAILABLE."""
        exc = self._make_client_error("ModelNotReadyException")
        err = _translator._map_client_error("ModelNotReadyException", exc)
        assert err.error_type == BedrockErrorType.MODEL_NOT_AVAILABLE
        assert err.is_retryable is False

    def test_resource_not_found_maps_to_model_not_available(
        self, _translator: BedrockTranslator
    ) -> None:
        """ResourceNotFoundException → MODEL_NOT_AVAILABLE."""
        exc = self._make_client_error("ResourceNotFoundException")
        err = _translator._map_client_error("ResourceNotFoundException", exc)
        assert err.error_type == BedrockErrorType.MODEL_NOT_AVAILABLE
        assert err.is_retryable is False

    def test_validation_exception_maps_to_invalid_response(
        self, _translator: BedrockTranslator
    ) -> None:
        """ValidationException → INVALID_RESPONSE."""
        exc = self._make_client_error("ValidationException")
        err = _translator._map_client_error("ValidationException", exc)
        assert err.error_type == BedrockErrorType.INVALID_RESPONSE
        assert err.is_retryable is False

    def test_unknown_error_code_maps_to_generic(self, _translator: BedrockTranslator) -> None:
        """Unknown error code → GENERIC."""
        exc = self._make_client_error("SomeNewUnknownException")
        err = _translator._map_client_error("SomeNewUnknownException", exc)
        assert err.error_type == BedrockErrorType.GENERIC
        assert err.is_retryable is False

    def test_all_mapped_errors_include_technical_detail(
        self, _translator: BedrockTranslator
    ) -> None:
        """All mapped errors include non-empty technical_detail."""
        codes = [
            "AccessDeniedException",
            "UnrecognizedClientException",
            "ExpiredTokenException",
            "ThrottlingException",
            "ServiceQuotaExceededException",
            "ModelTimeoutException",
            "ModelNotReadyException",
            "ResourceNotFoundException",
            "ValidationException",
        ]
        for code in codes:
            exc = self._make_client_error(code)
            err = _translator._map_client_error(code, exc)
            assert err.technical_detail != "", f"Missing technical_detail for {code}"

    def test_is_retryable_true_for_throttling(self) -> None:
        """BedrockError with THROTTLING is retryable."""
        err = BedrockError("Throttled", error_type=BedrockErrorType.THROTTLING)
        assert err.is_retryable is True

    def test_is_retryable_true_for_timeout(self) -> None:
        """BedrockError with TIMEOUT is retryable."""
        err = BedrockError("Timeout", error_type=BedrockErrorType.TIMEOUT)
        assert err.is_retryable is True

    def test_is_retryable_false_for_credentials(self) -> None:
        """BedrockError with CREDENTIALS is NOT retryable."""
        err = BedrockError("Denied", error_type=BedrockErrorType.CREDENTIALS)
        assert err.is_retryable is False

    def test_is_retryable_false_for_model_not_available(self) -> None:
        """BedrockError with MODEL_NOT_AVAILABLE is NOT retryable."""
        err = BedrockError("Not found", error_type=BedrockErrorType.MODEL_NOT_AVAILABLE)
        assert err.is_retryable is False

    def test_is_retryable_false_for_invalid_response(self) -> None:
        """BedrockError with INVALID_RESPONSE is NOT retryable."""
        err = BedrockError("Bad JSON", error_type=BedrockErrorType.INVALID_RESPONSE)
        assert err.is_retryable is False

    def test_is_retryable_false_for_generic(self) -> None:
        """BedrockError with GENERIC is NOT retryable."""
        err = BedrockError("Unknown", error_type=BedrockErrorType.GENERIC)
        assert err.is_retryable is False
