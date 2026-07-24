---
inclusion: fileMatch
fileMatchPattern: "tests/**/*.py"
---

# Skill: Pytest Unit Creator

Genera tests unitarios para módulos de CloudShellGPT siguiendo las convenciones del testing-guide.

## Cuándo usar

Cuando necesites crear tests para un módulo en `src/cloudshellgpt/`. Cada módulo debe tener su test mirror en `tests/unit/`.

## Mapeo de archivos

| Módulo | Test |
|--------|------|
| `src/cloudshellgpt/intent.py` | `tests/unit/test_intent.py` |
| `src/cloudshellgpt/bedrock_translator.py` | `tests/unit/test_bedrock.py` |
| `src/cloudshellgpt/safety.py` | `tests/unit/test_safety.py` |
| `src/cloudshellgpt/cost.py` | `tests/unit/test_cost.py` |
| `src/cloudshellgpt/executor.py` | `tests/unit/test_executor.py` |
| `src/cloudshellgpt/formatter.py` | `tests/unit/test_formatter.py` |
| `src/cloudshellgpt/audit.py` | `tests/unit/test_audit.py` |
| `src/cloudshellgpt/learning.py` | `tests/unit/test_learning.py` |
| `src/cloudshellgpt/config.py` | `tests/unit/test_config.py` |

## Template base de archivo test

```python
"""Tests unitarios para <module_name>."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cloudshellgpt.<module> import <ClassUnderTest>


class TestClassName:
    """Tests para ClassName."""

    def test_action_condition_expected_result(self) -> None:
        """Descripción clara de qué verifica este test."""
        # Arrange
        input_data = "..."

        # Act
        result = function_under_test(input_data)

        # Assert
        assert result.field == expected_value

    def test_another_scenario(self) -> None:
        """Otro escenario."""
        ...
```

## Naming convention para tests

Formato: `test_<acción>_<condición>_<resultado_esperado>`

```python
# Buenos nombres:
def test_parse_spanish_list_intent_returns_high_confidence(): ...
def test_destructive_command_upgrades_risk_to_critical(): ...
def test_executor_rejects_pipe_in_command(): ...
def test_cost_explorer_failure_returns_unknown_status(): ...


# Malos nombres:
def test_1(): ...
def test_intent(): ...
def test_it_works(): ...
```

## Fixtures — usar conftest.py

Fixtures compartidas van en `tests/conftest.py`:

```python
"""Fixtures compartidas para tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from cloudshellgpt.config import Config
from cloudshellgpt.intent import Intent


@pytest.fixture
def tmp_config(tmp_path: Path) -> Config:
    """Provides a temporary config for testing."""
    from cloudshellgpt.config import ConfigManager

    return ConfigManager(config_path=tmp_path / "config.yaml")


@pytest.fixture
def sample_intent() -> Intent:
    """Provides a sample Intent for testing."""
    return Intent(
        action="list",
        service="s3",
        confidence=0.9,
        raw_input="lista los buckets de S3",
        detected_language="es",
    )


@pytest.fixture
def sample_translation() -> Translation:
    """Provides a sample Translation for testing."""
    from cloudshellgpt.bedrock_translator import Translation

    return Translation(
        command="aws s3api list-buckets --output json",
        explanation="Lista todos los buckets",
        detailed_explanation="Usa la API ListBuckets de S3",
        risk_level="low",
        estimated_cost="$0.00",
        requires_dry_run=False,
        affected_resources=["s3:*"],
        flags_used=["--output json"],
    )
```

## Mocking AWS — patrones

### Moto para servicios AWS completos

```python
import pytest
from moto import mock_aws


@mock_aws
def test_cost_explorer_returns_estimate() -> None:
    """Cost Explorer mock retorna estimación válida."""
    # moto intercepta boto3 calls automáticamente
    import boto3

    client = boto3.client("ce", region_name="us-east-1")
    # ... setup y assertions
```

### unittest.mock para subprocess (executor)

```python
from unittest.mock import MagicMock, patch


def test_executor_runs_aws_command() -> None:
    """Executor ejecuta comando y retorna resultado."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout='{"Buckets": []}',
            stderr="",
            returncode=0,
        )
        executor = AWSExecutor()
        result = executor.run("aws s3api list-buckets")

        assert result.exit_code == 0
        assert result.stdout == '{"Buckets": []}'
        mock_run.assert_called_once()
```

### Mock de Bedrock (translator)

```python
from unittest.mock import MagicMock, patch


def test_translator_calls_converse_api() -> None:
    """Translator usa Converse API, no invoke_model."""
    with patch("boto3.client") as mock_boto:
        mock_client = MagicMock()
        mock_boto.return_value = mock_client
        mock_client.converse.return_value = {
            "output": {
                "message": {"content": [{"text": '{"command": "aws s3 ls", "explanation": "..."}'}]}
            },
            "usage": {"inputTokens": 100, "outputTokens": 50},
        }

        translator = BedrockTranslator()
        result = translator.translate(sample_intent)

        mock_client.converse.assert_called_once()
        # Verificar que NO se usó invoke_model
        mock_client.invoke_model.assert_not_called()
```

## Patrones por módulo

### Tests de IntentParser (sin mocks — lógica pura)

```python
class TestIntentParser:
    """Tests para IntentParser — no requiere mocks AWS."""

    def test_parse_spanish_s3_list(self) -> None:
        parser = IntentParser()
        intent = parser.parse("lista los buckets de S3")
        assert intent.service == "s3"
        assert intent.action == "list"
        assert intent.detected_language == "es"
        assert intent.confidence >= 0.85

    def test_parse_english_ec2_create(self) -> None:
        parser = IntentParser()
        intent = parser.parse("create a t3.micro EC2 instance")
        assert intent.service == "ec2"
        assert intent.action == "create"
        assert intent.detected_language == "en"

    def test_ambiguous_input_low_confidence(self) -> None:
        parser = IntentParser()
        intent = parser.parse("muéstrame las cosas")
        assert intent.confidence < 0.7
```

### Tests de SafetyLayer (critical path — > 90% coverage)

```python
class TestSafetyLayer:
    """Tests para SafetyLayer — critical path."""

    def test_read_only_command_is_low(self) -> None:
        safety = SafetyLayer()
        check = safety.evaluate("aws s3api list-buckets")
        assert check.risk_level == "low"
        assert check.requires_confirmation is False

    def test_delete_command_is_high(self) -> None:
        safety = SafetyLayer()
        check = safety.evaluate("aws s3api delete-bucket --bucket prod")
        assert check.risk_level == "high"
        assert check.requires_confirmation is True

    def test_recursive_delete_is_critical(self) -> None:
        safety = SafetyLayer()
        check = safety.evaluate("aws s3 rm s3://prod --recursive")
        assert check.risk_level == "critical"
        assert check.requires_dry_run is True

    def test_never_downgrades_below_llm_risk(self) -> None:
        """Si LLM dice high, safety no puede poner medium."""
        safety = SafetyLayer()
        check = safety.evaluate("aws s3api list-buckets", llm_risk="high")
        assert check.risk_level in ("high", "critical")
```

### Tests de Executor (critical path — > 90% coverage)

```python
class TestAWSExecutor:
    """Tests para AWSExecutor — shell injection prevention."""

    @pytest.mark.parametrize("metachar", ["|", "&&", "||", ";", "`", "$(", ">", ">>", "<"])
    def test_rejects_shell_metacharacter(self, metachar: str) -> None:
        executor = AWSExecutor()
        with pytest.raises(ExecutorError, match="metacharacter"):
            executor.run(f"aws s3 ls {metachar} malicious")

    def test_accepts_stdin_dash_argument(self) -> None:
        """Argumento `-` es válido en posición de argumento."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            executor = AWSExecutor()
            result = executor.run("aws s3 cp - s3://bucket/file")
            assert result.exit_code == 0

    def test_rejects_non_aws_command(self) -> None:
        executor = AWSExecutor()
        with pytest.raises(ExecutorError):
            executor.run("rm -rf /")

    def test_timeout_kills_process(self) -> None:
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("aws", 30)):
            executor = AWSExecutor(timeout=30)
            with pytest.raises(ExecutorError, match="timeout"):
                executor.run("aws s3 sync s3://bucket .")
```

## Reglas obligatorias

1. **NUNCA** hit real AWS en unit tests — siempre moto o unittest.mock
2. **Type annotations** en todos los tests (→ None para test methods)
3. **Docstring** en cada test explicando qué verifica
4. **Arrange → Act → Assert** como estructura interna
5. **Un assert principal** por test (asserts auxiliares OK para setup validation)
6. **`@pytest.mark.parametrize`** para variaciones del mismo escenario
7. **`@pytest.mark.integration`** solo en `tests/integration/` (nunca en unit)
8. **Fixtures** para setup compartido, nunca setup en el test body repetido
9. **Nombres descriptivos** — el nombre del test debe explicar el escenario sin leer el body

## Ejecución

```bash
# Todos los unit tests
pytest tests/unit/ -v

# Un archivo específico
pytest tests/unit/test_safety.py -v

# Un test específico
pytest tests/unit/test_safety.py::TestSafetyLayer::test_recursive_delete_is_critical -v

# Con coverage
pytest --cov=cloudshellgpt --cov-report=html tests/unit/

# Solo tests que matchean nombre
pytest -k "test_parse_spanish" -v
```

## Coverage targets

| Módulo | Target |
|--------|--------|
| `safety.py` | > 90% |
| `executor.py` | > 90% |
| `intent.py` | > 80% |
| `bedrock_translator.py` | > 80% |
| `cost.py` | > 80% |
| `formatter.py` | > 70% |
| `learning.py` | > 70% |
| `audit.py` | > 80% |
| `config.py` | > 80% |
| **Global** | > 80% |
