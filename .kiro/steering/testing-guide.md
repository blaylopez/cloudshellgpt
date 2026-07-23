---
inclusion: fileMatch
fileMatchPattern: "tests/**"
---

# Testing Guide — CloudShellGPT

## Test Structure

```
tests/
├── unit/                    # Fast, no network, mocked AWS
│   ├── test_intent.py       # IntentParser logic
│   ├── test_bedrock.py      # BedrockTranslator (mocked boto3/Bedrock calls)
│   ├── test_executor.py     # AWSExecutor (mocked subprocess)
│   ├── test_safety.py       # SafetyLayer risk classification
│   ├── test_formatter.py    # Output formatting
│   ├── test_audit.py        # AuditLogger file operations
│   ├── test_cost.py         # CostTracker
│   ├── test_learning.py     # LearningMode tips and suggestions
│   └── test_config.py       # ConfigManager
├── integration/             # Needs AWS (sandbox account)
│   ├── test_bedrock.py      # Real Bedrock calls
│   ├── test_mcp.py          # MCP server protocol
│   └── test_e2e.py          # Full flow end-to-end
└── eval/
    └── translation_eval.jsonl  # 100 test cases for accuracy
```

## Unit Testing Patterns

### Mocking AWS with moto

```python
import pytest
from moto import mock_aws

@mock_aws
def test_cost_explorer_returns_estimate():
    # moto automatically mocks boto3 calls
    ...
```

### Mocking subprocess for executor

```python
from unittest.mock import patch, MagicMock

def test_executor_runs_aws_command():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout='{"Buckets": []}',
            stderr="",
            returncode=0,
        )
        executor = AWSExecutor()
        result = executor.run("aws s3api list-buckets")
        assert result.exit_code == 0
```

### Testing IntentParser (no mocks needed)

```python
def test_parse_spanish_s3_list():
    parser = IntentParser()
    intent = parser.parse("lista los buckets de S3")
    assert intent.service == "s3"
    assert intent.action == "list"
    assert intent.detected_language == "es"
    assert intent.confidence >= 0.85
```

### Testing SafetyLayer

```python
from unittest.mock import patch, MagicMock

def test_destructive_command_upgrades_risk():
    from cloudshellgpt.bedrock_translator import Translation
    from cloudshellgpt.safety import SafetyLayer

    translation = Translation(
        command="aws s3 rm s3://prod --recursive",
        explanation="Delete all",
        detailed_explanation="...",
        risk_level="medium",
    )

    with patch("boto3.client") as mock_boto:
        safety = SafetyLayer()
    
    assert safety._is_destructive(translation.command) is True
```

## Fixtures

Use `conftest.py` for shared fixtures:

```python
# tests/conftest.py
import pytest
from pathlib import Path
from cloudshellgpt.config import ConfigManager

@pytest.fixture
def tmp_config(tmp_path):
    """Provides a temporary config file."""
    return ConfigManager(config_path=tmp_path / "config.yaml")

@pytest.fixture
def sample_intent():
    """Provides a sample Intent for testing."""
    from cloudshellgpt.intent import Intent
    return Intent(
        action="list",
        service="s3",
        confidence=0.9,
        raw_input="lista los buckets de S3",
        detected_language="es",
    )
```

## Running Tests

```bash
# All tests
pytest

# Unit tests only (fast)
pytest tests/unit/

# With coverage
pytest --cov=cloudshellgpt --cov-report=html

# Single file
pytest tests/unit/test_intent.py -v

# Match test name
pytest -k "test_parse_spanish"
```

## Integration Tests

Integration tests are marked and can be skipped in CI if no AWS credentials:

```python
import pytest

@pytest.mark.integration
def test_bedrock_translates_simple_intent():
    """Requires real AWS credentials with Bedrock access."""
    ...
```

Run with: `pytest -m integration`

## Eval Set

The eval set (`tests/eval/translation_eval.jsonl`) contains 100 test cases:

```jsonl
{"input": "lista los buckets de S3", "expected_service": "s3", "expected_action": "list", "language": "es"}
{"input": "create a t3.micro EC2 instance", "expected_service": "ec2", "expected_action": "create", "language": "en"}
```

Use it to measure translation accuracy:

```bash
# Requires custom pytest plugin defined in tests/eval/conftest.py
pytest tests/eval/ --eval-threshold=0.90
```

> Si el plugin no está instalado, pytest mostrará: `error: unrecognized arguments: --eval-threshold=0.90`. En ese caso, asegúrate de que `tests/eval/conftest.py` define el flag con `pytest_addoption`.

## Coverage Targets

- Overall: > 80%
- Critical paths (safety, executor): > 90%
- Formatter, learning: > 70%

## What NOT to test

- Don't test Pydantic model validation (Pydantic already tests itself)
- Don't test Rich rendering output pixel-by-pixel
- Don't test boto3 internals
- Don't write tests that hit real AWS in the unit test suite
