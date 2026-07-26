"""Bedrock translator — converts Intent objects into AWS CLI commands via Claude 3.5 Sonnet."""

from __future__ import annotations

import json
import logging
import random
import time
from enum import StrEnum
from typing import Any

import boto3
from botocore.exceptions import ClientError, ReadTimeoutError
from pydantic import BaseModel, Field

from cloudshellgpt.intent import Intent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Error types (defined before BedrockTranslator so they can be referenced)
# ---------------------------------------------------------------------------


class BedrockErrorType(StrEnum):
    """Categories of Bedrock errors for user-facing messaging."""

    CREDENTIALS = "credentials"
    THROTTLING = "throttling"
    TIMEOUT = "timeout"
    MODEL_NOT_AVAILABLE = "model_not_available"
    INVALID_RESPONSE = "invalid_response"
    GENERIC = "generic"


class BedrockError(Exception):
    """Raised when Bedrock translation fails.

    Provides structured error information with user-facing messages
    and actionable suggestions.

    Attributes:
        error_type: Category of the error for classification.
        user_message: Human-readable message explaining what went wrong.
        suggestion: Actionable advice on how to resolve the issue.
        technical_detail: Raw error message for debugging (optional).
    """

    def __init__(
        self,
        user_message: str,
        *,
        error_type: BedrockErrorType = BedrockErrorType.GENERIC,
        suggestion: str = "",
        technical_detail: str = "",
    ) -> None:
        self.error_type = error_type
        self.user_message = user_message
        self.suggestion = suggestion
        self.technical_detail = technical_detail
        super().__init__(user_message)

    @property
    def is_retryable(self) -> bool:
        """Whether this error is transient and safe to retry.

        Returns:
            True if the error type is throttling or timeout.
        """
        return self.error_type in _RETRYABLE_ERROR_TYPES


# Tipos de error que son transitorios y seguros para reintentar
_RETRYABLE_ERROR_TYPES: frozenset[BedrockErrorType] = frozenset(
    {
        BedrockErrorType.THROTTLING,
        BedrockErrorType.TIMEOUT,
    }
)


# ---------------------------------------------------------------------------
# Translation model
# ---------------------------------------------------------------------------


class Translation(BaseModel):
    """A translated AWS CLI command with metadata."""

    command: str
    explanation: str
    detailed_explanation: str
    risk_level: str = "low"
    estimated_cost: str = "$0.00"
    requires_dry_run: bool = False
    affected_resources: list[str] = Field(default_factory=list)
    flags_used: dict[str, str] = Field(default_factory=dict)
    tip: str | None = None
    related_commands: list[dict[str, str]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Translator
# ---------------------------------------------------------------------------


class BedrockTranslator:
    """Translates natural language intents to AWS CLI commands using Amazon Bedrock.

    Uses Claude 3.5 Sonnet via the Bedrock Converse API. Implements a
    few-shot system prompt with best practices for AWS CLI generation.
    Retries transient errors (throttling, timeouts) with exponential backoff.
    """

    MODEL_ID = "us.anthropic.claude-sonnet-4-6"
    REGION = "us-east-1"

    # --- Retry configuration constants ---
    MAX_RETRIES = 3
    BASE_DELAY = 1.0  # seconds
    MAX_JITTER = 0.5  # seconds

    # --- Inference configuration constants ---
    # Temperature por tipo de intención (menor = más preciso)
    TRANSLATION_TEMPERATURE = 0.2
    EXPLANATION_TEMPERATURE = 0.3
    CODE_GENERATION_TEMPERATURE = 0.2
    ARCHITECTURE_REVIEW_TEMPERATURE = 0.2
    DEFAULT_TEMPERATURE = 0.2

    # Max tokens por tipo de intención
    TRANSLATION_MAX_TOKENS = 2048
    EXPLANATION_MAX_TOKENS = 1024
    CODE_GENERATION_MAX_TOKENS = 4096
    ARCHITECTURE_REVIEW_MAX_TOKENS = 4096
    DEFAULT_MAX_TOKENS = 4096

    # Top-P compartido para todas las intenciones
    TOP_P = 0.9

    SYSTEM_PROMPT = """Eres un experto en AWS con 15 años de experiencia.
Tu trabajo es traducir intenciones en lenguaje natural a comandos AWS CLI exactos, seguros y eficientes.

REGLAS CRÍTICAS:
1. SIEMPRE devuelve JSON válido con esta estructura:
   {
     "command": "aws <service> <action> ...flags",
     "explanation": "Resumen de 1 línea en el mismo idioma del input",
     "detailed_explanation": "Explicación de 3-5 líneas de qué hace cada flag importante",
     "risk_level": "low|medium|high|critical",
     "estimated_cost": "$X.XX per month o per request",
     "requires_dry_run": boolean,
     "affected_resources": ["lista de recursos afectados"],
     "flags_used": {"flag_name": "explicación breve"}
   }

2. Si la intención es ambigua, devuelve:
   {
     "clarification_needed": true,
     "clarification_question": "Pregunta específica para clarificar"
   }

3. Riesgo:
   - low: SIEMPRE para read-only (list, describe, get, head, wait, show, ls)
   - medium: create/update reversible
   - high: delete de UN recurso específico, terminate
   - critical: delete recursivo, force sin confirmación, o que afecta múltiples recursos/producción
   IMPORTANTE: los comandos describe-* y list-* SIEMPRE son "low", sin importar los filtros o queries.

4. Comandos destructivos DEBEN marcar requires_dry_run: true

5. NUNCA generes comandos con shell operators: |, &&, ;, xargs, $(), backticks.
   Solo genera UN ÚNICO comando `aws` puro. Si la operación requiere múltiples IDs,
   pásalos como argumentos separados por espacio (ej: --instance-ids id1 id2 id3).
   Si la operación NO se puede hacer con un solo comando, usa "clarification_needed" y
   explica qué pasos seguir manualmente.
   EJEMPLO INCORRECTO: aws iam generate-credential-report && aws iam get-credential-report
   EJEMPLO INCORRECTO: aws ec2 describe-instances | xargs aws ec2 terminate-instances
   EJEMPLO INCORRECTO: aws s3 ls $(aws sts get-caller-identity --query Account --output text)
   EJEMPLO CORRECTO: aws iam get-credential-report --output json
   EJEMPLO CORRECTO: aws ec2 terminate-instances --instance-ids i-123 i-456 i-789

   Si el usuario pide una operación que necesita múltiples pasos (ej: "elimina todas las instancias activas"),
   responde con clarification_needed: true y explica los pasos que debe seguir manualmente.

6. Usa flags modernos:
   - --output json por defecto (el usuario quiere parseable)
   - --output table cuando el usuario pide listar/mostrar (más legible)
   - --no-paginate cuando el resultado es chico
   - --query para filtrar server-side (IMPORTANTE: los alias/keys en --query SIEMPRE en ASCII, nunca usar caracteres Unicode. Ej: {Name:Name,Created:CreationDate} NO {名称:Name})
   - --filters en lugar de client-side

7. Idioma: TODAS las cadenas de texto dirigidas al usuario (explanation, detailed_explanation,
   estimated_cost, tip, related_commands descriptions) deben estar en el MISMO idioma del input.
   Los comandos AWS y nombres de flags permanecen en inglés.

8. Incluye siempre estos campos adicionales en tu respuesta JSON:
   "tip": "Un consejo educativo breve relacionado al comando (en el idioma del input)",
   "related_commands": [{"command": "aws ...", "description": "breve descripción en el idioma del input"}]

EJEMPLOS:

Input: "lista los buckets de S3"
Output: {
  "command": "aws s3api list-buckets --query 'Buckets[].{Name:Name,Created:CreationDate}' --output table",
  "explanation": "Lista todos los buckets de S3 con nombre y fecha de creación",
  "detailed_explanation": "Usa s3api (API directa) en lugar de s3 (alto nivel) para mejor control. --query filtra server-side y --output table da formato legible.",
  "risk_level": "low",
  "estimated_cost": "$0.00",
  "requires_dry_run": false,
  "affected_resources": [],
  "flags_used": {"--query": "JMESPath filter", "--output": "table format"}
}

Input: "borra todos los objetos del bucket de logs"
Output: {
  "command": "aws s3 rm s3://logs-bucket-name/ --recursive",
  "explanation": "Elimina TODOS los objetos del bucket de logs recursivamente",
  "detailed_explanation": "⚠️ ESTA ACCIÓN ES IRREVERSIBLE. Borra todos los objetos pero NO el bucket. Para borrar el bucket también usa s3api delete-bucket. Recomendamos primero: aws s3 ls s3://logs-bucket-name/ --recursive | wc -l para contar archivos.",
  "risk_level": "critical",
  "estimated_cost": "$0.00",
  "requires_dry_run": true,
  "affected_resources": ["s3://logs-bucket-name/*"],
  "flags_used": {"--recursive": "Borra todos los objetos, no solo el primero"}
}

Input: "muéstrame las lambdas que fallaron ayer"
Output: {
  "command": "aws lambda list-functions --query 'Functions[?State==`Failed`].{Name:FunctionName,Runtime:Runtime,LastModified:LastModified}' --output table",
  "explanation": "Lista funciones Lambda en estado Failed",
  "detailed_explanation": "Filtra server-side usando --query. Para más detalles de un fallo específico: aws logs filter-log-events --log-group-name /aws/lambda/FUNCTION_NAME",
  "risk_level": "low",
  "estimated_cost": "$0.00",
  "requires_dry_run": false,
  "affected_resources": [],
  "flags_used": {"--query": "Filter by state", "--output": "table"}
}
"""

    def __init__(
        self,
        region: str = REGION,
        *,
        model_id: str = MODEL_ID,
        max_retries: int = MAX_RETRIES,
        base_delay: float = BASE_DELAY,
    ) -> None:
        self.client = boto3.client("bedrock-runtime", region_name=region)
        self.region = region
        self.model_id = model_id
        self.max_retries = max_retries
        self.base_delay = base_delay

    def translate(self, intent: Intent) -> Translation:
        """Translate an Intent into an AWS CLI command.

        Retries transient errors (throttling, timeouts) with exponential
        backoff and jitter. Non-transient errors fail immediately.

        Args:
            intent: The parsed user intent

        Returns:
            Translation object with the command and metadata

        Raises:
            BedrockError: If translation fails after all retries (for transient)
                or immediately (for non-transient errors).
        """
        user_message = self._build_user_message(intent)
        response = self._call_converse_with_retry(user_message)
        return self._parse_response(response)

    def _call_converse_with_retry(self, user_message: str) -> dict[str, Any]:
        """Call Bedrock Converse API with exponential backoff for transient errors.

        Args:
            user_message: The formatted user message to send.

        Returns:
            The raw Bedrock Converse API response dict.

        Raises:
            BedrockError: If a non-retryable error occurs, or after exhausting retries.
        """
        last_error: BedrockError | None = None

        for attempt in range(self.max_retries + 1):
            try:
                return self.client.converse(  # type: ignore[no-any-return]
                    modelId=self.model_id,
                    messages=[
                        {
                            "role": "user",
                            "content": [{"text": user_message}],
                        }
                    ],
                    system=[{"text": self.SYSTEM_PROMPT}],
                    inferenceConfig={
                        "maxTokens": self.TRANSLATION_MAX_TOKENS,
                        "temperature": self.TRANSLATION_TEMPERATURE,
                    },
                )
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")
                bedrock_error = self._map_client_error(error_code, e)
                last_error = bedrock_error

                if not bedrock_error.is_retryable:
                    raise bedrock_error from e

                if attempt < self.max_retries:
                    delay = self._calculate_backoff(attempt)
                    logger.warning(
                        "Transient error '%s' on attempt %d/%d, retrying in %.2fs",
                        error_code,
                        attempt + 1,
                        self.max_retries + 1,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    raise bedrock_error from e

            except ReadTimeoutError as e:
                last_error = BedrockError(
                    "Request to Bedrock timed out",
                    error_type=BedrockErrorType.TIMEOUT,
                    suggestion="Check your network connection and try again",
                    technical_detail=str(e),
                )

                if attempt < self.max_retries:
                    delay = self._calculate_backoff(attempt)
                    logger.warning(
                        "Read timeout on attempt %d/%d, retrying in %.2fs",
                        attempt + 1,
                        self.max_retries + 1,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    raise last_error from e

            except Exception as e:
                # Non-transient unexpected errors fail immediately
                raise BedrockError(
                    "Unexpected error communicating with Bedrock",
                    error_type=BedrockErrorType.GENERIC,
                    suggestion="Check AWS connectivity and try again",
                    technical_detail=str(e),
                ) from e

        # Nunca debería llegar aquí, pero por seguridad de tipos
        assert last_error is not None  # noqa: S101
        raise last_error

    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff delay with jitter.

        Formula: base_delay * 2^attempt + random_jitter

        Args:
            attempt: Zero-indexed attempt number.

        Returns:
            Delay in seconds before the next retry.
        """
        exponential_delay = self.base_delay * (2**attempt)
        jitter = random.uniform(0, self.MAX_JITTER)  # noqa: S311
        return exponential_delay + jitter  # type: ignore[no-any-return]

    def _parse_response(self, response: dict[str, Any]) -> Translation:
        """Parse and validate the Bedrock Converse API response.

        Args:
            response: Raw response from client.converse().

        Returns:
            A Translation model with the parsed data.

        Raises:
            BedrockError: If response structure is invalid or JSON is malformed.
        """
        try:
            response_text = response["output"]["message"]["content"][0]["text"]
        except (KeyError, IndexError) as e:
            raise BedrockError(
                "Bedrock returned an empty or malformed response",
                error_type=BedrockErrorType.INVALID_RESPONSE,
                suggestion="Try rephrasing your request or try again later",
                technical_detail=str(e),
            ) from e

        try:
            data = self._extract_json(response_text)
        except json.JSONDecodeError as e:
            raise BedrockError(
                "Model returned invalid JSON — could not parse translation",
                error_type=BedrockErrorType.INVALID_RESPONSE,
                suggestion="Try rephrasing your request with more specific details",
                technical_detail=f"JSON parse error: {e}",
            ) from e

        # Handle clarification requests from the LLM
        if data.get("clarification_needed"):
            raise BedrockError(
                data.get(
                    "clarification_question", "Please be more specific about what you want to do."
                ),
                error_type=BedrockErrorType.INVALID_RESPONSE,
                suggestion=data.get("clarification_question", "Try specifying exact resource IDs."),
                technical_detail="LLM requested clarification instead of generating a command",
            )

        return Translation(
            command=data["command"],
            explanation=data.get("explanation", ""),
            detailed_explanation=data.get("detailed_explanation", ""),
            risk_level=data.get("risk_level", "low"),
            estimated_cost=data.get("estimated_cost", "$0.00"),
            requires_dry_run=data.get("requires_dry_run", False),
            affected_resources=data.get("affected_resources", []),
            flags_used=data.get("flags_used", {}),
            tip=data.get("tip"),
            related_commands=data.get("related_commands", []),
        )

    def _map_client_error(self, error_code: str, exc: ClientError) -> BedrockError:
        """Map a botocore ClientError code to a structured BedrockError."""
        error_map: dict[str, tuple[BedrockErrorType, str, str]] = {
            "AccessDeniedException": (
                BedrockErrorType.CREDENTIALS,
                "Access denied — insufficient permissions to invoke Bedrock",
                "Check that your IAM role has bedrock:InvokeModel permission",
            ),
            "UnrecognizedClientException": (
                BedrockErrorType.CREDENTIALS,
                "AWS credentials are invalid or expired",
                "Run 'aws sts get-caller-identity' to verify your credentials",
            ),
            "ExpiredTokenException": (
                BedrockErrorType.CREDENTIALS,
                "AWS session token has expired",
                "Refresh your credentials (e.g., re-run 'aws sso login')",
            ),
            "ThrottlingException": (
                BedrockErrorType.THROTTLING,
                "Request was throttled by Bedrock",
                "Try again in a few seconds",
            ),
            "ServiceQuotaExceededException": (
                BedrockErrorType.THROTTLING,
                "Bedrock service quota exceeded",
                "Wait a moment or request a quota increase in the AWS console",
            ),
            "ModelTimeoutException": (
                BedrockErrorType.TIMEOUT,
                "Model took too long to respond",
                "Try again — the model may be under heavy load",
            ),
            "ModelNotReadyException": (
                BedrockErrorType.MODEL_NOT_AVAILABLE,
                "The model is not ready to serve requests",
                "Wait a few minutes and try again",
            ),
            "ResourceNotFoundException": (
                BedrockErrorType.MODEL_NOT_AVAILABLE,
                "Model not found — it may not be available in your region",
                (f"Verify that model '{self.model_id}' is enabled in region '{self.region}'"),
            ),
            "ValidationException": (
                BedrockErrorType.INVALID_RESPONSE,
                "Request validation failed",
                "Try rephrasing your request with fewer special characters",
            ),
        }

        if error_code in error_map:
            err_type, msg, suggestion = error_map[error_code]
            return BedrockError(
                msg,
                error_type=err_type,
                suggestion=suggestion,
                technical_detail=str(exc),
            )

        return BedrockError(
            f"AWS error: {error_code}",
            error_type=BedrockErrorType.GENERIC,
            suggestion="Check AWS service status and try again",
            technical_detail=str(exc),
        )

    def _build_user_message(self, intent: Intent) -> str:
        """Build the user message for Bedrock."""
        from datetime import date, timedelta

        today = date.today()
        seven_days_ago = today - timedelta(days=7)

        return f"""Input: "{intent.raw_input}"

Language detected: {intent.detected_language}
Service detected: {intent.service}
Action detected: {intent.action}
Region: {intent.region or "default (us-east-1)"}
Today's date: {today.isoformat()}
Seven days ago: {seven_days_ago.isoformat()}
Response language: ALL user-facing text MUST be in "{intent.detected_language}"

Translate this to an AWS CLI command. Return ONLY the JSON object."""

    def _extract_json(self, text: str) -> dict[str, Any]:
        """Extract JSON from Claude's response (handles markdown code blocks)."""
        text = text.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])

        result: dict[str, Any] = json.loads(text)
        return result
