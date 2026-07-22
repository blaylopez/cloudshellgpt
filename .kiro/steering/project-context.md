# Project Context — CloudShellGPT

## Identity

- **Name:** CloudShellGPT
- **CLI command:** `csgpt`
- **Tagline:** AWS CLI que habla tu idioma
- **Category:** HACKATHONKIRO — Agentes especializados / Productividad para developers
- **License:** Apache 2.0
- **Python:** 3.12+
- **Build system:** hatchling

## Architecture Summary

```
User input (natural language, any language)
    │
    ▼
IntentParser (intent.py)
    → Detects language, service, action
    → Returns Intent (Pydantic model)
    │
    ▼
BedrockTranslator (bedrock_translator.py)
    → Sends Intent to Claude 3.5 Sonnet
    → Returns Translation (command + metadata)
    │
    ▼
SafetyLayer (safety.py)
    → Evaluates risk level
    → Checks for destructive patterns
    → Estimates cost
    → Returns SafetyCheck
    │
    ▼
AWSExecutor (executor.py)
    → Runs the AWS CLI command via subprocess
    → Enforces timeout + security
    → Returns ExecutionResult
    │
    ▼
Formatter (formatter.py)
    → Renders output as table/json/yaml/csv
    │
    ▼
AuditLogger (audit.py)
    → Logs everything to ~/.csgpt/audit.log
```

## Key Data Models (contracts between modules)

- `Intent` — output of IntentParser, input to BedrockTranslator
- `Translation` — output of BedrockTranslator, input to SafetyLayer
- `SafetyCheck` — output of SafetyLayer, used by CLI for confirmation flow
- `ExecutionResult` — output of AWSExecutor, input to Formatter
- `Config` — user settings loaded from ~/.csgpt/config.yaml

These models are the API contracts. Changing their fields requires coordinating with whoever owns the consuming module.

## MCP Server

CloudShellGPT doubles as an MCP server with 4 tools:
- `aws_translate` — natural language → AWS CLI command
- `aws_execute` — run a command with optional dry-run
- `aws_cost_preview` — estimate cost before executing
- `aws_explain` — detailed explanation of a command

Runs via `csgpt mcp serve` on stdio transport.

## Configuration

User config at `~/.csgpt/config.yaml`:
- `region` (default: us-east-1)
- `language` (default: auto)
- `default_output` (default: table)
- `bedrock_model` (default: Claude 3.5 Sonnet)
- `require_confirmation_for` (default: [high, critical])
- `enable_cost_preview` (default: true)
- `enable_learning_mode` (default: true)
- `max_cost_alert` (default: $100)

## What's NOT implemented yet

When working on this project, be aware these are documented but not yet built:
- Tests (entire `tests/` directory)
- Lambda handler (`src/cloudshellgpt/lambda_translator/`)
- CI/CD pipeline (`.github/workflows/`)
- Streaming output in executor
- Local translation cache (SQLite)
- Context preservation between commands
- PII detection with Comprehend
- Boto3 fallback in executor
- Quiz mode in learning
- `docs/` directory

## Dependencies That Matter

| Package | Why |
|---------|-----|
| typer | CLI framework (commands, flags, help text) |
| rich | Terminal UI (tables, panels, colors, progress) |
| boto3 | AWS SDK (Bedrock, Cost Explorer) |
| pydantic | Data validation and models |
| mcp | Model Context Protocol server |
| langdetect | Language detection for multi-lang support |
| pyyaml | Config file format |
| moto | AWS mocking for tests |

## Development Commands

```bash
# Install all deps (including dev)
uv sync --all-extras

# Run CLI
csgpt --help
csgpt "lista los buckets de S3"

# Run tests
pytest

# Lint + format
ruff check . --fix
ruff format .

# Type check
mypy src/

# CDK deploy (dev)
cd infrastructure && cdk deploy -c environment=dev
```
