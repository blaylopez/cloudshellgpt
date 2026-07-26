"""Tests parametrizados para los 4 MCP tools — verificar input/output contract.

Cada tool tiene un contrato de entrada/salida definido en la especificación MCP:
- aws_translate: input válido → JSON con 8 campos
- aws_execute: input válido → JSON con 6 campos
- aws_cost_preview: input válido → JSON con 4 campos
- aws_explain: input válido → string markdown
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from mcp.types import TextContent

from cloudshellgpt.mcp_server import call_tool, list_tools

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_json_response(result: list[TextContent]) -> dict[str, Any]:
    """Extrae y parsea JSON de un resultado MCP TextContent."""
    assert isinstance(result, list), f"Expected list, got {type(result)}"
    assert len(result) == 1, f"Expected 1 item, got {len(result)}"
    content = result[0]
    assert isinstance(content, TextContent)
    assert content.type == "text"
    data: dict[str, Any] = json.loads(content.text)
    return data


def _get_text_response(result: list[TextContent]) -> str:
    """Extrae texto plano de un resultado MCP TextContent."""
    assert isinstance(result, list), f"Expected list, got {type(result)}"
    assert len(result) == 1, f"Expected 1 item, got {len(result)}"
    content = result[0]
    assert isinstance(content, TextContent)
    assert content.type == "text"
    return content.text


# ---------------------------------------------------------------------------
# aws_translate — contrato: JSON con 8 campos
# ---------------------------------------------------------------------------

# Los 8 campos esperados en la respuesta de aws_translate
AWS_TRANSLATE_EXPECTED_FIELDS = [
    "command",
    "explanation",
    "detailed_explanation",
    "risk_level",
    "estimated_cost",
    "requires_dry_run",
    "affected_resources",
    "flags_used",
]

# Inputs variados para parametrizar aws_translate
_TRANSLATE_INPUTS: list[tuple[str, dict[str, Any]]] = [
    ("spanish_s3_list", {"intent": "lista los buckets de S3"}),
    ("english_ec2_describe", {"intent": "describe all EC2 instances"}),
    ("english_with_region", {"intent": "list lambda functions", "region": "eu-west-1"}),
    ("portuguese_dynamodb", {"intent": "criar uma tabela no DynamoDB"}),
]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("test_id", "args"),
    _TRANSLATE_INPUTS,
    ids=[t[0] for t in _TRANSLATE_INPUTS],
)
async def test_aws_translate_returns_json_with_8_fields(test_id: str, args: dict[str, Any]) -> None:
    """aws_translate retorna JSON válido con exactamente los 8 campos del contrato."""
    from cloudshellgpt.bedrock_translator import Translation
    from cloudshellgpt.intent import Intent

    mock_intent = Intent(
        action="list",
        service="s3",
        confidence=0.9,
        raw_input=args["intent"],
        detected_language="es",
        region=args.get("region"),
    )

    mock_translation = Translation(
        command="aws s3 ls",
        explanation="Lista todos los buckets de S3",
        detailed_explanation="Usa el servicio s3 para listar todos los buckets disponibles.",
        risk_level="low",
        estimated_cost="$0.00",
        requires_dry_run=False,
        affected_resources=[],
        flags_used={"--output": "table format"},
    )

    mock_parser = MagicMock()
    mock_parser.parse.return_value = mock_intent

    mock_translator = MagicMock()
    mock_translator.translate.return_value = mock_translation

    with (
        patch("cloudshellgpt.mcp_server.IntentParser", return_value=mock_parser),
        patch("cloudshellgpt.mcp_server.BedrockTranslator", return_value=mock_translator),
    ):
        result = await call_tool("aws_translate", args)

    data = _parse_json_response(result)

    # Verificar que tiene exactamente los 8 campos
    for field in AWS_TRANSLATE_EXPECTED_FIELDS:
        assert field in data, f"Campo faltante en respuesta: '{field}'"

    # Verificar tipos de cada campo
    assert isinstance(data["command"], str), "command debe ser str"
    assert isinstance(data["explanation"], str), "explanation debe ser str"
    assert isinstance(data["detailed_explanation"], str), "detailed_explanation debe ser str"
    assert isinstance(data["risk_level"], str), "risk_level debe ser str"
    assert isinstance(data["estimated_cost"], str), "estimated_cost debe ser str"
    assert isinstance(data["requires_dry_run"], bool), "requires_dry_run debe ser bool"
    assert isinstance(data["affected_resources"], list), "affected_resources debe ser list"
    assert isinstance(data["flags_used"], dict), "flags_used debe ser dict"


@pytest.mark.unit
async def test_aws_translate_fields_contain_expected_values() -> None:
    """aws_translate retorna valores coherentes con el input proporcionado."""
    from cloudshellgpt.bedrock_translator import Translation
    from cloudshellgpt.intent import Intent

    mock_intent = Intent(
        action="delete",
        service="s3",
        confidence=0.95,
        raw_input="borra todos los objetos del bucket logs",
        detected_language="es",
    )

    mock_translation = Translation(
        command="aws s3 rm s3://logs/ --recursive",
        explanation="Elimina todos los objetos del bucket logs",
        detailed_explanation="Operación irreversible que borra recursivamente.",
        risk_level="critical",
        estimated_cost="$0.00",
        requires_dry_run=True,
        affected_resources=["s3://logs/*"],
        flags_used={"--recursive": "Borra todos los objetos"},
    )

    mock_parser = MagicMock()
    mock_parser.parse.return_value = mock_intent

    mock_translator = MagicMock()
    mock_translator.translate.return_value = mock_translation

    with (
        patch("cloudshellgpt.mcp_server.IntentParser", return_value=mock_parser),
        patch("cloudshellgpt.mcp_server.BedrockTranslator", return_value=mock_translator),
    ):
        result = await call_tool(
            "aws_translate", {"intent": "borra todos los objetos del bucket logs"}
        )

    data = _parse_json_response(result)

    assert data["command"] == "aws s3 rm s3://logs/ --recursive"
    assert data["risk_level"] == "critical"
    assert data["requires_dry_run"] is True
    assert "s3://logs/*" in data["affected_resources"]
    assert "--recursive" in data["flags_used"]


# ---------------------------------------------------------------------------
# aws_execute — contrato: JSON con 6 campos
# ---------------------------------------------------------------------------

# Los 6 campos esperados en la respuesta de aws_execute
AWS_EXECUTE_EXPECTED_FIELDS = [
    "command",
    "exit_code",
    "stdout",
    "stderr",
    "duration_ms",
    "dry_run",
]

# Inputs variados para parametrizar aws_execute
_EXECUTE_INPUTS: list[tuple[str, dict[str, Any]]] = [
    ("simple_list", {"command": "aws s3 ls"}),
    ("with_flags", {"command": "aws ec2 describe-instances --output json"}),
    ("with_dry_run_false", {"command": "aws s3 ls", "dry_run": False}),
    (
        "with_dry_run_true",
        {"command": "aws ec2 run-instances --instance-type t2.micro", "dry_run": True},
    ),
]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("test_id", "args"),
    _EXECUTE_INPUTS,
    ids=[t[0] for t in _EXECUTE_INPUTS],
)
async def test_aws_execute_returns_json_with_6_fields(test_id: str, args: dict[str, Any]) -> None:
    """aws_execute retorna JSON válido con exactamente los 6 campos del contrato."""
    from cloudshellgpt.executor import ExecutionResult

    mock_result = ExecutionResult(
        command=args["command"],
        stdout='{"Buckets": []}',
        stderr="",
        exit_code=0,
        duration_ms=150,
        dry_run=args.get("dry_run", False),
    )

    mock_executor = MagicMock()
    mock_executor.run.return_value = mock_result

    with patch("cloudshellgpt.mcp_server.AWSExecutor", return_value=mock_executor):
        result = await call_tool("aws_execute", args)

    data = _parse_json_response(result)

    # Verificar que tiene exactamente los 6 campos
    for field in AWS_EXECUTE_EXPECTED_FIELDS:
        assert field in data, f"Campo faltante en respuesta: '{field}'"

    # Verificar tipos de cada campo
    assert isinstance(data["command"], str), "command debe ser str"
    assert isinstance(data["exit_code"], int), "exit_code debe ser int"
    assert isinstance(data["stdout"], str), "stdout debe ser str"
    assert isinstance(data["stderr"], str), "stderr debe ser str"
    assert isinstance(data["duration_ms"], int), "duration_ms debe ser int"
    assert isinstance(data["dry_run"], bool), "dry_run debe ser bool"


@pytest.mark.unit
async def test_aws_execute_error_still_returns_6_fields() -> None:
    """aws_execute retorna los 6 campos incluso cuando el comando falla."""
    from cloudshellgpt.executor import ExecutionResult

    mock_result = ExecutionResult(
        command="aws s3 ls s3://nonexistent",
        stdout="",
        stderr="An error occurred (NoSuchBucket) when calling ListObjectsV2",
        exit_code=1,
        duration_ms=200,
        dry_run=False,
    )

    mock_executor = MagicMock()
    mock_executor.run.return_value = mock_result

    with patch("cloudshellgpt.mcp_server.AWSExecutor", return_value=mock_executor):
        result = await call_tool("aws_execute", {"command": "aws s3 ls s3://nonexistent"})

    data = _parse_json_response(result)

    for field in AWS_EXECUTE_EXPECTED_FIELDS:
        assert field in data, f"Campo faltante en error response: '{field}'"

    assert data["exit_code"] == 1
    assert "NoSuchBucket" in data["stderr"]


# ---------------------------------------------------------------------------
# aws_cost_preview — contrato: JSON con 4 campos
# ---------------------------------------------------------------------------

# Los 4 campos esperados en la respuesta de aws_cost_preview
AWS_COST_PREVIEW_EXPECTED_FIELDS = [
    "command",
    "estimated_cost",
    "risk_level",
    "warnings",
]

# Inputs variados para parametrizar aws_cost_preview
_COST_PREVIEW_INPUTS: list[tuple[str, dict[str, Any]]] = [
    ("read_only_list", {"command": "aws s3 ls"}),
    ("create_instance", {"command": "aws ec2 run-instances --instance-type t3.large"}),
    ("delete_bucket", {"command": "aws s3api delete-bucket --bucket prod-data"}),
    ("lambda_invoke", {"command": "aws lambda invoke --function-name my-func out.json"}),
]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("test_id", "args"),
    _COST_PREVIEW_INPUTS,
    ids=[t[0] for t in _COST_PREVIEW_INPUTS],
)
async def test_aws_cost_preview_returns_json_with_4_fields(
    test_id: str, args: dict[str, Any]
) -> None:
    """aws_cost_preview retorna JSON válido con exactamente los 4 campos del contrato."""
    from cloudshellgpt.cost import CostEstimate
    from cloudshellgpt.safety import SafetyCheck

    mock_cost_estimate = CostEstimate(
        status="estimated",
        estimated_monthly_cost=45.0,
        currency="USD",
        cost_breakdown={"EC2 hourly": 45.0},
        warnings=[],
        confidence="medium",
        service="ec2",
        command=args["command"],
    )

    mock_safety_check = SafetyCheck(
        risk_level="medium",
        requires_confirmation=True,
        requires_dry_run=False,
        estimated_cost="$45.00/month",
        confirmation_prompt="Proceed?",
        warnings=[],
        affected_resources=[],
        reversible=True,
    )

    mock_cost_estimator = MagicMock()
    mock_cost_estimator.estimate.return_value = mock_cost_estimate

    mock_safety_layer = MagicMock()
    mock_safety_layer.assess.return_value = mock_safety_check

    with (
        patch("cloudshellgpt.cost.CostEstimator", return_value=mock_cost_estimator),
        patch("cloudshellgpt.mcp_server.SafetyLayer", return_value=mock_safety_layer),
    ):
        result = await call_tool("aws_cost_preview", args)

    data = _parse_json_response(result)

    # Verificar que tiene exactamente los 4 campos
    for field in AWS_COST_PREVIEW_EXPECTED_FIELDS:
        assert field in data, f"Campo faltante en respuesta: '{field}'"

    # Verificar tipos de cada campo
    assert isinstance(data["command"], str), "command debe ser str"
    assert isinstance(data["estimated_cost"], str), "estimated_cost debe ser str"
    assert isinstance(data["risk_level"], str), "risk_level debe ser str"
    assert isinstance(data["warnings"], list), "warnings debe ser list"


@pytest.mark.unit
async def test_aws_cost_preview_unknown_status_returns_unknown_cost() -> None:
    """aws_cost_preview retorna estimated_cost='unknown' cuando Cost Explorer falla."""
    from cloudshellgpt.cost import CostEstimate
    from cloudshellgpt.safety import SafetyCheck

    mock_cost_estimate = CostEstimate(
        status="unknown",
        estimated_monthly_cost=0.0,
        currency="USD",
        cost_breakdown={},
        warnings=["Cost estimation unavailable: API error"],
        confidence="low",
        service="ec2",
        command="aws ec2 run-instances",
    )

    mock_safety_check = SafetyCheck(
        risk_level="medium",
        requires_confirmation=True,
        requires_dry_run=False,
        estimated_cost="unknown",
        confirmation_prompt="Proceed?",
        warnings=[],
        affected_resources=[],
        reversible=True,
    )

    mock_cost_estimator = MagicMock()
    mock_cost_estimator.estimate.return_value = mock_cost_estimate

    mock_safety_layer = MagicMock()
    mock_safety_layer.assess.return_value = mock_safety_check

    with (
        patch("cloudshellgpt.cost.CostEstimator", return_value=mock_cost_estimator),
        patch("cloudshellgpt.mcp_server.SafetyLayer", return_value=mock_safety_layer),
    ):
        result = await call_tool("aws_cost_preview", {"command": "aws ec2 run-instances"})

    data = _parse_json_response(result)

    for field in AWS_COST_PREVIEW_EXPECTED_FIELDS:
        assert field in data
    assert data["estimated_cost"] == "unknown"


@pytest.mark.unit
async def test_aws_cost_preview_warnings_propagated() -> None:
    """aws_cost_preview propaga warnings de cost estimate y safety check."""
    from cloudshellgpt.cost import CostEstimate
    from cloudshellgpt.safety import SafetyCheck

    cost_warning = "Estimated cost $150.00/month exceeds max_cost_alert threshold ($100)"
    safety_warning = "Destructive operation detected"

    mock_cost_estimate = CostEstimate(
        status="estimated",
        estimated_monthly_cost=150.0,
        currency="USD",
        cost_breakdown={"EC2": 150.0},
        warnings=[cost_warning],
        confidence="medium",
        service="ec2",
        command="aws ec2 run-instances --instance-type r5.xlarge",
    )

    mock_safety_check = SafetyCheck(
        risk_level="high",
        requires_confirmation=True,
        requires_dry_run=True,
        estimated_cost="$150.00/month",
        confirmation_prompt="Are you sure?",
        warnings=[safety_warning],
        affected_resources=["EC2 instance"],
        reversible=True,
    )

    mock_cost_estimator = MagicMock()
    mock_cost_estimator.estimate.return_value = mock_cost_estimate

    mock_safety_layer = MagicMock()
    mock_safety_layer.assess.return_value = mock_safety_check

    with (
        patch("cloudshellgpt.cost.CostEstimator", return_value=mock_cost_estimator),
        patch("cloudshellgpt.mcp_server.SafetyLayer", return_value=mock_safety_layer),
    ):
        result = await call_tool(
            "aws_cost_preview",
            {"command": "aws ec2 run-instances --instance-type r5.xlarge"},
        )

    data = _parse_json_response(result)

    assert cost_warning in data["warnings"]
    assert safety_warning in data["warnings"]


# ---------------------------------------------------------------------------
# aws_explain — contrato: string markdown (no JSON)
# ---------------------------------------------------------------------------

# Inputs variados para parametrizar aws_explain
_EXPLAIN_INPUTS: list[tuple[str, dict[str, Any]]] = [
    ("simple_s3_ls", {"command": "aws s3 ls"}),
    ("ec2_describe", {"command": "aws ec2 describe-instances --output json"}),
    (
        "complex_command",
        {"command": "aws s3api list-objects-v2 --bucket prod --prefix logs/ --max-items 100"},
    ),
    ("destructive_command", {"command": "aws ec2 terminate-instances --instance-ids i-12345"}),
]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("test_id", "args"),
    _EXPLAIN_INPUTS,
    ids=[t[0] for t in _EXPLAIN_INPUTS],
)
async def test_aws_explain_returns_markdown_string(test_id: str, args: dict[str, Any]) -> None:
    """aws_explain retorna un string markdown (no JSON) con la explicación."""
    mock_explanation = (
        "## Command: `{cmd}`\n\n"
        "### What it does\n"
        "This command lists objects in an S3 bucket.\n\n"
        "### Flags\n"
        "- `--bucket`: The target bucket\n"
        "- `--prefix`: Filter by key prefix\n\n"
        "### Common pitfalls\n"
        "- Pagination may hide results\n\n"
        "### Docs\n"
        "[AWS S3 API Reference](https://docs.aws.amazon.com/s3/)\n"
    ).format(cmd=args["command"])

    mock_explainer = MagicMock()
    mock_explainer.explain_sync.return_value = mock_explanation

    with patch("cloudshellgpt.learning.Explainer", return_value=mock_explainer):
        result = await call_tool("aws_explain", args)

    text = _get_text_response(result)

    # aws_explain retorna texto plano (markdown), NO JSON
    assert isinstance(text, str), "Respuesta debe ser str"
    assert len(text) > 0, "Respuesta no debe estar vacía"

    # Verificar que NO es JSON (el contrato dice string markdown)
    with pytest.raises(json.JSONDecodeError):
        json.loads(text)

    # Verificar que contiene elementos de markdown
    assert "#" in text or "-" in text or "`" in text, (
        "Respuesta debe contener elementos de markdown"
    )


@pytest.mark.unit
async def test_aws_explain_passes_command_to_explainer() -> None:
    """aws_explain pasa el comando correctamente al Explainer."""
    command = "aws lambda list-functions --output table"
    mock_explainer = MagicMock()
    mock_explainer.explain_sync.return_value = "# Explanation\nThis lists Lambda functions."

    with patch("cloudshellgpt.learning.Explainer", return_value=mock_explainer):
        await call_tool("aws_explain", {"command": command})

    mock_explainer.explain_sync.assert_called_once_with(command)


@pytest.mark.unit
async def test_aws_explain_bedrock_error_returns_error_string() -> None:
    """aws_explain retorna un string de error (no crash) si Bedrock falla."""
    mock_explainer = MagicMock()
    mock_explainer.explain_sync.return_value = "Error explaining command: Connection timed out"

    with patch("cloudshellgpt.learning.Explainer", return_value=mock_explainer):
        result = await call_tool("aws_explain", {"command": "aws s3 ls"})

    text = _get_text_response(result)
    assert "Error" in text


# ---------------------------------------------------------------------------
# Validaciones cruzadas: todos los tools retornan list[TextContent]
# ---------------------------------------------------------------------------

_ALL_TOOLS_VALID_INPUTS: list[tuple[str, str, dict[str, Any]]] = [
    ("aws_translate", "translate_basic", {"intent": "list s3 buckets"}),
    ("aws_execute", "execute_basic", {"command": "aws s3 ls"}),
    ("aws_cost_preview", "cost_basic", {"command": "aws s3 ls"}),
    ("aws_explain", "explain_basic", {"command": "aws s3 ls"}),
]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("tool_name", "test_id", "args"),
    _ALL_TOOLS_VALID_INPUTS,
    ids=[f"{t[0]}_{t[1]}" for t in _ALL_TOOLS_VALID_INPUTS],
)
async def test_all_tools_return_list_text_content(
    tool_name: str, test_id: str, args: dict[str, Any]
) -> None:
    """Todos los tools retornan list[TextContent] con input válido."""
    from cloudshellgpt.bedrock_translator import Translation
    from cloudshellgpt.cost import CostEstimate
    from cloudshellgpt.executor import ExecutionResult
    from cloudshellgpt.intent import Intent
    from cloudshellgpt.safety import SafetyCheck

    # Setup mocks completos para todos los tools
    mock_intent = Intent(
        action="list",
        service="s3",
        confidence=0.9,
        raw_input="list s3 buckets",
        detected_language="en",
    )
    mock_translation = Translation(
        command="aws s3 ls",
        explanation="test",
        detailed_explanation="test",
        risk_level="low",
        estimated_cost="$0.00",
    )
    mock_exec_result = ExecutionResult(
        command="aws s3 ls",
        stdout="{}",
        stderr="",
        exit_code=0,
        duration_ms=100,
        dry_run=False,
    )
    mock_cost_estimate = CostEstimate(
        status="estimated",
        estimated_monthly_cost=0.0,
        currency="USD",
        warnings=[],
        confidence="high",
        service="s3",
        command="aws s3 ls",
    )
    mock_safety_check = SafetyCheck(
        risk_level="low",
        requires_confirmation=False,
        requires_dry_run=False,
        estimated_cost="$0.00",
        confirmation_prompt="",
        warnings=[],
    )

    mock_parser = MagicMock()
    mock_parser.parse.return_value = mock_intent
    mock_translator = MagicMock()
    mock_translator.translate.return_value = mock_translation
    mock_executor = MagicMock()
    mock_executor.run.return_value = mock_exec_result
    mock_cost_estimator = MagicMock()
    mock_cost_estimator.estimate.return_value = mock_cost_estimate
    mock_safety_layer = MagicMock()
    mock_safety_layer.assess.return_value = mock_safety_check
    mock_explainer = MagicMock()
    mock_explainer.explain_sync.return_value = "# Explanation\nCommand explanation."

    with (
        patch("cloudshellgpt.mcp_server.IntentParser", return_value=mock_parser),
        patch("cloudshellgpt.mcp_server.BedrockTranslator", return_value=mock_translator),
        patch("cloudshellgpt.mcp_server.AWSExecutor", return_value=mock_executor),
        patch("cloudshellgpt.cost.CostEstimator", return_value=mock_cost_estimator),
        patch("cloudshellgpt.mcp_server.SafetyLayer", return_value=mock_safety_layer),
        patch("cloudshellgpt.learning.Explainer", return_value=mock_explainer),
    ):
        result = await call_tool(tool_name, args)

    assert isinstance(result, list), f"Expected list, got {type(result)}"
    assert len(result) >= 1, "Expected at least 1 TextContent item"
    for item in result:
        assert isinstance(item, TextContent), f"Expected TextContent, got {type(item)}"
        assert item.type == "text"
        assert len(item.text) > 0, "TextContent.text must not be empty"


# ---------------------------------------------------------------------------
# aws_translate — campos faltantes/inválidos en input
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_aws_translate_input_missing_intent_empty_dict() -> None:
    """aws_translate con dict vacío ({}) usa default '' para intent y no crashea."""
    from cloudshellgpt.bedrock_translator import Translation
    from cloudshellgpt.intent import Intent

    # IntentParser recibe "" → devuelve intent de baja confianza
    mock_intent = Intent(
        action="unknown",
        service="unknown",
        confidence=0.0,
        raw_input="",
        detected_language="en",
        clarification_needed=True,
    )

    mock_translation = Translation(
        command="",
        explanation="No se pudo determinar la intención",
        detailed_explanation="El input está vacío.",
        risk_level="low",
        estimated_cost="$0.00",
        requires_dry_run=False,
        affected_resources=[],
        flags_used={},
    )

    mock_parser = MagicMock()
    mock_parser.parse.return_value = mock_intent

    mock_translator = MagicMock()
    mock_translator.translate.return_value = mock_translation

    with (
        patch("cloudshellgpt.mcp_server.IntentParser", return_value=mock_parser),
        patch("cloudshellgpt.mcp_server.BedrockTranslator", return_value=mock_translator),
    ):
        result = await call_tool("aws_translate", {})

    data = _parse_json_response(result)

    # Debe retornar los 8 campos del contrato
    for field in AWS_TRANSLATE_EXPECTED_FIELDS:
        assert field in data, f"Campo faltante: '{field}'"

    # Verificar que IntentParser recibió string vacío
    mock_parser.parse.assert_called_once_with("", region=None)


@pytest.mark.unit
async def test_aws_translate_input_intent_none() -> None:
    """aws_translate con intent=None maneja gracefully (error capturado o respuesta válida)."""
    from cloudshellgpt.bedrock_translator import Translation
    from cloudshellgpt.intent import Intent

    # Si IntentParser puede manejar None, retorna intent válido
    mock_intent = Intent(
        action="unknown",
        service="unknown",
        confidence=0.0,
        raw_input="",
        detected_language="en",
        clarification_needed=True,
    )

    mock_translation = Translation(
        command="",
        explanation="No se pudo determinar la intención",
        detailed_explanation="Input nulo recibido.",
        risk_level="low",
        estimated_cost="$0.00",
        requires_dry_run=False,
        affected_resources=[],
        flags_used={},
    )

    mock_parser = MagicMock()
    mock_parser.parse.return_value = mock_intent

    mock_translator = MagicMock()
    mock_translator.translate.return_value = mock_translation

    with (
        patch("cloudshellgpt.mcp_server.IntentParser", return_value=mock_parser),
        patch("cloudshellgpt.mcp_server.BedrockTranslator", return_value=mock_translator),
    ):
        result = await call_tool("aws_translate", {"intent": None})

    # El tool no debe crashear — retorna JSON válido o error capturado
    text = _get_text_response(result)
    assert len(text) > 0, "La respuesta no debe estar vacía"


@pytest.mark.unit
async def test_aws_translate_input_missing_region_optional() -> None:
    """aws_translate sin region (campo opcional) funciona normalmente con 8 campos."""
    from cloudshellgpt.bedrock_translator import Translation
    from cloudshellgpt.intent import Intent

    mock_intent = Intent(
        action="list",
        service="s3",
        confidence=0.9,
        raw_input="list s3 buckets",
        detected_language="en",
        region=None,
    )

    mock_translation = Translation(
        command="aws s3 ls",
        explanation="Lists all S3 buckets",
        detailed_explanation="Usa el servicio S3 para listar todos los buckets.",
        risk_level="low",
        estimated_cost="$0.00",
        requires_dry_run=False,
        affected_resources=[],
        flags_used={},
    )

    mock_parser = MagicMock()
    mock_parser.parse.return_value = mock_intent

    mock_translator = MagicMock()
    mock_translator.translate.return_value = mock_translation

    with (
        patch("cloudshellgpt.mcp_server.IntentParser", return_value=mock_parser),
        patch("cloudshellgpt.mcp_server.BedrockTranslator", return_value=mock_translator),
    ):
        result = await call_tool("aws_translate", {"intent": "list s3 buckets"})

    data = _parse_json_response(result)

    for field in AWS_TRANSLATE_EXPECTED_FIELDS:
        assert field in data, f"Campo faltante: '{field}'"

    # Verificar que region=None se pasó correctamente
    mock_parser.parse.assert_called_once_with("list s3 buckets", region=None)


@pytest.mark.unit
async def test_aws_translate_input_empty_string() -> None:
    """aws_translate con intent='' retorna JSON válido (IntentParser maneja vacío)."""
    from cloudshellgpt.bedrock_translator import Translation
    from cloudshellgpt.intent import Intent

    mock_intent = Intent(
        action="unknown",
        service="unknown",
        confidence=0.0,
        raw_input="",
        detected_language="en",
        clarification_needed=True,
    )

    mock_translation = Translation(
        command="",
        explanation="No se pudo determinar la intención",
        detailed_explanation="El input está vacío, no se puede traducir.",
        risk_level="low",
        estimated_cost="$0.00",
        requires_dry_run=False,
        affected_resources=[],
        flags_used={},
    )

    mock_parser = MagicMock()
    mock_parser.parse.return_value = mock_intent

    mock_translator = MagicMock()
    mock_translator.translate.return_value = mock_translation

    with (
        patch("cloudshellgpt.mcp_server.IntentParser", return_value=mock_parser),
        patch("cloudshellgpt.mcp_server.BedrockTranslator", return_value=mock_translator),
    ):
        result = await call_tool("aws_translate", {"intent": ""})

    data = _parse_json_response(result)

    for field in AWS_TRANSLATE_EXPECTED_FIELDS:
        assert field in data, f"Campo faltante: '{field}'"

    mock_parser.parse.assert_called_once_with("", region=None)


@pytest.mark.unit
async def test_aws_translate_input_whitespace_only() -> None:
    """aws_translate con intent='   ' (solo espacios) no crashea."""
    from cloudshellgpt.bedrock_translator import Translation
    from cloudshellgpt.intent import Intent

    mock_intent = Intent(
        action="unknown",
        service="unknown",
        confidence=0.0,
        raw_input="   ",
        detected_language="en",
        clarification_needed=True,
    )

    mock_translation = Translation(
        command="",
        explanation="No se pudo determinar la intención",
        detailed_explanation="Input de solo espacios en blanco.",
        risk_level="low",
        estimated_cost="$0.00",
        requires_dry_run=False,
        affected_resources=[],
        flags_used={},
    )

    mock_parser = MagicMock()
    mock_parser.parse.return_value = mock_intent

    mock_translator = MagicMock()
    mock_translator.translate.return_value = mock_translation

    with (
        patch("cloudshellgpt.mcp_server.IntentParser", return_value=mock_parser),
        patch("cloudshellgpt.mcp_server.BedrockTranslator", return_value=mock_translator),
    ):
        result = await call_tool("aws_translate", {"intent": "   "})

    data = _parse_json_response(result)

    for field in AWS_TRANSLATE_EXPECTED_FIELDS:
        assert field in data, f"Campo faltante: '{field}'"

    mock_parser.parse.assert_called_once_with("   ", region=None)


@pytest.mark.unit
async def test_aws_translate_input_extremely_long() -> None:
    """aws_translate con input > 1000 chars no crashea (IntentParser trunca a 500)."""
    from cloudshellgpt.bedrock_translator import Translation
    from cloudshellgpt.intent import Intent

    long_input = "a" * 1500

    mock_intent = Intent(
        action="unknown",
        service="unknown",
        confidence=0.0,
        raw_input=long_input,
        detected_language="en",
        clarification_needed=True,
    )

    mock_translation = Translation(
        command="",
        explanation="No se pudo determinar la intención",
        detailed_explanation="Input demasiado largo, sin palabras clave reconocidas.",
        risk_level="low",
        estimated_cost="$0.00",
        requires_dry_run=False,
        affected_resources=[],
        flags_used={},
    )

    mock_parser = MagicMock()
    mock_parser.parse.return_value = mock_intent

    mock_translator = MagicMock()
    mock_translator.translate.return_value = mock_translation

    with (
        patch("cloudshellgpt.mcp_server.IntentParser", return_value=mock_parser),
        patch("cloudshellgpt.mcp_server.BedrockTranslator", return_value=mock_translator),
    ):
        result = await call_tool("aws_translate", {"intent": long_input})

    data = _parse_json_response(result)

    for field in AWS_TRANSLATE_EXPECTED_FIELDS:
        assert field in data, f"Campo faltante: '{field}'"

    # Verificar que el input largo se pasó al parser
    mock_parser.parse.assert_called_once_with(long_input, region=None)


@pytest.mark.unit
async def test_aws_translate_input_extremely_long_with_valid_keywords() -> None:
    """aws_translate con input largo pero con keywords válidos al inicio detecta servicio."""
    from cloudshellgpt.bedrock_translator import Translation
    from cloudshellgpt.intent import Intent

    long_input = "list s3 buckets " + "x" * 1000

    mock_intent = Intent(
        action="list",
        service="s3",
        confidence=0.7,
        raw_input=long_input,
        detected_language="en",
    )

    mock_translation = Translation(
        command="aws s3 ls",
        explanation="Lista los buckets de S3",
        detailed_explanation="Detectó keywords al inicio del texto largo.",
        risk_level="low",
        estimated_cost="$0.00",
        requires_dry_run=False,
        affected_resources=[],
        flags_used={},
    )

    mock_parser = MagicMock()
    mock_parser.parse.return_value = mock_intent

    mock_translator = MagicMock()
    mock_translator.translate.return_value = mock_translation

    with (
        patch("cloudshellgpt.mcp_server.IntentParser", return_value=mock_parser),
        patch("cloudshellgpt.mcp_server.BedrockTranslator", return_value=mock_translator),
    ):
        result = await call_tool("aws_translate", {"intent": long_input})

    data = _parse_json_response(result)

    for field in AWS_TRANSLATE_EXPECTED_FIELDS:
        assert field in data, f"Campo faltante: '{field}'"

    # Verificar que el comando se tradujo correctamente
    assert data["command"] == "aws s3 ls"
    mock_parser.parse.assert_called_once_with(long_input, region=None)


# ---------------------------------------------------------------------------
# aws_execute — descripción incluye texto de confirmación con usuario (AC-6.3)
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_aws_execute_description_contains_user_confirmation_text() -> None:
    """aws_execute description contiene texto indicando confirmar con el usuario antes de ejecutar.

    Verifica AC-6.3: Description MUST tell the client to confirm with user before calling.
    """
    tools = await list_tools()

    # Buscar el tool aws_execute
    aws_execute_tool = next((t for t in tools if t.name == "aws_execute"), None)
    assert aws_execute_tool is not None, "Tool 'aws_execute' no encontrado en list_tools()"

    description = aws_execute_tool.description
    assert description is not None, "aws_execute no tiene description"

    # Verificar que la descripción contiene lenguaje de confirmación con el usuario
    desc_lower = description.lower()
    assert "confirm" in desc_lower or "show" in desc_lower, (
        f"La descripción de aws_execute debe indicar que se confirme con el usuario. "
        f"Descripción actual: '{description}'"
    )
    assert "user" in desc_lower, (
        f"La descripción de aws_execute debe mencionar al usuario. "
        f"Descripción actual: '{description}'"
    )


# ---------------------------------------------------------------------------
# list_tools() — verificar que retorna exactamente 4 tools con names correctos,
# schemas JSON válidos, y descriptions no vacías
# ---------------------------------------------------------------------------

# Nombres esperados de los 4 tools del MCP server
EXPECTED_TOOL_NAMES = ["aws_translate", "aws_execute", "aws_cost_preview", "aws_explain"]


@pytest.mark.unit
async def test_list_tools_returns_exactly_4_tools() -> None:
    """list_tools() retorna exactamente 4 tools (ni más, ni menos)."""
    tools = await list_tools()

    assert isinstance(tools, list), f"Expected list, got {type(tools)}"
    assert len(tools) == 4, (
        f"Se esperaban exactamente 4 tools, pero list_tools() retornó {len(tools)}. "
        f"Tools encontrados: {[t.name for t in tools]}"
    )


@pytest.mark.unit
async def test_list_tools_returns_correct_tool_names() -> None:
    """list_tools() retorna los 4 nombres correctos: aws_translate, aws_execute, aws_cost_preview, aws_explain."""
    tools = await list_tools()

    tool_names = [t.name for t in tools]

    for expected_name in EXPECTED_TOOL_NAMES:
        assert expected_name in tool_names, (
            f"Tool '{expected_name}' no encontrado en list_tools(). Tools disponibles: {tool_names}"
        )

    # Verificar que NO hay tools adicionales inesperados
    unexpected = set(tool_names) - set(EXPECTED_TOOL_NAMES)
    assert len(unexpected) == 0, (
        f"Se encontraron tools inesperados: {unexpected}. Solo se esperan: {EXPECTED_TOOL_NAMES}"
    )


@pytest.mark.unit
@pytest.mark.parametrize("tool_name", EXPECTED_TOOL_NAMES)
async def test_list_tools_each_tool_has_non_empty_description(tool_name: str) -> None:
    """Cada tool en list_tools() tiene una description no vacía."""
    tools = await list_tools()

    tool = next((t for t in tools if t.name == tool_name), None)
    assert tool is not None, f"Tool '{tool_name}' no encontrado"

    assert tool.description is not None, f"Tool '{tool_name}' tiene description=None"
    assert isinstance(tool.description, str), (
        f"Tool '{tool_name}' description debe ser str, got {type(tool.description)}"
    )
    assert len(tool.description.strip()) > 0, (
        f"Tool '{tool_name}' tiene description vacía o solo whitespace"
    )


@pytest.mark.unit
@pytest.mark.parametrize("tool_name", EXPECTED_TOOL_NAMES)
async def test_list_tools_each_tool_has_valid_json_schema(tool_name: str) -> None:
    """Cada tool en list_tools() tiene un inputSchema que es un JSON Schema válido."""
    tools = await list_tools()

    tool = next((t for t in tools if t.name == tool_name), None)
    assert tool is not None, f"Tool '{tool_name}' no encontrado"

    schema = tool.inputSchema
    assert schema is not None, f"Tool '{tool_name}' tiene inputSchema=None"
    assert isinstance(schema, dict), (
        f"Tool '{tool_name}' inputSchema debe ser dict, got {type(schema)}"
    )

    # Verificar estructura mínima de JSON Schema
    assert "type" in schema, (
        f"Tool '{tool_name}' inputSchema no tiene campo 'type'. Schema: {schema}"
    )
    assert schema["type"] == "object", (
        f"Tool '{tool_name}' inputSchema type debe ser 'object', got '{schema['type']}'"
    )

    # Verificar que tiene properties definidas
    assert "properties" in schema, (
        f"Tool '{tool_name}' inputSchema no tiene campo 'properties'. Schema: {schema}"
    )
    assert isinstance(schema["properties"], dict), (
        f"Tool '{tool_name}' inputSchema.properties debe ser dict"
    )
    assert len(schema["properties"]) > 0, (
        f"Tool '{tool_name}' inputSchema.properties está vacío (debe tener al menos 1 propiedad)"
    )

    # Verificar que required es un array (si existe)
    if "required" in schema:
        assert isinstance(schema["required"], list), (
            f"Tool '{tool_name}' inputSchema.required debe ser list, got {type(schema['required'])}"
        )
        # Verificar que cada required field existe en properties
        for req_field in schema["required"]:
            assert req_field in schema["properties"], (
                f"Tool '{tool_name}': campo required '{req_field}' no está definido en properties"
            )

    # Verificar que cada property tiene al menos 'type' y 'description'
    for prop_name, prop_schema in schema["properties"].items():
        assert isinstance(prop_schema, dict), (
            f"Tool '{tool_name}' property '{prop_name}' debe ser dict"
        )
        assert "type" in prop_schema, (
            f"Tool '{tool_name}' property '{prop_name}' no tiene 'type'. "
            f"Schema de la propiedad: {prop_schema}"
        )
        assert "description" in prop_schema, (
            f"Tool '{tool_name}' property '{prop_name}' no tiene 'description'. "
            f"Schema de la propiedad: {prop_schema}"
        )
        assert len(prop_schema["description"].strip()) > 0, (
            f"Tool '{tool_name}' property '{prop_name}' tiene description vacía"
        )


@pytest.mark.unit
async def test_list_tools_all_tools_are_tool_instances() -> None:
    """list_tools() retorna instancias de mcp.types.Tool (no dicts u otros tipos)."""
    from mcp.types import Tool

    tools = await list_tools()

    for i, tool in enumerate(tools):
        assert isinstance(tool, Tool), (
            f"Elemento [{i}] en list_tools() no es instancia de Tool, "
            f"es {type(tool)}. Name: {getattr(tool, 'name', 'N/A')}"
        )


@pytest.mark.unit
async def test_list_tools_tool_names_are_unique() -> None:
    """list_tools() no retorna tools con nombres duplicados."""
    tools = await list_tools()

    tool_names = [t.name for t in tools]
    duplicates = [name for name in tool_names if tool_names.count(name) > 1]

    assert len(duplicates) == 0, f"Se encontraron nombres de tools duplicados: {set(duplicates)}"


@pytest.mark.unit
async def test_list_tools_schemas_have_required_fields() -> None:
    """Cada tool que requiere inputs tiene el campo 'required' en su schema."""
    tools = await list_tools()

    # Todos los tools de CloudShellGPT requieren al menos un campo
    expected_required_fields = {
        "aws_translate": ["intent"],
        "aws_execute": ["command"],
        "aws_cost_preview": ["command"],
        "aws_explain": ["command"],
    }

    for tool in tools:
        schema = tool.inputSchema
        assert "required" in schema, (
            f"Tool '{tool.name}' inputSchema no tiene 'required' pero se espera "
            f"que requiera: {expected_required_fields.get(tool.name, [])}"
        )

        expected = expected_required_fields.get(tool.name, [])
        for field in expected:
            assert field in schema["required"], (
                f"Tool '{tool.name}': campo '{field}' debe estar en required. "
                f"Required actual: {schema['required']}"
            )


@pytest.mark.unit
async def test_list_tools_descriptions_are_descriptive() -> None:
    """Las descriptions de los tools tienen longitud mínima razonable (>20 chars).

    Una descripción de tool MCP debe ser lo suficientemente informativa para que
    un cliente (Kiro, Claude Desktop) entienda qué hace la herramienta.
    """
    tools = await list_tools()

    min_description_length = 20

    for tool in tools:
        assert len(tool.description) >= min_description_length, (
            f"Tool '{tool.name}' tiene description demasiado corta "
            f"({len(tool.description)} chars): '{tool.description}'. "
            f"Mínimo esperado: {min_description_length} chars."
        )
