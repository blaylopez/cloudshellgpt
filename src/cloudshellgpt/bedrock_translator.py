"""Bedrock translator — converts Intent objects into AWS CLI commands via Claude 3.5 Sonnet."""

from __future__ import annotations

import json
from typing import Any

import boto3
from pydantic import BaseModel, Field

from cloudshellgpt.intent import Intent


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


class BedrockTranslator:
    """Translates natural language intents to AWS CLI commands using Amazon Bedrock.

    Uses Claude 3.5 Sonnet via the Bedrock Converse API. Implements a
    few-shot system prompt with best practices for AWS CLI generation.
    """

    MODEL_ID = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    REGION = "us-east-1"

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
   - low: read-only (list, describe, get)
   - medium: create/update reversible
   - high: delete, terminate, force-delete
   - critical: delete recursivo, force sin confirmación, o que afecta producción

4. Comandos destructivos DEBEN marcar requires_dry_run: true

5. Usa flags modernos:
   - --output json por defecto (el usuario quiere parseable)
   - --no-paginate cuando el resultado es chico
   - --query para filtrar server-side
   - --filters en lugar de client-side

6. Idioma: explanation y detailed_explanation en el MISMO idioma del input

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

    def __init__(self, region: str = REGION) -> None:
        self.client = boto3.client("bedrock-runtime", region_name=region)
        self.region = region

    def translate(self, intent: Intent) -> Translation:
        """Translate an Intent into an AWS CLI command.

        Args:
            intent: The parsed user intent

        Returns:
            Translation object with the command and metadata

        Raises:
            BedrockError: If translation fails
        """
        user_message = self._build_user_message(intent)

        try:
            response = self.client.converse(
                modelId=self.MODEL_ID,
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": user_message}],
                    }
                ],
                system=[{"text": self.SYSTEM_PROMPT}],
                inferenceConfig={
                    "maxTokens": 2048,
                    "temperature": 0.2,  # Low temp for precision
                    "topP": 0.9,
                },
            )

            response_text = response["output"]["message"]["content"][0]["text"]
            data = self._extract_json(response_text)

            return Translation(
                command=data["command"],
                explanation=data.get("explanation", ""),
                detailed_explanation=data.get("detailed_explanation", ""),
                risk_level=data.get("risk_level", "low"),
                estimated_cost=data.get("estimated_cost", "$0.00"),
                requires_dry_run=data.get("requires_dry_run", False),
                affected_resources=data.get("affected_resources", []),
                flags_used=data.get("flags_used", {}),
            )

        except Exception as e:
            raise BedrockError(f"Translation failed: {e}") from e

    def _build_user_message(self, intent: Intent) -> str:
        """Build the user message for Bedrock."""
        return f"""Input: "{intent.raw_input}"

Language detected: {intent.detected_language}
Service detected: {intent.service}
Action detected: {intent.action}
Region: {intent.region or "default (us-east-1)"}

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


class BedrockError(Exception):
    """Raised when Bedrock translation fails."""

    pass
