"""Intent parser — converts natural language into structured Intent objects."""
from __future__ import annotations

from typing import Any, Literal

import langdetect
from pydantic import BaseModel, Field


class Intent(BaseModel):
    """Structured representation of user's natural language request."""

    action: Literal["list", "create", "delete", "update", "describe", "invoke", "unknown"]
    service: str = Field(..., description="AWS service short name (s3, ec2, lambda, etc.)")
    resource_type: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    region: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    raw_input: str
    detected_language: str = "en"
    suggestion: str | None = None
    clarification_needed: bool = False
    clarification_question: str | None = None


class IntentParser:
    """Parses natural language into structured Intent objects.

    Uses a hybrid approach:
    1. Rule-based keyword detection for high-confidence cases
    2. Fallback to Bedrock for ambiguous inputs
    """

    SERVICE_KEYWORDS = {
        "s3": ["s3", "bucket", "buckets", "objeto", "objetos", "almacenamiento"],
        "ec2": ["ec2", "instancia", "instances", "vm", "servidor", "server"],
        "lambda": ["lambda", "funcion", "function", "función"],
        "dynamodb": ["dynamodb", "dynamo", "tabla", "table", "nosql"],
        "iam": ["iam", "usuario", "user", "rol", "role", "permisos", "permissions"],
        "rds": ["rds", "database", "base de datos", "postgres", "mysql", "aurora"],
        "vpc": ["vpc", "red", "network", "subnet", "subnets"],
        "cloudfront": ["cloudfront", "cdn", "distribucion"],
        "sns": ["sns", "topic", "notificacion", "notification"],
        "sqs": ["sqs", "queue", "cola"],
    }

    ACTION_KEYWORDS = {
        "list": ["lista", "list", "muestra", "show", "muéstrame", "ver", "dame"],
        "create": ["crea", "create", "haz", "genera", "nuevo", "new", "provisiona"],
        "delete": ["borra", "delete", "elimina", "quita", "remove"],
        "update": ["actualiza", "update", "modifica", "change", "cambia"],
        "describe": ["describe", "describe", "info", "informacion", "detalles", "details"],
        "invoke": ["invoca", "invoke", "ejecuta", "execute", "llama", "call"],
    }

    def parse(self, text: str, region: str | None = None) -> Intent:
        """Parse natural language text into an Intent.

        Args:
            text: The natural language input
            region: Optional default region

        Returns:
            Intent object with detected action, service, and metadata
        """
        text_lower = text.lower().strip()

        # Detect language
        try:
            detected_lang = langdetect.detect(text)
        except langdetect.lang_detect_exception.LangDetectException:
            detected_lang = "en"

        # Detect service via keywords
        service = self._detect_service(text_lower)
        action = self._detect_action(text_lower)

        # Calculate confidence (rule-based)
        confidence = 0.0
        if service and action != "unknown":
            confidence = 0.85
        elif service or action != "unknown":
            confidence = 0.5
        else:
            confidence = 0.2

        # Build suggestion if low confidence
        suggestion = None
        if confidence < 0.5:
            suggestion = self._suggestion(text, service, action)

        return Intent(
            action=action,
            service=service or "unknown",
            confidence=confidence,
            raw_input=text,
            detected_language=detected_lang,
            region=region,
            suggestion=suggestion,
        )

    def _detect_service(self, text: str) -> str | None:
        """Detect AWS service from text via keyword matching."""
        for service, keywords in self.SERVICE_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                return service
        return None

    def _detect_action(self, text: str) -> str:
        """Detect intended action from text via keyword matching."""
        for action, keywords in self.ACTION_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                return action
        return "unknown"

    def _suggestion(self, text: str, service: str | None, action: str) -> str:
        """Generate a helpful suggestion when intent is unclear."""
        return (
            f"Try being more specific. Example: 'list the S3 buckets' "
            f"or 'create a new EC2 instance t3.micro'"
        )
