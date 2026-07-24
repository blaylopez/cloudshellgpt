"""Unit tests for IntentParser module."""

from __future__ import annotations

import pytest

from cloudshellgpt.intent import Intent, IntentParser


@pytest.fixture
def parser() -> IntentParser:
    """Create an IntentParser instance for testing."""
    return IntentParser()


class TestACBasicIntentParsing:
    """AC-1.1: Basic intent parsing."""

    def test_lista_los_buckets_de_s3(self, parser: IntentParser) -> None:
        """Given 'lista los buckets de S3', should return list/s3/confidence>0.85."""
        result = parser.parse("lista los buckets de S3")
        assert result.action == "list"
        assert result.service == "s3"
        assert result.confidence > 0.85
        assert result.clarification_needed is False

    def test_list_all_ec2_instances(self, parser: IntentParser) -> None:
        """English: list EC2 instances."""
        result = parser.parse("list all EC2 instances in us-east-1")
        assert result.action == "list"
        assert result.service == "ec2"
        assert result.confidence > 0.85

    def test_create_lambda_function(self, parser: IntentParser) -> None:
        """English: create Lambda function."""
        result = parser.parse("create a new Lambda function called my-handler")
        assert result.action == "create"
        assert result.service == "lambda"
        assert result.confidence > 0.85

    def test_delete_dynamodb_table(self, parser: IntentParser) -> None:
        """English: delete DynamoDB table."""
        result = parser.parse("delete the DynamoDB table named users")
        assert result.action == "delete"
        assert result.service == "dynamodb"
        assert result.confidence > 0.85


class TestACMultiLanguageSupport:
    """AC-1.2: Multi-language support."""

    @pytest.mark.parametrize(
        ("text", "expected_lang"),
        [
            ("por favor lista todos los buckets disponibles en mi cuenta de Amazon S3", "es"),
            ("list all S3 buckets in my AWS account please", "en"),
            ("listar todos os buckets do S3 na minha conta AWS", "pt"),
            ("afficher tous les buckets S3 dans mon compte AWS", "fr"),
            ("zeige alle S3 Buckets in meinem AWS Konto an", "de"),
        ],
    )
    def test_language_detection(
        self, parser: IntentParser, text: str, expected_lang: str
    ) -> None:
        """Verifies langdetect correctly identifies each language."""
        result = parser.parse(text)
        assert result.detected_language == expected_lang
        # All should detect s3 + list action regardless of language
        assert result.service == "s3"
        assert result.action == "list"
        assert result.confidence > 0.85

    @pytest.mark.parametrize(
        ("text", "expected_service", "expected_action"),
        [
            # PT
            ("criar uma nova instância EC2 do tipo t3.micro", "ec2", "create"),
            ("excluir o banco de dados RDS chamado producao", "rds", "delete"),
            # FR
            ("créer un nouveau bucket S3 pour les backups", "s3", "create"),
            ("supprimer la fonction Lambda obsolète", "lambda", "delete"),
            # DE
            ("erstelle eine neue EC2 Instanz in Frankfurt", "ec2", "create"),
            ("lösche die DynamoDB Tabelle mit alten Daten", "dynamodb", "delete"),
        ],
    )
    def test_multilang_service_action_detection(
        self, parser: IntentParser, text: str, expected_service: str, expected_action: str
    ) -> None:
        """Verifies service and action detection works across languages."""
        result = parser.parse(text)
        assert result.service == expected_service
        assert result.action == expected_action
        assert result.confidence > 0.85


class TestACAmbiguityHandling:
    """AC-1.3: Ambiguity handling."""

    def test_ambiguous_input_muestrame_las_cosas(self, parser: IntentParser) -> None:
        """Ambiguous 'muéstrame las cosas' → confidence < 0.7, clarification needed."""
        result = parser.parse("muéstrame las cosas")
        assert result.confidence < 0.7
        assert result.clarification_needed is True
        assert result.clarification_question is not None
        assert len(result.clarification_question) > 10

    def test_ambiguous_input_help_me(self, parser: IntentParser) -> None:
        """Completely ambiguous input with no service or action keywords."""
        result = parser.parse("ayudame con algo de la nube")
        assert result.confidence < 0.7
        assert result.clarification_needed is True

    def test_partial_ambiguity_action_only(self, parser: IntentParser) -> None:
        """When only action is detected, confidence is 0.5 (< 0.7)."""
        result = parser.parse("por favor lista todo lo que tengo disponible")
        assert result.action == "list"
        assert result.service == "unknown"
        assert result.confidence == 0.5
        assert result.clarification_needed is True


class TestEdgeCases:
    """Edge case handling for IntentParser."""

    def test_empty_input(self, parser: IntentParser) -> None:
        """Empty string returns confidence 0, clarification needed."""
        result = parser.parse("")
        assert result.confidence == 0.0
        assert result.clarification_needed is True
        assert result.action == "unknown"
        assert result.service == "unknown"

    def test_whitespace_only_input(self, parser: IntentParser) -> None:
        """Whitespace-only input returns confidence 0."""
        result = parser.parse("   \t\n  ")
        assert result.confidence == 0.0
        assert result.clarification_needed is True

    def test_very_long_input(self, parser: IntentParser) -> None:
        """Input > 500 chars is truncated but still processes."""
        long_text = "lista los buckets de S3 " * 100  # ~2400 chars
        result = parser.parse(long_text)
        assert result.raw_input == long_text  # raw_input preserves original
        assert result.service == "s3"
        assert result.action == "list"

    def test_unicode_emoji_input(self, parser: IntentParser) -> None:
        """Input with emojis doesn't crash."""
        result = parser.parse("🚀 lista los buckets de S3 📦")
        assert result.service == "s3"
        assert result.action == "list"

    def test_mixed_language_es_en(self, parser: IntentParser) -> None:
        """Mixed ES+EN input still detects service and action."""
        result = parser.parse("list los buckets de S3 in my account")
        assert result.service == "s3"
        assert result.action == "list"
        assert result.confidence > 0.85

    def test_region_passed_through(self, parser: IntentParser) -> None:
        """Region parameter is correctly stored in Intent."""
        result = parser.parse("list S3 buckets", region="eu-west-1")
        assert result.region == "eu-west-1"


class TestServiceDetection:
    """Verifies detection of all 10 supported AWS services."""

    @pytest.mark.parametrize(
        ("text", "expected_service"),
        [
            ("list the S3 buckets", "s3"),
            ("show EC2 instances", "ec2"),
            ("describe Lambda functions", "lambda"),
            ("list DynamoDB tables", "dynamodb"),
            ("show IAM users", "iam"),
            ("describe RDS databases", "rds"),
            ("list VPC subnets", "vpc"),
            ("show CloudFront distributions", "cloudfront"),
            ("list SNS topics", "sns"),
            ("show SQS queues", "sqs"),
        ],
    )
    def test_service_keyword_detection(
        self, parser: IntentParser, text: str, expected_service: str
    ) -> None:
        """Each service is correctly identified by its keywords."""
        result = parser.parse(text)
        assert result.service == expected_service


class TestActionDetection:
    """Verifies detection of all 6 action types."""

    @pytest.mark.parametrize(
        ("text", "expected_action"),
        [
            ("list S3 buckets", "list"),
            ("create a new EC2 instance", "create"),
            ("delete the Lambda function", "delete"),
            ("update the IAM policy", "update"),
            ("describe the RDS instance details", "describe"),
            ("invoke the Lambda function", "invoke"),
        ],
    )
    def test_action_keyword_detection(
        self, parser: IntentParser, text: str, expected_action: str
    ) -> None:
        """Each action type is correctly identified."""
        result = parser.parse(text)
        assert result.action == expected_action
