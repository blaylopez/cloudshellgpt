"""Tests for the Formatter module — Spanish error messages and output rendering."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest
import yaml
from rich.console import Console

from cloudshellgpt.executor import ExecutionResult
from cloudshellgpt.formatter import ERROR_MESSAGES, Formatter

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tty_formatter() -> Formatter:
    """Formatter with forced TTY mode for Rich rendering."""
    return Formatter(format_type="table", force_tty=True)


@pytest.fixture
def non_tty_formatter() -> Formatter:
    """Formatter with forced non-TTY mode for JSON output."""
    return Formatter(format_type="table", force_tty=False)


@pytest.fixture
def error_result_access_denied() -> ExecutionResult:
    """An execution result with AccessDenied error."""
    return ExecutionResult(
        command="aws s3 rm s3://prod-bucket --recursive",
        stdout="",
        stderr="An error occurred (AccessDenied) when calling the DeleteObject operation",
        exit_code=1,
        duration_ms=200,
        dry_run=False,
        error="AccessDenied: User is not authorized",
    )


@pytest.fixture
def error_result_invalid_region() -> ExecutionResult:
    """An execution result with region error."""
    return ExecutionResult(
        command="aws ec2 describe-instances --region invalid-region",
        stdout="",
        stderr="Could not connect to the endpoint URL",
        exit_code=1,
        duration_ms=100,
        dry_run=False,
        error="Could not connect to the endpoint URL",
    )


@pytest.fixture
def error_result_syntax() -> ExecutionResult:
    """An execution result with syntax error."""
    return ExecutionResult(
        command="aws s3api list-buckets --invalid-flag",
        stdout="",
        stderr="usage: aws s3api list-buckets [options]",
        exit_code=2,
        duration_ms=50,
        dry_run=False,
        error="InvalidParameterValue",
    )


@pytest.fixture
def success_result() -> ExecutionResult:
    """A successful execution result with JSON output."""
    return ExecutionResult(
        command="aws s3api list-buckets",
        stdout='{"Buckets": [{"Name": "my-bucket", "CreationDate": "2024-01-01"}]}',
        stderr="",
        exit_code=0,
        duration_ms=150,
        dry_run=False,
    )


# ---------------------------------------------------------------------------
# Tests: ERROR_MESSAGES dictionary completeness
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestErrorMessagesDictionary:
    """Verify the ERROR_MESSAGES dictionary has all required Spanish messages."""

    def test_contains_command_failed_message(self) -> None:
        """El mensaje de fallo incluye placeholder para exit_code."""
        assert "command_failed" in ERROR_MESSAGES
        assert "{exit_code}" in ERROR_MESSAGES["command_failed"]

    def test_contains_command_failed_detail(self) -> None:
        """El mensaje de detalle incluye placeholder para error."""
        assert "command_failed_detail" in ERROR_MESSAGES
        assert "{error}" in ERROR_MESSAGES["command_failed_detail"]

    def test_contains_stderr_output_label(self) -> None:
        """Existe etiqueta para salida de error."""
        assert "stderr_output" in ERROR_MESSAGES

    def test_contains_credential_suggestion(self) -> None:
        """Existe sugerencia para problemas de credenciales."""
        assert "suggestion_check_credentials" in ERROR_MESSAGES
        assert "credenciales" in ERROR_MESSAGES["suggestion_check_credentials"].lower()

    def test_contains_syntax_suggestion(self) -> None:
        """Existe sugerencia para problemas de sintaxis."""
        assert "suggestion_check_syntax" in ERROR_MESSAGES
        assert "sintaxis" in ERROR_MESSAGES["suggestion_check_syntax"].lower()

    def test_contains_region_suggestion(self) -> None:
        """Existe sugerencia para problemas de región."""
        assert "suggestion_check_region" in ERROR_MESSAGES
        assert "región" in ERROR_MESSAGES["suggestion_check_region"].lower()

    def test_contains_ui_labels(self) -> None:
        """Existen etiquetas de UI en español."""
        assert "dry_run_label" in ERROR_MESSAGES
        assert "executed_label" in ERROR_MESSAGES
        assert "duration_label" in ERROR_MESSAGES
        assert "command_label" in ERROR_MESSAGES
        assert "executing_label" in ERROR_MESSAGES

    def test_all_messages_are_in_spanish(self) -> None:
        """Todos los mensajes contienen palabras en español."""
        spanish_indicators = [
            "falló",
            "código",
            "salida",
            "Detalle",
            "Sugerencia",
            "Verifica",
            "Revisa",
            "Confirma",
            "Simulación",
            "Ejecutado",
            "Duración",
            "Comando",
            "Ejecutando",
        ]
        all_values = " ".join(ERROR_MESSAGES.values())
        matches = [word for word in spanish_indicators if word in all_values]
        # At least most Spanish indicators should be present
        assert len(matches) >= 8, f"Only found {len(matches)} Spanish indicators: {matches}"


# ---------------------------------------------------------------------------
# Tests: Error suggestion logic
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestErrorSuggestions:
    """Verify contextual error suggestions are returned correctly."""

    def test_credentials_error_returns_credentials_suggestion(
        self, tty_formatter: Formatter, error_result_access_denied: ExecutionResult
    ) -> None:
        """AccessDenied debe sugerir verificar credenciales."""
        suggestion = tty_formatter._get_error_suggestion(error_result_access_denied)
        assert suggestion == ERROR_MESSAGES["suggestion_check_credentials"]

    def test_region_error_returns_region_suggestion(
        self, tty_formatter: Formatter, error_result_invalid_region: ExecutionResult
    ) -> None:
        """Error de endpoint debe sugerir verificar región."""
        suggestion = tty_formatter._get_error_suggestion(error_result_invalid_region)
        assert suggestion == ERROR_MESSAGES["suggestion_check_region"]

    def test_syntax_error_returns_syntax_suggestion(
        self, tty_formatter: Formatter, error_result_syntax: ExecutionResult
    ) -> None:
        """Error de sintaxis debe sugerir revisar comando."""
        suggestion = tty_formatter._get_error_suggestion(error_result_syntax)
        assert suggestion == ERROR_MESSAGES["suggestion_check_syntax"]

    def test_generic_error_returns_empty_suggestion(self, tty_formatter: Formatter) -> None:
        """Error genérico no debe retornar sugerencia."""
        result = ExecutionResult(
            command="aws s3api list-buckets",
            stdout="",
            stderr="Unknown error occurred",
            exit_code=1,
            duration_ms=100,
            error="SomeRandomError",
        )
        suggestion = tty_formatter._get_error_suggestion(result)
        assert suggestion == ""

    def test_forbidden_keyword_triggers_credentials_suggestion(
        self, tty_formatter: Formatter
    ) -> None:
        """'Forbidden' en stderr también sugiere credenciales."""
        result = ExecutionResult(
            command="aws lambda invoke",
            stdout="",
            stderr="Forbidden: you don't have permission",
            exit_code=1,
            duration_ms=50,
            error="Forbidden",
        )
        suggestion = tty_formatter._get_error_suggestion(result)
        assert suggestion == ERROR_MESSAGES["suggestion_check_credentials"]


# ---------------------------------------------------------------------------
# Tests: Error rendering (TTY mode)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestErrorRendering:
    """Verify error output renders with Spanish messages in TTY mode."""

    def test_render_error_includes_exit_code_in_spanish(
        self, tty_formatter: Formatter, error_result_access_denied: ExecutionResult
    ) -> None:
        """El panel de error incluye el código de salida en español."""
        output = StringIO()
        tty_formatter.console = Console(file=output, force_terminal=True, width=120)
        tty_formatter._render_error(error_result_access_denied)
        rendered = output.getvalue()
        assert "falló" in rendered
        assert "1" in rendered  # exit code

    def test_render_error_includes_suggestion(
        self, tty_formatter: Formatter, error_result_access_denied: ExecutionResult
    ) -> None:
        """El panel de error incluye la sugerencia contextual."""
        output = StringIO()
        tty_formatter.console = Console(file=output, force_terminal=True, width=120)
        tty_formatter._render_error(error_result_access_denied)
        rendered = output.getvalue()
        assert "credenciales" in rendered.lower()

    def test_render_error_includes_stderr_content(
        self, tty_formatter: Formatter, error_result_access_denied: ExecutionResult
    ) -> None:
        """El panel de error muestra el contenido de stderr."""
        output = StringIO()
        tty_formatter.console = Console(file=output, force_terminal=True, width=120)
        tty_formatter._render_error(error_result_access_denied)
        rendered = output.getvalue()
        assert "AccessDenied" in rendered


# ---------------------------------------------------------------------------
# Tests: Non-TTY error rendering (plain JSON)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNonTTYErrorRendering:
    """Verify error output in non-TTY mode returns structured JSON."""

    def test_non_tty_error_outputs_json_with_error_field(
        self, non_tty_formatter: Formatter, error_result_access_denied: ExecutionResult
    ) -> None:
        """En non-TTY, errores se serializan como JSON con campo error."""
        import json

        with patch("builtins.print") as mock_print:
            non_tty_formatter.render(error_result_access_denied)
            printed = mock_print.call_args[0][0]
            data = json.loads(printed)
            assert data["exit_code"] == 1
            assert "error" in data
            assert "stderr" in data

    def test_non_tty_success_outputs_json_with_output_field(
        self, non_tty_formatter: Formatter, success_result: ExecutionResult
    ) -> None:
        """En non-TTY, éxito se serializa como JSON con campo output."""
        import json

        with patch("builtins.print") as mock_print:
            non_tty_formatter.render(success_result)
            printed = mock_print.call_args[0][0]
            data = json.loads(printed)
            assert data["exit_code"] == 0
            assert "output" in data
            assert data["output"]["Buckets"][0]["Name"] == "my-bucket"


# ---------------------------------------------------------------------------
# Tests: Formatter initialization and TTY detection
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFormatterInit:
    """Verify Formatter initialization and TTY detection."""

    def test_force_tty_true(self) -> None:
        """force_tty=True fuerza modo terminal."""
        fmt = Formatter(force_tty=True)
        assert fmt.is_tty is True

    def test_force_tty_false(self) -> None:
        """force_tty=False fuerza modo no-terminal."""
        fmt = Formatter(force_tty=False)
        assert fmt.is_tty is False

    def test_format_type_default(self) -> None:
        """Formato por defecto es table."""
        fmt = Formatter(force_tty=True)
        assert fmt.format_type == "table"

    def test_format_type_configurable(self) -> None:
        """Formato es configurable."""
        fmt = Formatter(format_type="yaml", force_tty=True)
        assert fmt.format_type == "yaml"


# ---------------------------------------------------------------------------
# Tests: Parametrized format rendering (5 formats)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFormatterFormats:
    """Verifica que los 5 formatos de salida producen output válido con el mismo input."""

    @pytest.fixture
    def list_of_dicts_result(self) -> ExecutionResult:
        """ExecutionResult exitoso con stdout JSON de lista de dicts."""
        return ExecutionResult(
            command="aws s3api list-buckets",
            stdout='[{"Name": "prod-bucket", "CreationDate": "2024-01-15"}, {"Name": "dev-bucket", "CreationDate": "2024-06-01"}]',
            stderr="",
            exit_code=0,
            duration_ms=250,
            dry_run=False,
        )

    @pytest.mark.parametrize("format_type", ["table", "json", "yaml", "csv", "raw"])
    def test_format_renders_without_exception(
        self, format_type: str, list_of_dicts_result: ExecutionResult
    ) -> None:
        """Cada formato renderiza sin lanzar excepciones."""
        output = StringIO()
        fmt = Formatter(format_type=format_type, force_tty=True)
        fmt.console = Console(file=output, force_terminal=True, width=120)
        fmt.render(list_of_dicts_result)
        # Si llegamos aquí, no hubo excepción

    @pytest.mark.parametrize("format_type", ["table", "json", "yaml", "csv", "raw"])
    def test_format_produces_non_empty_output(
        self, format_type: str, list_of_dicts_result: ExecutionResult
    ) -> None:
        """Cada formato produce output no vacío."""
        output = StringIO()
        fmt = Formatter(format_type=format_type, force_tty=True)
        fmt.console = Console(file=output, force_terminal=True, width=120)
        fmt.render(list_of_dicts_result)
        rendered = output.getvalue()
        assert rendered.strip(), f"El formato '{format_type}' produjo output vacío"

    def test_json_format_produces_valid_json(self, list_of_dicts_result: ExecutionResult) -> None:
        """El formato json produce JSON válido parseable."""
        import json as json_mod
        import re

        output = StringIO()
        fmt = Formatter(format_type="json", force_tty=True)
        fmt.console = Console(file=output, force_terminal=True, width=120, no_color=True)
        fmt.render(list_of_dicts_result)
        rendered = output.getvalue().strip()
        # Eliminar secuencias ANSI que Rich puede insertar con print_json
        clean = re.sub(r"\x1b\[[0-9;]*m", "", rendered)
        parsed = json_mod.loads(clean)
        assert isinstance(parsed, list)
        assert len(parsed) == 2

    def test_yaml_format_produces_valid_yaml(self, list_of_dicts_result: ExecutionResult) -> None:
        """El formato yaml produce YAML válido parseable."""
        output = StringIO()
        fmt = Formatter(format_type="yaml", force_tty=True)
        fmt.console = Console(file=output, force_terminal=True, width=120, no_color=True)
        fmt.render(list_of_dicts_result)
        rendered = output.getvalue().strip()
        parsed = yaml.safe_load(rendered)
        assert isinstance(parsed, list)
        assert len(parsed) == 2

    def test_csv_format_contains_header_and_data(
        self, list_of_dicts_result: ExecutionResult
    ) -> None:
        """El formato csv contiene fila de encabezado y datos."""
        output = StringIO()
        fmt = Formatter(format_type="csv", force_tty=True)
        fmt.console = Console(file=output, force_terminal=True, width=120, no_color=True)
        fmt.render(list_of_dicts_result)
        rendered = output.getvalue().strip()
        lines = rendered.splitlines()
        assert len(lines) >= 3, "CSV debe tener al menos header + 2 filas de datos"
        assert "Name" in lines[0]
        assert "CreationDate" in lines[0]
        assert "prod-bucket" in rendered
        assert "dev-bucket" in rendered

    def test_table_format_contains_data_values(self, list_of_dicts_result: ExecutionResult) -> None:
        """El formato table contiene los valores de datos."""
        output = StringIO()
        fmt = Formatter(format_type="table", force_tty=True)
        fmt.console = Console(file=output, force_terminal=True, width=120)
        fmt.render(list_of_dicts_result)
        rendered = output.getvalue()
        assert "prod-bucket" in rendered
        assert "dev-bucket" in rendered
        assert "2024-01-15" in rendered
        assert "2024-06-01" in rendered

    def test_raw_format_contains_raw_stdout(self, list_of_dicts_result: ExecutionResult) -> None:
        """El formato raw contiene el texto stdout tal cual."""
        output = StringIO()
        fmt = Formatter(format_type="raw", force_tty=True)
        fmt.console = Console(file=output, force_terminal=True, width=120, no_color=True)
        fmt.render(list_of_dicts_result)
        rendered = output.getvalue()
        assert "prod-bucket" in rendered
        assert "dev-bucket" in rendered


# ---------------------------------------------------------------------------
# Tests: TTY auto-detection (sys.stdout.isatty mock)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTTYAutoDetection:
    """Verifica la auto-detección de TTY via sys.stdout.isatty() sin force_tty."""

    @pytest.fixture
    def success_result(self) -> ExecutionResult:
        """ExecutionResult exitoso con JSON parseable."""
        return ExecutionResult(
            command="aws s3api list-buckets",
            stdout='[{"Name": "bucket-1", "CreationDate": "2024-01-01"}]',
            stderr="",
            exit_code=0,
            duration_ms=120,
            dry_run=False,
        )

    def test_isatty_true_detects_tty_mode(self) -> None:
        """Cuando sys.stdout.isatty() retorna True, Formatter detecta modo TTY."""
        with patch("sys.stdout.isatty", return_value=True):
            fmt = Formatter(format_type="table")
            assert fmt.is_tty is True

    def test_isatty_false_detects_non_tty_mode(self) -> None:
        """Cuando sys.stdout.isatty() retorna False, Formatter detecta modo non-TTY."""
        with patch("sys.stdout.isatty", return_value=False):
            fmt = Formatter(format_type="table")
            assert fmt.is_tty is False

    def test_non_tty_render_outputs_plain_json(self, success_result: ExecutionResult) -> None:
        """En non-TTY (auto-detectado), render() llama a _render_plain_json."""
        with patch("sys.stdout.isatty", return_value=False):
            fmt = Formatter(format_type="table")

        with patch.object(fmt, "_render_plain_json") as mock_plain:
            fmt.render(success_result)
            mock_plain.assert_called_once_with(success_result)

    def test_tty_render_uses_rich_formatting(self, success_result: ExecutionResult) -> None:
        """En TTY (auto-detectado), render() usa el renderer Rich correspondiente."""
        with patch("sys.stdout.isatty", return_value=True):
            fmt = Formatter(format_type="table")

        with patch.object(fmt, "_render_table") as mock_table:
            fmt.render(success_result)
            mock_table.assert_called_once_with(success_result)

    def test_console_force_terminal_true_when_tty(self) -> None:
        """Console se crea con force_terminal=True cuando se detecta TTY."""
        with patch("sys.stdout.isatty", return_value=True):
            with patch("cloudshellgpt.formatter.Console") as mock_console:
                Formatter(format_type="table")
                mock_console.assert_called_once_with(
                    force_terminal=True,
                    no_color=False,
                )

    def test_console_force_terminal_false_when_non_tty(self) -> None:
        """Console se crea con force_terminal=False cuando no hay TTY."""
        with patch("sys.stdout.isatty", return_value=False):
            with patch("cloudshellgpt.formatter.Console") as mock_console:
                Formatter(format_type="table")
                mock_console.assert_called_once_with(
                    force_terminal=False,
                    no_color=True,
                )

    def test_progress_spinner_noop_when_non_tty(self) -> None:
        """progress_spinner() es no-op cuando non-TTY (no muestra Rich Progress)."""
        with patch("sys.stdout.isatty", return_value=False):
            fmt = Formatter(format_type="table")

        with patch("cloudshellgpt.formatter.Progress") as mock_progress:
            with fmt.progress_spinner("Procesando..."):
                pass
            mock_progress.assert_not_called()

    def test_progress_spinner_shows_spinner_when_tty(self) -> None:
        """progress_spinner() muestra spinner Rich cuando TTY está activo."""
        with patch("sys.stdout.isatty", return_value=True):
            fmt = Formatter(format_type="table")

        # Redirigir output para evitar ruido en terminal de tests
        fmt.console = Console(file=StringIO(), force_terminal=True, width=120)

        with patch("cloudshellgpt.formatter.Progress") as mock_progress:
            mock_instance = mock_progress.return_value
            mock_instance.__enter__ = lambda self: self
            mock_instance.__exit__ = lambda self, *args: None
            mock_instance.add_task = lambda *args, **kwargs: None

            with fmt.progress_spinner("Ejecutando..."):
                pass

            mock_progress.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: Edge cases — output vacío, JSON inválido, lista vacía, truncamiento, unicode
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFormatterEdgeCases:
    """Verifica el comportamiento del Formatter ante edge cases."""

    def test_empty_stdout_renders_without_crashing(self) -> None:
        """Output vacío (stdout='') no debe lanzar excepción y produce output."""
        result = ExecutionResult(
            command="aws s3api list-buckets",
            stdout="",
            stderr="",
            exit_code=0,
            duration_ms=100,
            dry_run=False,
        )
        output = StringIO()
        fmt = Formatter(format_type="table", force_tty=True)
        fmt.console = Console(file=output, force_terminal=True, width=120)
        fmt.render(result)
        rendered = output.getvalue()
        # Debe producir algo (el panel fallback)
        assert rendered.strip(), "Output vacío debería generar un panel fallback"

    @pytest.mark.parametrize("format_type", ["table", "json", "yaml", "csv", "raw"])
    def test_empty_stdout_all_formats(self, format_type: str) -> None:
        """Output vacío renderiza sin error en todos los formatos."""
        result = ExecutionResult(
            command="aws ec2 describe-instances",
            stdout="",
            stderr="",
            exit_code=0,
            duration_ms=50,
            dry_run=False,
        )
        output = StringIO()
        fmt = Formatter(format_type=format_type, force_tty=True)
        fmt.console = Console(file=output, force_terminal=True, width=120)
        # No debe lanzar excepción
        fmt.render(result)

    def test_invalid_json_stdout_renders_without_crashing(self) -> None:
        """JSON inválido como stdout no debe lanzar excepción."""
        result = ExecutionResult(
            command="aws s3api list-buckets",
            stdout="not valid json {[}",
            stderr="",
            exit_code=0,
            duration_ms=100,
            dry_run=False,
        )
        output = StringIO()
        fmt = Formatter(format_type="table", force_tty=True)
        fmt.console = Console(file=output, force_terminal=True, width=120)
        fmt.render(result)
        rendered = output.getvalue()
        # El texto raw debe aparecer en la salida (fallback)
        assert "not valid json" in rendered

    @pytest.mark.parametrize("format_type", ["table", "json", "yaml", "csv", "raw"])
    def test_invalid_json_stdout_all_formats(self, format_type: str) -> None:
        """JSON inválido renderiza sin excepción en todos los formatos."""
        result = ExecutionResult(
            command="aws lambda list-functions",
            stdout="this is not valid json",
            stderr="",
            exit_code=0,
            duration_ms=75,
            dry_run=False,
        )
        output = StringIO()
        fmt = Formatter(format_type=format_type, force_tty=True)
        fmt.console = Console(file=output, force_terminal=True, width=120)
        fmt.render(result)
        rendered = output.getvalue()
        # En todos los formatos, el texto raw debe aparecer
        assert "this is not valid json" in rendered

    def test_empty_list_renders_without_crashing(self) -> None:
        """Lista vacía '[]' no debe lanzar excepción y se maneja gracefully."""
        result = ExecutionResult(
            command="aws s3api list-buckets",
            stdout="[]",
            stderr="",
            exit_code=0,
            duration_ms=100,
            dry_run=False,
        )
        output = StringIO()
        fmt = Formatter(format_type="table", force_tty=True)
        fmt.console = Console(file=output, force_terminal=True, width=120)
        fmt.render(result)
        rendered = output.getvalue()
        # Debe producir output (panel fallback con el texto "[]")
        assert rendered.strip(), "Lista vacía debería generar output (panel fallback)"

    @pytest.mark.parametrize("format_type", ["table", "json", "yaml", "csv", "raw"])
    def test_empty_list_all_formats(self, format_type: str) -> None:
        """Lista vacía renderiza sin excepción en todos los formatos."""
        result = ExecutionResult(
            command="aws ec2 describe-instances",
            stdout="[]",
            stderr="",
            exit_code=0,
            duration_ms=60,
            dry_run=False,
        )
        output = StringIO()
        fmt = Formatter(format_type=format_type, force_tty=True)
        fmt.console = Console(file=output, force_terminal=True, width=120)
        fmt.render(result)

    def test_list_over_50_items_truncates_table(self) -> None:
        """Lista con >50 items renderiza solo 50 filas y muestra mensaje de truncamiento."""
        import json

        items = [{"Id": str(i), "Name": f"item-{i}"} for i in range(65)]
        result = ExecutionResult(
            command="aws ec2 describe-instances",
            stdout=json.dumps(items),
            stderr="",
            exit_code=0,
            duration_ms=300,
            dry_run=False,
        )
        output = StringIO()
        fmt = Formatter(format_type="table", force_tty=True)
        fmt.console = Console(file=output, force_terminal=True, width=120)
        fmt.render(result)
        rendered = output.getvalue()

        # El mensaje de truncamiento debe aparecer con la cantidad restante
        assert "más" in rendered, "Debe indicar que hay más items truncados"
        assert "15" in rendered, "Debe indicar que faltan 15 items (65 - 50)"

        # Verificar que el item 49 (último mostrado) aparece pero no el 50+ directamente
        assert "item-0" in rendered, "El primer item debe estar presente"
        assert "item-49" in rendered, "El último item mostrado (índice 49) debe estar"

    def test_list_exactly_50_items_no_truncation_message(self) -> None:
        """Lista con exactamente 50 items NO muestra mensaje de truncamiento."""
        import json

        items = [{"Id": str(i), "Name": f"resource-{i}"} for i in range(50)]
        result = ExecutionResult(
            command="aws ec2 describe-instances",
            stdout=json.dumps(items),
            stderr="",
            exit_code=0,
            duration_ms=200,
            dry_run=False,
        )
        output = StringIO()
        fmt = Formatter(format_type="table", force_tty=True)
        fmt.console = Console(file=output, force_terminal=True, width=120)
        fmt.render(result)
        rendered = output.getvalue()

        # No debe haber mensaje de truncamiento
        assert "más" not in rendered

    def test_unicode_characters_render_without_crashing(self) -> None:
        """Caracteres unicode (emojis, acentos, CJK, árabe) renderizan sin error."""
        import json

        data = [
            {"Name": "日本語テスト", "Status": "アクティブ"},
            {"Name": "Ñoño con acentós", "Status": "válido"},
            {"Name": "مرحبا", "Status": "نشط"},
            {"Name": "🚀 Deployment", "Status": "✅ Success"},
            {"Name": "Ünïcödé", "Status": "résümé"},
        ]
        result = ExecutionResult(
            command="aws dynamodb scan",
            stdout=json.dumps(data, ensure_ascii=False),
            stderr="",
            exit_code=0,
            duration_ms=150,
            dry_run=False,
        )
        output = StringIO()
        fmt = Formatter(format_type="table", force_tty=True)
        fmt.console = Console(file=output, force_terminal=True, width=120)
        fmt.render(result)
        rendered = output.getvalue()

        # Los datos unicode deben preservarse en la salida
        assert "日本語テスト" in rendered
        assert "Ñoño con acentós" in rendered
        assert "مرحبا" in rendered
        assert "🚀 Deployment" in rendered

    @pytest.mark.parametrize("format_type", ["table", "json", "yaml", "raw"])
    def test_unicode_preserved_across_formats(self, format_type: str) -> None:
        """Caracteres unicode se preservan en múltiples formatos de salida."""
        import json

        data = [{"Nombre": "café ☕", "Región": "São Paulo"}]
        result = ExecutionResult(
            command="aws dynamodb scan",
            stdout=json.dumps(data, ensure_ascii=False),
            stderr="",
            exit_code=0,
            duration_ms=100,
            dry_run=False,
        )
        output = StringIO()
        fmt = Formatter(format_type=format_type, force_tty=True)
        fmt.console = Console(file=output, force_terminal=True, width=120)
        fmt.render(result)
        rendered = output.getvalue()

        assert "café" in rendered
        assert "São Paulo" in rendered


# ---------------------------------------------------------------------------
# Tests: Error rendering humanizado — exit_code != 0 muestra mensaje con stderr
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestErrorRenderingHumanized:
    """Verifica que exit_code != 0 muestra mensaje humanizado en español con stderr."""

    # ------------------------------------------------------------------
    # Parametrizado: múltiples exit codes producen mensaje de error apropiado
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "exit_code",
        [1, 2, 127, 130, 255],
        ids=["exit_1", "exit_2", "exit_127", "exit_130", "exit_255"],
    )
    def test_different_exit_codes_show_spanish_error_message(self, exit_code: int) -> None:
        """Diferentes exit codes producen mensaje humanizado en español con el código."""
        result = ExecutionResult(
            command="aws s3 ls",
            stdout="",
            stderr="some error occurred",
            exit_code=exit_code,
            duration_ms=100,
            error="GenericError",
        )
        output = StringIO()
        fmt = Formatter(format_type="table", force_tty=True)
        fmt.console = Console(file=output, force_terminal=True, width=120)
        fmt.render(result)
        rendered = output.getvalue()

        # Debe contener el mensaje en español con el exit code
        assert "falló" in rendered, "Debe mostrar 'falló' en español"
        assert str(exit_code) in rendered, f"Debe mostrar exit_code={exit_code}"

    # ------------------------------------------------------------------
    # stderr se muestra al usuario en modo TTY
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "stderr_content",
        [
            "An error occurred (NoSuchBucket) when calling GetObject",
            "Unable to locate credentials",
            "Connection timed out after 30000ms",
            "fatal error: An error occurred (403) when calling HeadObject",
        ],
        ids=["no_such_bucket", "no_credentials", "timeout", "forbidden_head"],
    )
    def test_stderr_content_displayed_in_tty_mode(self, stderr_content: str) -> None:
        """El contenido de stderr se muestra al usuario en modo TTY."""
        result = ExecutionResult(
            command="aws s3api get-object --bucket test --key file.txt",
            stdout="",
            stderr=stderr_content,
            exit_code=1,
            duration_ms=200,
            error=None,
        )
        output = StringIO()
        fmt = Formatter(format_type="table", force_tty=True)
        fmt.console = Console(file=output, force_terminal=True, width=120)
        fmt.render(result)
        rendered = output.getvalue()

        assert stderr_content.strip() in rendered, (
            f"stderr debe aparecer en la salida: '{stderr_content}'"
        )

    # ------------------------------------------------------------------
    # El comando que falló aparece en el panel de error
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "command",
        [
            "aws s3 rm s3://prod-bucket --recursive",
            "aws ec2 terminate-instances --instance-ids i-1234567890abcdef0",
            "aws lambda delete-function --function-name my-func",
        ],
        ids=["s3_rm", "ec2_terminate", "lambda_delete"],
    )
    def test_command_name_appears_in_error_output(self, command: str) -> None:
        """El nombre del comando que falló aparece en el panel de error."""
        result = ExecutionResult(
            command=command,
            stdout="",
            stderr="Access Denied",
            exit_code=1,
            duration_ms=150,
            error="AccessDenied",
        )
        output = StringIO()
        fmt = Formatter(format_type="table", force_tty=True)
        fmt.console = Console(file=output, force_terminal=True, width=120)
        fmt.render(result)
        rendered = output.getvalue()

        assert command in rendered, f"El comando '{command}' debe aparecer en la salida de error"

    # ------------------------------------------------------------------
    # Escenarios de error: solo stderr, solo error, ambos, ninguno
    # ------------------------------------------------------------------

    def test_only_stderr_shows_stderr_output_label(self) -> None:
        """Cuando solo hay stderr (sin campo error), se muestra la etiqueta de salida de error."""
        result = ExecutionResult(
            command="aws iam list-roles",
            stdout="",
            stderr="ExpiredTokenException: token expired",
            exit_code=1,
            duration_ms=80,
            error=None,
        )
        output = StringIO()
        fmt = Formatter(format_type="table", force_tty=True)
        fmt.console = Console(file=output, force_terminal=True, width=120)
        fmt.render(result)
        rendered = output.getvalue()

        assert "Salida de error" in rendered
        assert "ExpiredTokenException" in rendered

    def test_only_error_field_shows_detail(self) -> None:
        """Cuando solo hay campo error (sin stderr), se muestra el detalle."""
        result = ExecutionResult(
            command="aws cloudformation describe-stacks",
            stdout="",
            stderr="",
            exit_code=1,
            duration_ms=90,
            error="Stack my-stack does not exist",
        )
        output = StringIO()
        fmt = Formatter(format_type="table", force_tty=True)
        fmt.console = Console(file=output, force_terminal=True, width=120)
        fmt.render(result)
        rendered = output.getvalue()

        assert "Detalle" in rendered
        assert "Stack my-stack does not exist" in rendered

    def test_both_stderr_and_error_shows_both(self) -> None:
        """Cuando hay stderr y error, ambos aparecen en la salida."""
        result = ExecutionResult(
            command="aws dynamodb put-item --table-name prod-table",
            stdout="",
            stderr="ValidationException: One or more parameter values were invalid",
            exit_code=1,
            duration_ms=120,
            error="ValidationException",
        )
        output = StringIO()
        fmt = Formatter(format_type="table", force_tty=True)
        fmt.console = Console(file=output, force_terminal=True, width=120)
        fmt.render(result)
        rendered = output.getvalue()

        assert "Detalle" in rendered
        assert "ValidationException" in rendered
        assert "One or more parameter values were invalid" in rendered

    def test_neither_stderr_nor_error_shows_fallback_title(self) -> None:
        """Cuando no hay stderr ni error, se muestra al menos el título del fallo."""
        result = ExecutionResult(
            command="aws sqs receive-message --queue-url https://sqs.us-east-1.amazonaws.com/q",
            stdout="",
            stderr="",
            exit_code=1,
            duration_ms=60,
            error=None,
        )
        output = StringIO()
        fmt = Formatter(format_type="table", force_tty=True)
        fmt.console = Console(file=output, force_terminal=True, width=120)
        fmt.render(result)
        rendered = output.getvalue()

        # Al menos el título del fallo debe estar presente
        assert "falló" in rendered
        assert "1" in rendered  # exit code

    # ------------------------------------------------------------------
    # Sugerencias contextuales aparecen para keywords relevantes
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        ("stderr_content", "expected_suggestion_fragment"),
        [
            ("AccessDenied when calling PutObject", "credenciales"),
            ("unauthorized to perform iam:CreateRole", "credenciales"),
            ("Could not connect to the endpoint URL", "región"),
            ("InvalidRegion: us-invalid-1", "región"),
            ("usage: aws s3api list-buckets [options]", "sintaxis"),
            ("InvalidParameterValue for input", "sintaxis"),
        ],
        ids=[
            "access_denied_creds",
            "unauthorized_creds",
            "endpoint_region",
            "invalid_region",
            "usage_syntax",
            "invalid_param_syntax",
        ],
    )
    def test_contextual_suggestions_appear_for_relevant_keywords(
        self, stderr_content: str, expected_suggestion_fragment: str
    ) -> None:
        """Sugerencias contextuales aparecen cuando stderr contiene keywords relevantes."""
        result = ExecutionResult(
            command="aws s3api put-object --bucket test",
            stdout="",
            stderr=stderr_content,
            exit_code=1,
            duration_ms=100,
            error=None,
        )
        output = StringIO()
        fmt = Formatter(format_type="table", force_tty=True)
        fmt.console = Console(file=output, force_terminal=True, width=120)
        fmt.render(result)
        rendered = output.getvalue()

        assert expected_suggestion_fragment in rendered.lower(), (
            f"Debe sugerir sobre '{expected_suggestion_fragment}' para stderr: '{stderr_content}'"
        )
        # La sugerencia va con emoji 💡
        assert "💡" in rendered

    def test_no_suggestion_for_generic_error(self) -> None:
        """Errores genéricos no producen sugerencia contextual."""
        result = ExecutionResult(
            command="aws sts get-caller-identity",
            stdout="",
            stderr="Something went wrong unexpectedly",
            exit_code=1,
            duration_ms=50,
            error="UnknownError",
        )
        output = StringIO()
        fmt = Formatter(format_type="table", force_tty=True)
        fmt.console = Console(file=output, force_terminal=True, width=120)
        fmt.render(result)
        rendered = output.getvalue()

        assert "💡" not in rendered, "No debe haber sugerencia para errores genéricos"

    # ------------------------------------------------------------------
    # Non-TTY: errores producen JSON con stderr y error
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "exit_code",
        [1, 2, 127, 255],
        ids=["exit_1", "exit_2", "exit_127", "exit_255"],
    )
    def test_non_tty_error_outputs_json_with_stderr_field(self, exit_code: int) -> None:
        """En non-TTY, errores con diferentes exit codes producen JSON con stderr."""
        import json

        result = ExecutionResult(
            command="aws s3 ls",
            stdout="",
            stderr="An error occurred",
            exit_code=exit_code,
            duration_ms=100,
            error="SomeError",
        )
        fmt = Formatter(format_type="table", force_tty=False)

        with patch("builtins.print") as mock_print:
            fmt.render(result)
            printed = mock_print.call_args[0][0]
            data = json.loads(printed)

            assert data["exit_code"] == exit_code
            assert data["stderr"] == "An error occurred"
            assert data["error"] == "SomeError"
            assert data["command"] == "aws s3 ls"

    def test_non_tty_error_with_only_stderr(self) -> None:
        """En non-TTY, error sin campo error muestra solo stderr en JSON."""
        import json

        result = ExecutionResult(
            command="aws ec2 describe-instances",
            stdout="",
            stderr="timeout waiting for response",
            exit_code=1,
            duration_ms=30000,
            error=None,
        )
        fmt = Formatter(format_type="table", force_tty=False)

        with patch("builtins.print") as mock_print:
            fmt.render(result)
            printed = mock_print.call_args[0][0]
            data = json.loads(printed)

            assert data["exit_code"] == 1
            assert data["stderr"] == "timeout waiting for response"
            assert data["error"] is None

    def test_non_tty_error_with_only_error_field(self) -> None:
        """En non-TTY, error sin stderr muestra solo error field en JSON."""
        import json

        result = ExecutionResult(
            command="aws lambda invoke --function-name test",
            stdout="",
            stderr="",
            exit_code=1,
            duration_ms=200,
            error="ResourceNotFoundException",
        )
        fmt = Formatter(format_type="table", force_tty=False)

        with patch("builtins.print") as mock_print:
            fmt.render(result)
            printed = mock_print.call_args[0][0]
            data = json.loads(printed)

            assert data["exit_code"] == 1
            assert data["stderr"] == ""
            assert data["error"] == "ResourceNotFoundException"
