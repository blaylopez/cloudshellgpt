"""Tests del MCP server: invariantes, routing y manejo de errores.

Incluye:
- Invariante: MCP server NUNCA crashea ante excepciones internas.
- Routing: call_tool retorna "Unknown tool" para nombres desconocidos.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from mcp.types import TextContent

from cloudshellgpt.bedrock_translator import BedrockError, BedrockErrorType
from cloudshellgpt.mcp_server import call_tool

# ---------------------------------------------------------------------------
# Tipos de excepción parametrizados (mínimo 10)
# ---------------------------------------------------------------------------

EXCEPTION_INSTANCES: list[tuple[str, Exception]] = [
    ("ValueError", ValueError("invalid value")),
    ("TypeError", TypeError("expected str, got int")),
    ("KeyError", KeyError("missing_key")),
    ("AttributeError", AttributeError("object has no attribute 'x'")),
    (
        "BedrockError",
        BedrockError(
            "Bedrock service unavailable",
            error_type=BedrockErrorType.GENERIC,
            suggestion="Retry later",
            technical_detail="HTTP 503",
        ),
    ),
    ("TimeoutError", TimeoutError("request timed out")),
    ("ConnectionError", ConnectionError("connection refused")),
    (
        "json.JSONDecodeError",
        json.JSONDecodeError("Expecting value", "doc", 0),
    ),
    (
        "botocore.ClientError",
        ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
            "InvokeModel",
        ),
    ),
    ("RuntimeError", RuntimeError("unexpected runtime failure")),
]

EXCEPTION_IDS = [name for name, _ in EXCEPTION_INSTANCES]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_error_text_content(result: Any) -> None:
    """Verifica que el resultado sea list[TextContent] con mensaje de error."""
    assert isinstance(result, list), f"Expected list, got {type(result)}"
    assert len(result) == 1, f"Expected 1 item, got {len(result)}"
    content = result[0]
    assert isinstance(content, TextContent), f"Expected TextContent, got {type(content)}"
    assert content.type == "text"
    assert content.text, "Error message must not be empty"
    assert "Error:" in content.text, f"Expected 'Error:' prefix, got: {content.text}"


# ---------------------------------------------------------------------------
# Invariante: aws_translate nunca crashea
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.invariant
@pytest.mark.parametrize(("exc_name", "exc"), EXCEPTION_INSTANCES, ids=EXCEPTION_IDS)
async def test_aws_translate_never_crashes(exc_name: str, exc: Exception) -> None:
    """call_tool('aws_translate') retorna TextContent con error, nunca propaga excepción."""
    with patch(
        "cloudshellgpt.mcp_server.IntentParser.parse",
        side_effect=exc,
    ):
        result = await call_tool("aws_translate", {"intent": "list s3 buckets"})

    _assert_error_text_content(result)


# ---------------------------------------------------------------------------
# Invariante: aws_execute nunca crashea
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.invariant
@pytest.mark.parametrize(("exc_name", "exc"), EXCEPTION_INSTANCES, ids=EXCEPTION_IDS)
async def test_aws_execute_never_crashes(exc_name: str, exc: Exception) -> None:
    """call_tool('aws_execute') retorna TextContent con error, nunca propaga excepción."""
    with patch(
        "cloudshellgpt.mcp_server.AWSExecutor.run",
        side_effect=exc,
    ):
        result = await call_tool("aws_execute", {"command": "aws s3 ls"})

    _assert_error_text_content(result)


# ---------------------------------------------------------------------------
# Invariante: aws_cost_preview nunca crashea
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.invariant
@pytest.mark.parametrize(("exc_name", "exc"), EXCEPTION_INSTANCES, ids=EXCEPTION_IDS)
async def test_aws_cost_preview_never_crashes(exc_name: str, exc: Exception) -> None:
    """call_tool('aws_cost_preview') retorna TextContent con error, nunca propaga excepción."""
    with patch(
        "cloudshellgpt.cost.CostEstimator.estimate",
        side_effect=exc,
    ):
        result = await call_tool("aws_cost_preview", {"command": "aws ec2 run-instances"})

    _assert_error_text_content(result)


# ---------------------------------------------------------------------------
# Invariante: aws_explain nunca crashea
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.invariant
@pytest.mark.parametrize(("exc_name", "exc"), EXCEPTION_INSTANCES, ids=EXCEPTION_IDS)
async def test_aws_explain_never_crashes(exc_name: str, exc: Exception) -> None:
    """call_tool('aws_explain') retorna TextContent con error, nunca propaga excepción."""
    with patch(
        "cloudshellgpt.learning.Explainer.explain_sync",
        side_effect=exc,
    ):
        result = await call_tool("aws_explain", {"command": "aws s3 ls"})

    _assert_error_text_content(result)


# ---------------------------------------------------------------------------
# Invariante: MCP es stateless — cada llamada instancia dependencias frescas
# ---------------------------------------------------------------------------

# Inputs variados para las 5 llamadas secuenciales
_STATELESS_INPUTS: list[tuple[str, dict[str, str]]] = [
    ("spanish_s3_list", {"intent": "lista los buckets de S3"}),
    ("english_ec2_create", {"intent": "create an EC2 instance", "region": "eu-west-1"}),
    ("spanish_dynamo_delete", {"intent": "borra la tabla DynamoDB users"}),
    ("english_lambda_describe", {"intent": "describe the Lambda function payments"}),
    ("chinese_iam_list", {"intent": "显示所有IAM用户", "region": "ap-northeast-1"}),
]


@pytest.mark.unit
@pytest.mark.invariant
async def test_aws_translate_stateless_fresh_intent_parser_per_call() -> None:
    """Verifica que IntentParser se instancia fresco en CADA llamada (no se reutiliza).

    Hace 5 calls secuenciales a aws_translate con inputs diferentes y verifica
    que IntentParser() se construyó 5 veces (una instancia nueva por call).
    Detecta reutilización trackeando las instancias creadas con side_effect.
    """
    from cloudshellgpt.bedrock_translator import Translation
    from cloudshellgpt.intent import Intent

    # Registro de instancias creadas
    parser_instances: list[object] = []

    class _TrackingIntentParser:
        """IntentParser falso que registra cada instancia creada."""

        def __init__(self) -> None:
            parser_instances.append(self)

        def parse(self, text: str, region: str | None = None) -> Intent:
            """Retorna un Intent mínimo válido."""
            return Intent(
                action="list",
                service="s3",
                confidence=0.9,
                raw_input=text,
                detected_language="es",
                region=region,
            )

    # Mock BedrockTranslator para que no llame a AWS
    mock_translator_instance = MagicMock()
    mock_translator_instance.translate.return_value = Translation(
        command="aws s3 ls",
        explanation="test",
        detailed_explanation="test detail",
        risk_level="low",
        estimated_cost="$0.00",
    )

    with (
        patch(
            "cloudshellgpt.mcp_server.IntentParser",
            _TrackingIntentParser,
        ),
        patch(
            "cloudshellgpt.mcp_server.BedrockTranslator",
            return_value=mock_translator_instance,
        ),
    ):
        # Ejecutar 5 llamadas secuenciales
        for _, args in _STATELESS_INPUTS:
            await call_tool("aws_translate", args)

    # Verificar: 5 instancias distintas creadas (una por llamada)
    assert len(parser_instances) == 5, (
        f"Se esperaban 5 instancias de IntentParser (una por call), "
        f"pero se crearon {len(parser_instances)}"
    )
    # Verificar que NINGUNA instancia se repite (todas son objetos distintos)
    instance_ids = [id(inst) for inst in parser_instances]
    assert len(set(instance_ids)) == 5, (
        "Se detectó reutilización: hay instancias de IntentParser compartidas entre llamadas"
    )


@pytest.mark.unit
@pytest.mark.invariant
async def test_aws_translate_stateless_fresh_bedrock_translator_per_call() -> None:
    """Verifica que BedrockTranslator se instancia fresco en CADA llamada (no se reutiliza).

    Hace 5 calls secuenciales a aws_translate con inputs diferentes y verifica
    que BedrockTranslator() se construyó 5 veces (una instancia nueva por call).
    Usa side_effect en el constructor mock para trackear instanciación.
    """
    from cloudshellgpt.bedrock_translator import Translation

    # Registro de instancias creadas
    translator_instances: list[object] = []

    class _TrackingBedrockTranslator:
        """BedrockTranslator falso que registra cada instancia creada."""

        def __init__(self) -> None:
            translator_instances.append(self)

        def translate(self, intent: object) -> Translation:
            """Retorna una Translation mínima válida."""
            return Translation(
                command="aws s3 ls",
                explanation="test",
                detailed_explanation="test detail",
                risk_level="low",
                estimated_cost="$0.00",
            )

    # Mock IntentParser para que no falle
    mock_parser_instance = MagicMock()
    mock_parser_instance.parse.return_value = MagicMock()

    with (
        patch(
            "cloudshellgpt.mcp_server.IntentParser",
            return_value=mock_parser_instance,
        ),
        patch(
            "cloudshellgpt.mcp_server.BedrockTranslator",
            _TrackingBedrockTranslator,
        ),
    ):
        # Ejecutar 5 llamadas secuenciales
        for _, args in _STATELESS_INPUTS:
            await call_tool("aws_translate", args)

    # Verificar: 5 instancias distintas creadas (una por llamada)
    assert len(translator_instances) == 5, (
        f"Se esperaban 5 instancias de BedrockTranslator (una por call), "
        f"pero se crearon {len(translator_instances)}"
    )
    # Verificar que NINGUNA instancia se repite (todas son objetos distintos)
    instance_ids = [id(inst) for inst in translator_instances]
    assert len(set(instance_ids)) == 5, (
        "Se detectó reutilización: hay instancias de BedrockTranslator compartidas entre llamadas"
    )


@pytest.mark.unit
@pytest.mark.invariant
async def test_aws_translate_stateless_both_dependencies_fresh_per_call() -> None:
    """Verifica que AMBAS dependencias (IntentParser + BedrockTranslator) se instancian frescas.

    Test integrado que confirma el invariante completo: en 5 llamadas secuenciales,
    tanto IntentParser como BedrockTranslator se crean nuevos cada vez, sin compartir
    estado entre invocaciones del tool.
    """
    from cloudshellgpt.bedrock_translator import Translation
    from cloudshellgpt.intent import Intent

    # Registro combinado de instancias
    parser_instances: list[object] = []
    translator_instances: list[object] = []

    class _TrackingIntentParser:
        """IntentParser falso con tracking de instancias."""

        def __init__(self) -> None:
            parser_instances.append(self)

        def parse(self, text: str, region: str | None = None) -> Intent:
            """Retorna un Intent mínimo válido."""
            return Intent(
                action="list",
                service="s3",
                confidence=0.9,
                raw_input=text,
                detected_language="en",
                region=region,
            )

    class _TrackingBedrockTranslator:
        """BedrockTranslator falso con tracking de instancias."""

        def __init__(self) -> None:
            translator_instances.append(self)

        def translate(self, intent: object) -> Translation:
            """Retorna una Translation mínima válida."""
            return Translation(
                command="aws s3 ls",
                explanation="test",
                detailed_explanation="test detail",
                risk_level="low",
                estimated_cost="$0.00",
            )

    with (
        patch(
            "cloudshellgpt.mcp_server.IntentParser",
            _TrackingIntentParser,
        ),
        patch(
            "cloudshellgpt.mcp_server.BedrockTranslator",
            _TrackingBedrockTranslator,
        ),
    ):
        # Ejecutar 5 llamadas secuenciales con inputs distintos
        for _, args in _STATELESS_INPUTS:
            result = await call_tool("aws_translate", args)
            # Verificar que cada call retorna resultado válido (no error)
            assert isinstance(result, list)
            assert len(result) == 1
            assert isinstance(result[0], TextContent)
            assert "Error:" not in result[0].text

    # Verificar conteo de instanciaciones
    assert len(parser_instances) == 5, (
        f"IntentParser: se esperaban 5 instancias, se crearon {len(parser_instances)}"
    )
    assert len(translator_instances) == 5, (
        f"BedrockTranslator: se esperaban 5 instancias, se crearon {len(translator_instances)}"
    )

    # Verificar unicidad — ninguna instancia se reutiliza entre calls
    parser_ids = [id(inst) for inst in parser_instances]
    translator_ids = [id(inst) for inst in translator_instances]
    assert len(set(parser_ids)) == 5, "Se detectó reutilización de IntentParser entre llamadas"
    assert len(set(translator_ids)) == 5, (
        "Se detectó reutilización de BedrockTranslator entre llamadas"
    )


# ---------------------------------------------------------------------------
# Routing: tool name desconocido retorna "Unknown tool: {name}"
# ---------------------------------------------------------------------------

UNKNOWN_TOOL_NAMES: list[tuple[str, str]] = [
    ("unknown_valid_looking", "aws_delete_everything"),
    ("empty_string", ""),
    ("whitespace_only", "   "),
    ("name_with_spaces", "aws translate"),
    ("unicode_emoji", "🚀💥"),
    ("unicode_cjk", "翻译命令"),
    ("unicode_arabic", "أداة_ترجمة"),
    ("sql_injection", "'; DROP TABLE tools; --"),
    ("path_traversal", "../../../etc/passwd"),
    ("null_byte", "aws_translate\x00evil"),
    ("very_long_string", "a" * 10_000),
    ("html_injection", "<script>alert('xss')</script>"),
    ("newline_injection", "aws_translate\naws_execute"),
    ("tab_character", "aws\ttranslate"),
    ("backslash", "aws\\translate"),
]

UNKNOWN_TOOL_IDS = [name for name, _ in UNKNOWN_TOOL_NAMES]


@pytest.mark.unit
@pytest.mark.parametrize(("case_id", "tool_name"), UNKNOWN_TOOL_NAMES, ids=UNKNOWN_TOOL_IDS)
async def test_call_tool_unknown_name_returns_unknown_tool_message(
    case_id: str, tool_name: str
) -> None:
    """call_tool con nombre desconocido retorna list[TextContent] con 'Unknown tool: {name}'.

    Verifica que el routing en call_tool responde correctamente para cualquier
    nombre de herramienta que no sea uno de los 4 válidos (aws_translate,
    aws_execute, aws_cost_preview, aws_explain).

    Args:
        case_id: Identificador descriptivo del caso de prueba.
        tool_name: Nombre de herramienta inválido/desconocido a probar.
    """
    result = await call_tool(tool_name, {})

    # Verifica estructura: list[TextContent] con un solo elemento
    assert isinstance(result, list), f"Expected list, got {type(result)}"
    assert len(result) == 1, f"Expected 1 item, got {len(result)}"

    content = result[0]
    assert isinstance(content, TextContent), f"Expected TextContent, got {type(content)}"
    assert content.type == "text"

    # Verifica mensaje exacto: "Unknown tool: {name}"
    assert content.text == f"Unknown tool: {tool_name}", (
        f"Expected 'Unknown tool: {tool_name}', got: {content.text!r}"
    )
