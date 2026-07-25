"""Intent parser — converts natural language into structured Intent objects."""

from __future__ import annotations

import re
from typing import Any, Literal, get_args

import langdetect
import langdetect.detector_factory
from pydantic import BaseModel, Field

# Seed para determinismo en langdetect
langdetect.detector_factory.LangDetectException = (
    langdetect.lang_detect_exception.LangDetectException
)
langdetect.DetectorFactory.seed = 0

# --- Constants ---

SUPPORTED_LANGUAGES = ("es", "en", "pt", "fr", "de", "zh-cn", "zh-tw", "zh")

ActionType = Literal["list", "create", "delete", "update", "describe", "invoke", "unknown"]

# Keywords por servicio, multi-idioma: ES, EN, PT, FR, DE, ZH
SERVICE_KEYWORDS: dict[str, list[str]] = {
    "s3": [
        "s3",
        "bucket",
        "buckets",
        # ES
        "almacenamiento",
        "objeto",
        "objetos",
        # PT
        "armazenamento",
        "balde",
        # FR
        "stockage",
        "seau",
        # DE
        "speicher",
        "eimer",
        # ZH
        "\u5b58\u50a8\u6876",
        "\u5bf9\u8c61\u5b58\u50a8",
    ],
    "ec2": [
        "ec2",
        "instance",
        "instances",
        # ES
        "instancia",
        "instancias",
        "servidor",
        "servidores",
        # EN
        "server",
        "vm",
        "virtual machine",
        # PT
        "inst\u00e2ncia",
        "inst\u00e2ncias",
        "servidor",
        # FR
        "serveur",
        "machine virtuelle",
        # DE
        "instanz",
        "instanzen",
        # ZH
        "\u5b9e\u4f8b",
        "\u670d\u52a1\u5668",
        "\u865a\u62df\u673a",
    ],
    "lambda": [
        "lambda",
        # ES
        "funcion",
        "funci\u00f3n",
        "funciones",
        # EN
        "function",
        "functions",
        # PT
        "fun\u00e7\u00e3o",
        "fun\u00e7\u00f5es",
        # FR
        "fonction",
        "fonctions",
        # DE
        "funktion",
        "funktionen",
        # ZH
        "\u51fd\u6570",
        "\u529f\u80fd",
    ],
    "dynamodb": [
        "dynamodb",
        "dynamo",
        # ES
        "tabla",
        "tablas",
        "base de datos nosql",
        # EN
        "table",
        "tables",
        "nosql",
        # PT
        "tabela",
        "tabelas",
        # FR
        "tableau",
        # DE
        "tabelle",
        "tabellen",
        # ZH
        "\u8868",
        "\u6570\u636e\u5e93\u8868",
    ],
    "iam": [
        "iam",
        # ES
        "usuario",
        "usuarios",
        "rol",
        "roles",
        "permisos",
        "permiso",
        # EN
        "user",
        "users",
        "role",
        "permission",
        "permissions",
        "policy",
        "policies",
        # PT
        "usu\u00e1rio",
        "usu\u00e1rios",
        "permiss\u00e3o",
        "permiss\u00f5es",
        # FR
        "utilisateur",
        "utilisateurs",
        "r\u00f4le",
        "r\u00f4les",
        "permission",
        # DE
        "benutzer",
        "berechtigung",
        "berechtigungen",
        "rolle",
        "rollen",
        # ZH
        "\u7528\u6237",
        "\u89d2\u8272",
        "\u6743\u9650",
    ],
    "rds": [
        "rds",
        # ES
        "base de datos",
        "bases de datos",
        "postgres",
        "mysql",
        "aurora",
        # EN
        "database",
        "databases",
        # PT
        "banco de dados",
        "bancos de dados",
        # FR
        "base de donn\u00e9es",
        "bases de donn\u00e9es",
        # DE
        "datenbank",
        "datenbanken",
        # ZH
        "\u6570\u636e\u5e93",
        "\u5173\u7cfb\u578b\u6570\u636e\u5e93",
    ],
    "vpc": [
        "vpc",
        # ES
        "red",
        "redes",
        "subred",
        "subredes",
        # EN
        "network",
        "subnet",
        "subnets",
        # PT
        "rede",
        "redes",
        "sub-rede",
        # FR
        "r\u00e9seau",
        "r\u00e9seaux",
        "sous-r\u00e9seau",
        # DE
        "netzwerk",
        "netzwerke",
        "subnetz",
        # ZH
        "\u7f51\u7edc",
        "\u5b50\u7f51",
    ],
    "cloudfront": [
        "cloudfront",
        # ES
        "distribucion",
        "distribuci\u00f3n",
        "cdn",
        # EN
        "distribution",
        "cdn",
        # PT
        "distribui\u00e7\u00e3o",
        # FR
        "distribution",
        # DE
        "verteilung",
        # ZH
        "\u5206\u53d1",
        "\u5185\u5bb9\u5206\u53d1",
    ],
    "sns": [
        "sns",
        # ES
        "notificacion",
        "notificaci\u00f3n",
        "notificaciones",
        "topic",
        "tema",
        # EN
        "notification",
        "notifications",
        "topic",
        # PT
        "notifica\u00e7\u00e3o",
        "notifica\u00e7\u00f5es",
        "t\u00f3pico",
        # FR
        "notification",
        "sujet",
        # DE
        "benachrichtigung",
        "benachrichtigungen",
        "thema",
        # ZH
        "\u901a\u77e5",
        "\u4e3b\u9898",
    ],
    "sqs": [
        "sqs",
        # ES
        "cola",
        "colas",
        # EN
        "queue",
        "queues",
        # PT
        "fila",
        "filas",
        # FR
        "file d'attente",
        "files d'attente",
        # DE
        "warteschlange",
        "warteschlangen",
        # ZH
        "\u961f\u5217",
        "\u6d88\u606f\u961f\u5217",
    ],
}

# Keywords por acción, multi-idioma: ES, EN, PT, FR, DE, ZH
ACTION_KEYWORDS: dict[str, list[str]] = {
    "list": [
        # ES
        "lista",
        "listar",
        "mu\u00e9strame",
        "muestra",
        "mostrar",
        "ver",
        "dame",
        "ens\u00e9\u00f1ame",
        # EN
        "list",
        "show",
        "display",
        "get all",
        "view",
        # PT
        "listar",
        "mostrar",
        "exibir",
        "mostre",
        # FR
        "lister",
        "afficher",
        "montrer",
        "montrez",
        # DE
        "auflisten",
        "anzeigen",
        "zeigen",
        "zeige",
        # ZH
        "\u5217\u51fa",
        "\u663e\u793a",
        "\u67e5\u770b",
        "\u5217\u8868",
    ],
    "create": [
        # ES
        "crea",
        "crear",
        "haz",
        "genera",
        "generar",
        "nuevo",
        "nueva",
        "provisiona",
        # EN
        "create",
        "make",
        "new",
        "provision",
        "generate",
        "launch",
        "start",
        # PT
        "criar",
        "crie",
        "gerar",
        "novo",
        "nova",
        # FR
        "cr\u00e9er",
        "cr\u00e9ez",
        "g\u00e9n\u00e9rer",
        "nouveau",
        "nouvelle",
        # DE
        "erstellen",
        "erstelle",
        "erzeugen",
        "neu",
        # ZH
        "\u521b\u5efa",
        "\u65b0\u5efa",
        "\u751f\u6210",
        "\u542f\u52a8",
    ],
    "delete": [
        # ES
        "borra",
        "borrar",
        "elimina",
        "eliminar",
        "quita",
        "quitar",
        # EN
        "delete",
        "remove",
        "destroy",
        "terminate",
        "drop",
        # PT
        "excluir",
        "deletar",
        "remover",
        "apagar",
        # FR
        "supprimer",
        "supprimez",
        "effacer",
        # DE
        "l\u00f6schen",
        "l\u00f6sche",
        "entfernen",
        # ZH
        "\u5220\u9664",
        "\u79fb\u9664",
        "\u4e22\u5f03",
    ],
    "update": [
        # ES
        "actualiza",
        "actualizar",
        "modifica",
        "modificar",
        "cambia",
        "cambiar",
        # EN
        "update",
        "modify",
        "change",
        "edit",
        "alter",
        # PT
        "atualizar",
        "atualize",
        "modificar",
        "alterar",
        # FR
        "mettre \u00e0 jour",
        "modifier",
        "modifiez",
        "changer",
        # DE
        "\u00e4ndern",
        "aktualisieren",
        "bearbeiten",
        # ZH
        "\u66f4\u65b0",
        "\u4fee\u6539",
        "\u53d8\u66f4",
    ],
    "describe": [
        # ES
        "describe",
        "describir",
        "info",
        "informacion",
        "informaci\u00f3n",
        "detalles",
        "detalle",
        # EN
        "describe",
        "detail",
        "details",
        "info",
        "information",
        # PT
        "descrever",
        "descreva",
        "detalhes",
        "informa\u00e7\u00e3o",
        # FR
        "d\u00e9crire",
        "d\u00e9crivez",
        "d\u00e9tails",
        "informations",
        # DE
        "beschreiben",
        "details",
        "informationen",
        # ZH
        "\u63cf\u8ff0",
        "\u8be6\u60c5",
        "\u4fe1\u606f",
    ],
    "invoke": [
        # ES
        "invoca",
        "invocar",
        "ejecuta",
        "ejecutar",
        "llama",
        "llamar",
        # EN
        "invoke",
        "execute",
        "run",
        "call",
        "trigger",
        # PT
        "invocar",
        "executar",
        "chamar",
        # FR
        "invoquer",
        "ex\u00e9cuter",
        "appeler",
        # DE
        "aufrufen",
        "ausf\u00fchren",
        # ZH
        "\u8c03\u7528",
        "\u6267\u884c",
        "\u89e6\u53d1",
    ],
}

# Longitud máxima de input que procesamos
MAX_INPUT_LENGTH = 500


# --- Pydantic Models ---


class Intent(BaseModel):
    """Structured representation of user's natural language request."""

    action: ActionType
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


# --- Classes ---


class IntentParser:
    """Parses natural language into structured Intent objects.

    Uses a hybrid approach combining rule-based keyword detection with
    language identification via langdetect. For high-confidence cases,
    rule-based matching is sufficient. Ambiguous inputs are flagged for
    potential Bedrock fallback.

    Supports 6 languages: ES, EN, PT, FR, DE, ZH.
    Supports 10 AWS services and 6 action types.
    """

    def parse(self, text: str, region: str | None = None) -> Intent:
        """Parse natural language text into an Intent.

        Args:
            text: The natural language input.
            region: Optional default AWS region.

        Returns:
            Intent object with detected action, service, and metadata.
        """
        # Edge case: empty or whitespace-only input
        if not text or not text.strip():
            return Intent(
                action="unknown",
                service="unknown",
                confidence=0.0,
                raw_input=text or "",
                detected_language="en",
                region=region,
                clarification_needed=True,
                clarification_question=(
                    "No input provided. Please describe what AWS operation you'd like to perform."
                ),
            )

        # Truncate very long input
        original_text = text
        if len(text) > MAX_INPUT_LENGTH:
            text = text[:MAX_INPUT_LENGTH]

        text_lower = text.lower().strip()

        # Detect language with langdetect (seeded for determinism)
        detected_lang = _detect_language(text)

        # Detect service and action via keyword matching
        service = _detect_service(text_lower)
        action = _detect_action(text_lower)

        # Calculate confidence based on detection results
        confidence = _calculate_confidence(service, action)

        # Build suggestion if low confidence
        suggestion: str | None = None
        if confidence < 0.5:
            suggestion = _build_suggestion()

        # AC-1.3: clarification needed when confidence < 0.7
        clarification_needed = confidence < 0.7
        clarification_question: str | None = None
        if clarification_needed:
            clarification_question = _build_clarification_question(service, action)

        return Intent(
            action=action,
            service=service or "unknown",
            confidence=confidence,
            raw_input=original_text,
            detected_language=detected_lang,
            region=region,
            suggestion=suggestion,
            clarification_needed=clarification_needed,
            clarification_question=clarification_question,
        )


# --- Private helpers ---


def _detect_language(text: str) -> str:
    """Detect language of the input text using langdetect.

    Args:
        text: Input text to analyze.

    Returns:
        ISO 639-1 language code (e.g., 'es', 'en', 'pt', 'fr', 'de', 'zh-cn').
    """
    try:
        return str(langdetect.detect(text))
    except langdetect.lang_detect_exception.LangDetectException:
        return "en"


def _detect_service(text: str) -> str | None:
    """Detect AWS service from text via keyword matching.

    Uses word boundary awareness for single-word keywords and
    substring matching for multi-word keywords to reduce false positives.

    Args:
        text: Lowercased input text.

    Returns:
        Service identifier string or None if not detected.
    """
    # TODO: implementar scoring por cantidad de keywords matcheados en vez de "first match wins".
    # Cuando el input contiene keywords de múltiples servicios, el actual retorna el primero
    # que encuentra en el orden del diccionario, lo cual puede ser incorrecto.
    for service, keywords in SERVICE_KEYWORDS.items():
        for kw in keywords:
            if " " in kw:
                # Multi-word keywords: substring match is fine
                if kw in text:
                    return service
            else:
                # Single-word keywords: use word boundary matching
                pattern = rf"(?:^|[\s,;:.!?()\"'\-/]){re.escape(kw)}(?:[\s,;:.!?()\"'\-/]|$)"
                if re.search(pattern, text):
                    return service
    return None


def _detect_action(text: str) -> ActionType:
    """Detect intended action from text via keyword matching.

    Args:
        text: Lowercased input text.

    Returns:
        One of the valid ActionType values.
    """
    for action, keywords in ACTION_KEYWORDS.items():
        for kw in keywords:
            if " " in kw:
                # Multi-word keywords: substring match
                if kw in text:
                    if action in get_args(ActionType):
                        return action  # type: ignore[return-value]
            else:
                # Single-word keywords: word boundary match
                pattern = rf"(?:^|[\s,;:.!?()\"'\-/]){re.escape(kw)}(?:[\s,;:.!?()\"'\-/]|$)"
                if re.search(pattern, text):
                    if action in get_args(ActionType):
                        return action  # type: ignore[return-value]
    return "unknown"


def _calculate_confidence(service: str | None, action: ActionType) -> float:
    """Calculate confidence score based on detection results.

    Args:
        service: Detected service or None.
        action: Detected action type.

    Returns:
        Confidence float between 0.0 and 1.0.
    """
    if service and action != "unknown":
        return 0.9
    if service or action != "unknown":
        return 0.5
    return 0.2


def _build_clarification_question(service: str | None, action: str) -> str:
    """Generate a clarification question when confidence is low.

    Args:
        service: Detected AWS service or None.
        action: Detected action type.

    Returns:
        A specific clarification question for the user.
    """
    if service is None and action == "unknown":
        return "Could you specify which AWS service and what operation you'd like to perform?"
    if service is None:
        return f"Which AWS service would you like to {action}?"
    if action == "unknown":
        return f"What would you like to do with {service}? (list, create, delete, describe)"
    return "Could you provide more details about what you'd like to do?"


def _build_suggestion() -> str:
    """Generate a helpful suggestion when intent is unclear.

    Returns:
        Suggestion string with usage examples.
    """
    return (
        "Try being more specific. Example: 'list the S3 buckets' "
        "or 'create a new EC2 instance t3.micro'"
    )
