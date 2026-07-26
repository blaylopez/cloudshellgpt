"""Unit tests for LearningMode — TutorialRunner interactive tutorials."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cloudshellgpt.learning import (
    Explainer,
    FlagExplainer,
    PostExecutionTips,
    RelatedCommands,
    TutorialRunner,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALL_VALID_TOPICS = ["s3", "ec2", "lambda", "dynamodb", "iam", "vpc"]


# ---------------------------------------------------------------------------
# Tests: Valid topic shows tutorial steps
# ---------------------------------------------------------------------------


class TestTutorialRunnerValidTopic:
    """Verify TutorialRunner behaviour with valid topics."""

    @pytest.mark.unit
    @patch("cloudshellgpt.learning.Prompt")
    @patch("cloudshellgpt.learning.Console")
    def test_valid_topic_prints_header_panel(
        self, mock_console_cls: MagicMock, mock_prompt_cls: MagicMock
    ) -> None:
        """A valid topic prints a header Panel with topic title and step count."""
        mock_console = MagicMock()
        mock_console_cls.return_value = mock_console
        mock_prompt_cls.ask.return_value = ""

        runner = TutorialRunner("s3")
        runner.run()

        # Al menos se imprime el header + cada step
        steps = TutorialRunner.TUTORIALS["s3"]
        # header (1) + steps (N) = N+1 llamadas a print mínimo
        assert mock_console.print.call_count >= len(steps) + 1

        # Verificar que el primer print contiene el header con el topic
        first_call_args = mock_console.print.call_args_list[0]
        panel = first_call_args[0][0]
        # El Panel tiene el renderable con el texto del topic
        from rich.panel import Panel

        assert isinstance(panel, Panel)

    @pytest.mark.unit
    @patch("cloudshellgpt.learning.Prompt")
    @patch("cloudshellgpt.learning.Console")
    def test_valid_topic_prints_step_panels(
        self, mock_console_cls: MagicMock, mock_prompt_cls: MagicMock
    ) -> None:
        """Each step in a valid tutorial prints a Panel with step content."""
        mock_console = MagicMock()
        mock_console_cls.return_value = mock_console
        mock_prompt_cls.ask.return_value = ""

        runner = TutorialRunner("ec2")
        runner.run()

        steps = TutorialRunner.TUTORIALS["ec2"]
        # Prompt.ask se llama una vez por cada step
        assert mock_prompt_cls.ask.call_count == len(steps)

    @pytest.mark.unit
    @patch("cloudshellgpt.learning.Prompt")
    @patch("cloudshellgpt.learning.Console")
    def test_quit_action_stops_tutorial_early(
        self, mock_console_cls: MagicMock, mock_prompt_cls: MagicMock
    ) -> None:
        """Entering 'q' at a prompt stops iterating through steps."""
        mock_console = MagicMock()
        mock_console_cls.return_value = mock_console
        # Primera llamada retorna "q" para salir
        mock_prompt_cls.ask.return_value = "q"

        runner = TutorialRunner("s3")
        runner.run()

        # Solo se pidió una vez porque se detuvo con "q"
        assert mock_prompt_cls.ask.call_count == 1

    @pytest.mark.unit
    @patch("cloudshellgpt.learning.Prompt")
    @patch("cloudshellgpt.learning.Console")
    def test_run_action_prints_command(
        self, mock_console_cls: MagicMock, mock_prompt_cls: MagicMock
    ) -> None:
        """Entering 'r' prints the would-execute message for that step."""
        mock_console = MagicMock()
        mock_console_cls.return_value = mock_console
        # Retorna "r" en la primera y luego "q" para salir
        mock_prompt_cls.ask.side_effect = ["r", "q"]

        runner = TutorialRunner("s3")
        runner.run()

        # Buscar la llamada con "Would execute"
        print_calls = [str(call) for call in mock_console.print.call_args_list]
        would_execute_calls = [c for c in print_calls if "Would execute" in c]
        assert len(would_execute_calls) >= 1


# ---------------------------------------------------------------------------
# Tests: Invalid topic shows error
# ---------------------------------------------------------------------------


class TestTutorialRunnerInvalidTopic:
    """Verify TutorialRunner behaviour with invalid topics."""

    @pytest.mark.unit
    @patch("cloudshellgpt.learning.Prompt")
    @patch("cloudshellgpt.learning.Console")
    def test_invalid_topic_prints_error_message(
        self, mock_console_cls: MagicMock, mock_prompt_cls: MagicMock
    ) -> None:
        """An invalid topic prints an error with the unknown topic name."""
        mock_console = MagicMock()
        mock_console_cls.return_value = mock_console

        runner = TutorialRunner("nonexistent")
        runner.run()

        # Debe imprimir el mensaje de error con el topic
        calls_text = [str(call) for call in mock_console.print.call_args_list]
        error_calls = [c for c in calls_text if "Unknown topic: nonexistent" in c]
        assert len(error_calls) == 1

    @pytest.mark.unit
    @patch("cloudshellgpt.learning.Prompt")
    @patch("cloudshellgpt.learning.Console")
    def test_invalid_topic_prints_available_topics(
        self, mock_console_cls: MagicMock, mock_prompt_cls: MagicMock
    ) -> None:
        """An invalid topic prints the available topics list."""
        mock_console = MagicMock()
        mock_console_cls.return_value = mock_console

        runner = TutorialRunner("nonexistent")
        runner.run()

        calls_text = [str(call) for call in mock_console.print.call_args_list]
        available_calls = [c for c in calls_text if "Available:" in c]
        assert len(available_calls) == 1

        # Verifica que todos los topics válidos están listados
        available_str = available_calls[0]
        for topic in ALL_VALID_TOPICS:
            assert topic in available_str

    @pytest.mark.unit
    @patch("cloudshellgpt.learning.Prompt")
    @patch("cloudshellgpt.learning.Console")
    def test_invalid_topic_does_not_prompt_user(
        self, mock_console_cls: MagicMock, mock_prompt_cls: MagicMock
    ) -> None:
        """An invalid topic returns without prompting for user input."""
        mock_console = MagicMock()
        mock_console_cls.return_value = mock_console

        runner = TutorialRunner("nonexistent")
        runner.run()

        mock_prompt_cls.ask.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: All valid topics recognized (parametrized)
# ---------------------------------------------------------------------------


class TestTutorialRunnerAllTopics:
    """Verify all valid topics are recognized and have steps."""

    @pytest.mark.unit
    @pytest.mark.parametrize("topic", ALL_VALID_TOPICS)
    def test_topic_exists_in_tutorials(self, topic: str) -> None:
        """Each expected topic is a key in TUTORIALS."""
        assert topic in TutorialRunner.TUTORIALS

    @pytest.mark.unit
    @pytest.mark.parametrize("topic", ALL_VALID_TOPICS)
    def test_topic_has_at_least_one_step(self, topic: str) -> None:
        """Each valid topic has at least 1 step defined."""
        steps = TutorialRunner.TUTORIALS[topic]
        assert len(steps) >= 1

    @pytest.mark.unit
    @pytest.mark.parametrize("topic", ALL_VALID_TOPICS)
    @patch("cloudshellgpt.learning.Prompt")
    @patch("cloudshellgpt.learning.Console")
    def test_valid_topic_does_not_print_error(
        self,
        mock_console_cls: MagicMock,
        mock_prompt_cls: MagicMock,
        topic: str,
    ) -> None:
        """A valid topic does not trigger the error/available message."""
        mock_console = MagicMock()
        mock_console_cls.return_value = mock_console
        mock_prompt_cls.ask.return_value = ""

        runner = TutorialRunner(topic)
        runner.run()

        calls_text = [str(call) for call in mock_console.print.call_args_list]
        error_calls = [c for c in calls_text if "Unknown topic" in c]
        assert len(error_calls) == 0


# ---------------------------------------------------------------------------
# Tests: Explainer — mocked Bedrock converse
# ---------------------------------------------------------------------------


class TestExplainerSync:
    """Verify Explainer.explain_sync behaviour with mocked Bedrock client."""

    @pytest.mark.unit
    @patch("cloudshellgpt.learning.boto3")
    def test_explain_sync_returns_markdown_on_success(self, mock_boto3: MagicMock) -> None:
        """Happy path: converse returns proper response → returns markdown text."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        expected_markdown = (
            "## `aws s3 ls`\n\nLists all S3 buckets in the account.\n\n### Flags\n- None required\n"
        )
        mock_client.converse.return_value = {
            "output": {"message": {"content": [{"text": expected_markdown}]}}
        }

        explainer = Explainer(region="us-east-1")
        result = explainer.explain_sync("aws s3 ls")

        assert result == expected_markdown
        mock_client.converse.assert_called_once()

    @pytest.mark.unit
    @patch("cloudshellgpt.learning.boto3")
    def test_explain_sync_returns_error_message_on_generic_exception(
        self, mock_boto3: MagicMock
    ) -> None:
        """Generic Exception in converse → returns error string, no crash."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.converse.side_effect = Exception("Something went wrong")

        explainer = Explainer(region="us-east-1")
        result = explainer.explain_sync("aws s3 ls")

        assert "Error explaining command" in result
        assert "Something went wrong" in result

    @pytest.mark.unit
    @patch("cloudshellgpt.learning.boto3")
    def test_explain_sync_returns_error_message_on_timeout(self, mock_boto3: MagicMock) -> None:
        """TimeoutError in converse → returns error string, no crash."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.converse.side_effect = TimeoutError("Connection timed out")

        explainer = Explainer(region="us-east-1")
        result = explainer.explain_sync("aws ec2 describe-instances")

        assert "Error explaining command" in result
        assert "Connection timed out" in result

    @pytest.mark.unit
    @patch("cloudshellgpt.learning.boto3")
    def test_explain_sync_returns_error_message_on_client_error(
        self, mock_boto3: MagicMock
    ) -> None:
        """ClientError in converse → returns error string, no crash."""
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.converse.side_effect = ClientError(
            error_response={"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            operation_name="Converse",
        )

        explainer = Explainer(region="us-east-1")
        result = explainer.explain_sync("aws lambda list-functions")

        assert "Error explaining command" in result
        assert "ThrottlingException" in result or "Rate exceeded" in result

    @pytest.mark.unit
    @patch("cloudshellgpt.learning.boto3")
    def test_explain_sync_never_propagates_exception(self, mock_boto3: MagicMock) -> None:
        """No exception type propagates — method always returns a string."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.converse.side_effect = RuntimeError("Unexpected failure")

        explainer = Explainer(region="us-east-1")

        # No debe lanzar excepción, siempre retorna str
        result = explainer.explain_sync("aws iam list-users")
        assert isinstance(result, str)
        assert "Error explaining command" in result


# ---------------------------------------------------------------------------
# Tests: Explainer.explain_last — audit log interaction
# ---------------------------------------------------------------------------


class TestExplainerExplainLast:
    """Verify Explainer.explain_last behaviour with mocked AuditLogger."""

    @pytest.mark.unit
    @patch("cloudshellgpt.audit.AuditLogger")
    @patch("cloudshellgpt.learning.boto3")
    def test_explain_last_empty_audit_shows_warning(
        self, mock_boto3: MagicMock, mock_audit_cls: MagicMock
    ) -> None:
        """Empty audit log prints a yellow warning about no previous commands."""
        mock_audit_instance = MagicMock()
        mock_audit_cls.return_value = mock_audit_instance
        mock_audit_instance.tail.return_value = []

        explainer = Explainer(region="us-east-1")
        explainer.console = MagicMock()
        explainer.explain_last()

        # Verificar que se imprimió el warning
        calls_text = [str(call) for call in explainer.console.print.call_args_list]
        warning_calls = [c for c in calls_text if "No previous commands found" in c]
        assert len(warning_calls) == 1

    @pytest.mark.unit
    @patch("cloudshellgpt.audit.AuditLogger")
    @patch("cloudshellgpt.learning.boto3")
    def test_explain_last_empty_audit_does_not_call_explain(
        self, mock_boto3: MagicMock, mock_audit_cls: MagicMock
    ) -> None:
        """Empty audit log does NOT call self.explain()."""
        mock_audit_instance = MagicMock()
        mock_audit_cls.return_value = mock_audit_instance
        mock_audit_instance.tail.return_value = []

        explainer = Explainer(region="us-east-1")
        with patch.object(explainer, "explain") as mock_explain:
            explainer.explain_last()
            mock_explain.assert_not_called()

    @pytest.mark.unit
    @patch("cloudshellgpt.audit.AuditLogger")
    @patch("cloudshellgpt.learning.boto3")
    def test_explain_last_with_entries_calls_explain_with_last_command(
        self, mock_boto3: MagicMock, mock_audit_cls: MagicMock
    ) -> None:
        """Audit log with entries calls self.explain() with the last command string."""
        mock_audit_instance = MagicMock()
        mock_audit_cls.return_value = mock_audit_instance
        mock_audit_instance.tail.return_value = [{"command": "aws s3 ls"}]

        explainer = Explainer(region="us-east-1")
        with patch.object(explainer, "explain") as mock_explain:
            explainer.explain_last()
            mock_explain.assert_called_once_with("aws s3 ls")


# ---------------------------------------------------------------------------
# Tests: PostExecutionTips — rule-based tips
# ---------------------------------------------------------------------------


class TestPostExecutionTips:
    """Verify PostExecutionTips returns contextual tips."""

    @pytest.fixture
    def tips(self) -> PostExecutionTips:
        return PostExecutionTips()

    @pytest.mark.unit
    def test_s3_ls_returns_tip(self, tips: PostExecutionTips) -> None:
        """aws s3 ls returns a tip about --human-readable."""
        result = tips.get_tip("aws s3 ls")
        assert result is not None
        assert "--human-readable" in result

    @pytest.mark.unit
    def test_s3_cp_returns_tip(self, tips: PostExecutionTips) -> None:
        """aws s3 cp returns a tip about --recursive."""
        result = tips.get_tip("aws s3 cp file.txt s3://bucket/")
        assert result is not None
        assert "--recursive" in result

    @pytest.mark.unit
    def test_ec2_describe_instances_returns_tip(self, tips: PostExecutionTips) -> None:
        """ec2 describe-instances returns a tip about --query."""
        result = tips.get_tip("aws ec2 describe-instances --region us-east-1")
        assert result is not None
        assert "--query" in result

    @pytest.mark.unit
    def test_lambda_invoke_returns_tip(self, tips: PostExecutionTips) -> None:
        """lambda invoke returns a tip about --log-type."""
        result = tips.get_tip("aws lambda invoke --function-name f response.json")
        assert result is not None
        assert "--log-type" in result

    @pytest.mark.unit
    def test_unknown_command_returns_none(self, tips: PostExecutionTips) -> None:
        """Unknown commands return None."""
        result = tips.get_tip("aws route53 list-hosted-zones")
        assert result is None

    @pytest.mark.unit
    def test_non_aws_command_returns_none(self, tips: PostExecutionTips) -> None:
        """Non-AWS commands return None."""
        result = tips.get_tip("ls -la")
        assert result is None

    @pytest.mark.unit
    def test_command_with_only_service_returns_none(self, tips: PostExecutionTips) -> None:
        """Single-word commands without action return None."""
        result = tips.get_tip("aws")
        assert result is None


# ---------------------------------------------------------------------------
# Tests: FlagExplainer — rule-based flag explanations
# ---------------------------------------------------------------------------


class TestFlagExplainer:
    """Verify FlagExplainer explains flags in commands."""

    @pytest.fixture
    def explainer(self) -> FlagExplainer:
        return FlagExplainer()

    @pytest.mark.unit
    def test_explains_output_flag(self, explainer: FlagExplainer) -> None:
        """Recognizes and explains --output flag."""
        result = explainer.explain_flags("aws s3 ls --output json")
        assert len(result) == 1
        assert result[0].flag == "--output"
        assert "format" in result[0].explanation.lower()

    @pytest.mark.unit
    def test_explains_multiple_flags(self, explainer: FlagExplainer) -> None:
        """Explains multiple flags in a single command."""
        result = explainer.explain_flags(
            "aws ec2 describe-instances --output table --query 'Reservations[]' --region us-west-2"
        )
        flags = [r.flag for r in result]
        assert "--output" in flags
        assert "--query" in flags
        assert "--region" in flags

    @pytest.mark.unit
    def test_skips_unknown_flags(self, explainer: FlagExplainer) -> None:
        """Flags not in FLAG_DEFINITIONS are skipped."""
        result = explainer.explain_flags("aws s3 ls --unknown-flag value")
        assert len(result) == 0

    @pytest.mark.unit
    def test_deduplicates_flags(self, explainer: FlagExplainer) -> None:
        """Duplicate flags are only explained once."""
        result = explainer.explain_flags("aws s3 cp --recursive src/ --recursive dst/")
        recursive_flags = [r for r in result if r.flag == "--recursive"]
        assert len(recursive_flags) == 1

    @pytest.mark.unit
    def test_no_flags_returns_empty(self, explainer: FlagExplainer) -> None:
        """Commands without flags return empty list."""
        result = explainer.explain_flags("aws s3 ls")
        assert result == []


# ---------------------------------------------------------------------------
# Tests: RelatedCommands — rule-based command suggestions
# ---------------------------------------------------------------------------


class TestRelatedCommands:
    """Verify RelatedCommands suggests relevant follow-up commands."""

    @pytest.fixture
    def related(self) -> RelatedCommands:
        return RelatedCommands()

    @pytest.mark.unit
    def test_s3_ls_suggests_cp_and_sync(self, related: RelatedCommands) -> None:
        """aws s3 ls suggests s3 cp and s3 sync."""
        suggestions = related.suggest("aws s3 ls s3://bucket/")
        commands = [s.command for s in suggestions]
        assert "aws s3 cp" in commands
        assert "aws s3 sync" in commands

    @pytest.mark.unit
    def test_ec2_describe_instances_suggests_start_stop(self, related: RelatedCommands) -> None:
        """ec2 describe-instances suggests start and stop."""
        suggestions = related.suggest("aws ec2 describe-instances --region us-east-1")
        commands = [s.command for s in suggestions]
        assert "aws ec2 start-instances" in commands
        assert "aws ec2 stop-instances" in commands

    @pytest.mark.unit
    def test_unknown_command_returns_empty(self, related: RelatedCommands) -> None:
        """Unknown commands return empty suggestions list."""
        suggestions = related.suggest("aws route53 list-hosted-zones")
        assert suggestions == []

    @pytest.mark.unit
    def test_non_aws_command_returns_empty(self, related: RelatedCommands) -> None:
        """Non-AWS commands return empty list."""
        suggestions = related.suggest("ls -la")
        assert suggestions == []

    @pytest.mark.unit
    def test_suggestions_have_descriptions(self, related: RelatedCommands) -> None:
        """Each suggestion has a non-empty description."""
        suggestions = related.suggest("aws s3 ls")
        assert len(suggestions) > 0
        for s in suggestions:
            assert s.description
            assert len(s.description) > 0
