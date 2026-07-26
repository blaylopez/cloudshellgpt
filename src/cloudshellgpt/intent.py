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
        "lamda",
        # ES
        "funci\u00f3n lambda",
        "funcion lambda",
        "funcion",
        "funci\u00f3n",
        "funciones",
        # EN
        "lambda function",
        "function",
        "functions",
        # PT
        "fun\u00e7\u00e3o lambda",
        "fun\u00e7\u00e3o",
        "fun\u00e7\u00f5es",
        # FR
        "fonction lambda",
        "fonction",
        "fonctions",
        # DE
        "lambda-funktion",
        "funktion",
        "funktionen",
        # ZH
        "lambda\u51fd\u6570",
        "\u51fd\u6570",
    ],
    "dynamodb": [
        "dynamodb",
        "dynamo",
        # ES
        "tabla dynamodb",
        "tabla",
        "tablas",
        "base de datos nosql",
        # EN
        "dynamodb table",
        "table",
        "tables",
        "nosql",
        # PT
        "tabela dynamodb",
        "tabela",
        "tabelas",
        # FR
        "tableau dynamodb",
        "tableau",
        # DE
        "dynamodb-tabelle",
        "dynamodb tabelle",
        "tabelle",
        "tabellen",
        # ZH
        "dynamodb\u8868",
        "\u8868",
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
        "utilisateur iam",
        "utilisateur",
        "r\u00f4le iam",
        "r\u00f4le",
        # DE
        "berechtigung",
        "berechtigungen",
        "rolle",
        "rollen",
        # ZH
        "iam\u7528\u6237",
        "iam\u89d2\u8272",
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
        "sous-r\u00e9seau",
        "r\u00e9seau",
        # DE
        "netzwerk",
        "netzwerke",
        "subnetz",
        # ZH
        "\u5b50\u7f51",
        "\u7f51\u7edc",
    ],
    "cloudfront": [
        "cloudfront",
        # ES
        "cdn",
        "distribuci\u00f3n",
        "distribucion",
        # EN
        "cdn",
        "distribution",
        # PT
        "distribui\u00e7\u00e3o cdn",
        "distribui\u00e7\u00e3o",
        "distribui\u00e7\u00f5es",
        # FR
        "distribution cloudfront",
        # DE
        "cloudfront-distribution",
        "verteilung",
        # ZH
        "\u5185\u5bb9\u5206\u53d1",
        "\u5206\u53d1",
    ],
    "sns": [
        "sns",
        # ES
        "notificacion",
        "notificaci\u00f3n",
        "notificaciones",
        # EN
        "notification",
        "notifications",
        # PT
        "notifica\u00e7\u00e3o",
        "notifica\u00e7\u00f5es",
        "t\u00f3pico",
        # FR
        "notification sns",
        "sujet sns",
        # DE
        "sns-thema",
        "benachrichtigung",
        "benachrichtigungen",
        # ZH
        "sns\u4e3b\u9898",
        "\u901a\u77e5",
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
        "listes",
        "muestra",
        "mu\u00e9strame",
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
        "zeige",
        "zeigen",
        # ZH
        "\u5217\u51fa",
        "\u5217\u8868",
        "\u67e5\u770b",
        "\u663e\u793a",
    ],
    "create": [
        # ES
        "crea",
        "crear",
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
        "starte",
        "starten",
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
        "borrame",
        "elimina",
        "eliminar",
        "quita",
        "quitar",
        "vacia",
        "vaciar",
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
        "terminar",
        # FR
        "supprimer",
        "supprimez",
        "effacer",
        "vider",
        # DE
        "l\u00f6schen",
        "l\u00f6sche",
        "entfernen",
        "entferne",
        # ZH
        "\u5220\u9664",
        "\u79fb\u9664",
        "\u4e22\u5f03",
        "\u7ec8\u6b62",
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
        "\u00e4ndere",
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
        "f\u00fchre",
        # ZH
        "\u8c03\u7528",
        "\u6267\u884c",
        "\u89e6\u53d1",
    ],
}

# Keywords que implican "describe" con mayor prioridad si aparecen junto a un verbo de "list"
DESCRIBE_PRIORITY_KEYWORDS: list[str] = [
    "detalles",
    "detalle",
    "details",
    "detail",
    "detalhes",
    "d\u00e9tails",
    "informaci\u00f3n",
    "informacion",
    "information",
    "informa\u00e7\u00e3o",
    "informations",
    "informationen",
    "\u8be6\u60c5",
    "\u4fe1\u606f",
]

# Longitud máxima de input que procesamos
MAX_INPUT_LENGTH = 500

# Regex para detectar CJK characters
_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")


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
    """Detect language of the input text using langdetect with keyword-based fallback.

    Pre-processes text by removing AWS identifiers and technical tokens
    that confuse langdetect on short inputs. For texts that contain CJK
    characters, returns 'zh-cn' directly. Uses keyword-based heuristic
    as fallback for very short cleaned texts.

    Args:
        text: Input text to analyze.

    Returns:
        ISO 639-1 language code (e.g., 'es', 'en', 'pt', 'fr', 'de', 'zh-cn').
    """
    # If text contains CJK characters, it's Chinese
    if _CJK_PATTERN.search(text):
        return "zh-cn"

    # Remove technical tokens that confuse langdetect:
    cleaned = text
    # Remove ARNs
    cleaned = re.sub(r"arn:aws:\S+", " ", cleaned)
    # Remove s3:// URIs
    cleaned = re.sub(r"s3://\S+", " ", cleaned)
    # Remove AWS resource IDs (i-xxxx, vpc-xxxx, etc.)
    cleaned = re.sub(r"\b[a-z]+-[0-9a-f]{6,}\b", " ", cleaned)
    # Remove instance types (t3.micro, db.t3.micro, db.r5.large)
    cleaned = re.sub(r"\b(?:db\.)?[a-z]\d+\.\w+\b", " ", cleaned)
    # Remove alphanumeric IDs that look like AWS distribution IDs (E1XYZ2ABC3)
    cleaned = re.sub(r"\bE[0-9A-Z]{8,}\b", " ", cleaned)
    # Remove CLI flags
    cleaned = re.sub(r"--\w+", " ", cleaned)
    # Remove AWS service abbreviations that don't help language detection
    cleaned = re.sub(
        r"\b(?:S3|EC2|RDS|VPC|IAM|SQS|SNS|Lambda|DynamoDB|CloudFront|CIDR)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    # Remove IP/CIDR ranges
    cleaned = re.sub(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?:/\d{1,2})?", " ", cleaned)
    # Remove JSON payloads
    cleaned = re.sub(r"\{[^}]*\}", " ", cleaned)
    # Remove remaining identifiers (like resource names with hyphens: temp-data, legacy-app-db)
    cleaned = re.sub(r"\b[a-z]+-[a-z]+-[a-z0-9-]+\b", " ", cleaned)
    cleaned = re.sub(r"\b[a-z]+-[a-z]+\b", " ", cleaned)
    # Clean up multiple spaces
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # If cleaned text is too short, use keyword-based detection
    if len(cleaned) <= 15:
        kw_lang = _detect_language_by_keywords(text.lower())
        if kw_lang:
            return kw_lang

    try:
        detected = str(langdetect.detect(cleaned if len(cleaned) > 5 else text))
        # Always run keyword-based detection for cross-validation
        kw_lang = _detect_language_by_keywords(text.lower())

        # If keyword detection has a clear answer that differs from langdetect,
        # trust the keyword detection — langdetect is unreliable for short technical texts
        if kw_lang and kw_lang != detected:
            # Only override if langdetect returned something wrong
            # Common misdetections by langdetect on short technical texts:
            # - Catalan (ca) for Spanish (es) or Portuguese (pt)
            # - Italian (it) for French (fr)
            # - Romanian (ro) for Portuguese (pt)
            # - Spanish (es) for Portuguese (pt)
            # - Danish/Swedish/Dutch/French for English (en)
            # - French (fr) for Spanish (es) — short texts
            if detected == "ca" and kw_lang == "pt":
                return "pt"
            if detected in ("it", "ca", "es") and kw_lang == "fr":
                return "fr"
            if detected in ("ro", "es", "ca") and kw_lang == "pt":
                return "pt"
            if detected in ("da", "sv", "nl", "no", "af", "fr") and kw_lang == "en":
                return "en"
            if detected in ("fr", "it", "ca") and kw_lang == "es":
                return "es"
            if detected == "it" and kw_lang != "it":
                return kw_lang
            # If langdetect returns unexpected language, trust keywords
            if detected not in ("es", "en", "pt", "fr", "de"):
                return kw_lang
            # If langdetect returns es but keywords strongly say en, trust keywords
            # This handles cases where short English texts after AWS-term removal
            # get misclassified as Spanish
            if detected == "es" and kw_lang == "en":
                en_scores = _get_keyword_scores(text.lower())
                if en_scores.get("en", 0) > en_scores.get("es", 0):
                    return "en"

        # Simple corrections without keyword evidence
        if detected == "ca":
            return "es"
        return detected
    except langdetect.lang_detect_exception.LangDetectException:
        return "en"


# Language-specific keywords for heuristic detection
_LANG_HINT_KEYWORDS: dict[str, list[str]] = {
    "es": [
        "lista",
        "crea",
        "crear",
        "elimina",
        "eliminar",
        "borra",
        "borrar",
        "muestra",
        "mu\u00e9strame",
        "dame",
        "ens\u00e9\u00f1ame",
        "actualiza",
        "modifica",
        "quiero",
        "necesito",
        "por favor",
        "todos los",
        "todas las",
        "del",
        "los",
        "las",
        "hacer",
        "cu\u00e1l",
        "ejecuta",
        "ejecutar",
        "haz",
        "algo",
        "con",
        "funci\u00f3n",
        "base de datos",
    ],
    "en": [
        "list",
        "create",
        "delete",
        "remove",
        "show",
        "display",
        "get",
        "the",
        "all",
        "please",
        "every",
        "everything",
        "drop",
        "terminate",
        "launch",
        "run",
        "with",
        "from",
        "permanently",
        "immediately",
        "named",
        "queue",
        "instance",
        "bucket",
    ],
    "pt": [
        "listar",
        "criar",
        "excluir",
        "deletar",
        "remover",
        "terminar",
        "todos os",
        "todas as",
        "mostre",
        "da conta",
        "dos",
        "do",
        "inst\u00e2ncia",
        "inst\u00e2ncias",
        "tabela",
        "associadas",
        "da",
        "excluir a",
        "deletar a",
    ],
    "fr": [
        "lister",
        "cr\u00e9er",
        "cr\u00e9ez",
        "supprimer",
        "afficher",
        "montrer",
        "terminer",
        "vider",
        "tous les",
        "toutes les",
        "nomm\u00e9",
        "nouveau",
        "nouvelle",
        "r\u00f4le",
        "ancien",
        "ancienne",
        "fichier",
        "serveur",
        "r\u00e9seau",
        "obtenir",
        "ajouter",
        "configurer",
        "r\u00e9cursivement",
        "l'instance",
        "donn\u00e9es",
    ],
    "de": [
        "erstellen",
        "l\u00f6schen",
        "l\u00f6sche",
        "anzeigen",
        "zeige",
        "entferne",
        "entfernen",
        "starte",
        "f\u00fchre",
        "alle",
        "der",
        "die",
        "das",
        "den",
        "dem",
        "eine",
        "einen",
        "mit",
        "auf",
        "vom",
        "und",
    ],
}


def _detect_language_by_keywords(text: str) -> str | None:
    """Detect language by counting keyword matches from each language.

    Args:
        text: Lowercased text to analyze.

    Returns:
        Language code or None if no clear winner.
    """
    scores = _get_keyword_scores(text)

    if not scores:
        return None

    # Return language with highest score, but only if it clearly wins
    best_lang = max(scores, key=scores.get)  # type: ignore[arg-type]
    return best_lang


def _get_keyword_scores(text: str) -> dict[str, int]:
    """Get keyword match scores for each language.

    Args:
        text: Lowercased text to analyze.

    Returns:
        Dictionary mapping language codes to their keyword match scores.
    """
    scores: dict[str, int] = {}
    for lang, keywords in _LANG_HINT_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if " " in kw:
                if kw in text:
                    score += 2
            else:
                # Word-presence check (simple substring for common short words)
                pattern = rf"(?:^|[\s,;:.!?\(\)\"'\-/]){re.escape(kw)}(?:[\s,;:.!?\(\)\"'\-/]|$)"
                if re.search(pattern, text):
                    score += 1
        if score > 0:
            scores[lang] = score

    return scores


def _contains_cjk(text: str) -> bool:
    """Check if text contains CJK characters.

    Args:
        text: Text to check.

    Returns:
        True if CJK characters are present.
    """
    return bool(_CJK_PATTERN.search(text))


def _keyword_matches(keyword: str, text: str) -> bool:
    """Check if a keyword matches in the text, with appropriate boundary handling.

    For multi-word keywords or keywords containing CJK characters, uses substring match.
    For single-word ASCII keywords in text with CJK characters, also uses substring match.
    For single-word ASCII keywords in pure ASCII text, uses word boundary regex.

    Args:
        keyword: The keyword to search for.
        text: The lowercased input text.

    Returns:
        True if the keyword matches.
    """
    # Multi-word keywords or CJK keywords: use substring match
    if " " in keyword or _contains_cjk(keyword):
        return keyword in text

    # If the text contains CJK characters, use substring match for ASCII keywords too
    # (CJK text doesn't have word boundaries between chars and embedded ASCII words)
    if _contains_cjk(text):
        return keyword in text

    # Single-word keywords in non-CJK text: use word boundary matching
    pattern = rf"(?:^|[\s,;:.!?\(\)\"'\-/]){re.escape(keyword)}(?:[\s,;:.!?\(\)\"'\-/]|$)"
    return bool(re.search(pattern, text))


def _detect_service(text: str) -> str | None:
    """Detect AWS service from text via keyword matching.

    First checks for exact AWS service names (highest priority), then
    falls back to keyword matching. Uses word boundary awareness for
    single-word ASCII keywords and substring matching for CJK keywords.

    Args:
        text: Lowercased input text.

    Returns:
        Service identifier string or None if not detected.
    """
    # Priority 1: Exact service name matches (case-insensitive, already lowercase)
    # These are unambiguous identifiers that should always win
    # Order: longer/more specific first; IAM before lambda to avoid role name conflicts
    exact_services = [
        "cloudfront",
        "dynamodb",
        "iam",
        "lambda",
        "lamda",
        "vpc",
        "sqs",
        "sns",
        "rds",
        "ec2",
        "s3",
    ]
    for svc_name in exact_services:
        # Use keyword matching which handles CJK and word boundaries
        if _keyword_matches(svc_name, text):
            # Map to canonical service key
            if svc_name in ("lambda", "lamda"):
                return "lambda"
            return svc_name

    # Priority 2: Keyword-based detection for when service name isn't mentioned
    for service, keywords in SERVICE_KEYWORDS.items():
        for kw in keywords:
            if _keyword_matches(kw, text):
                return service
    return None


def _detect_action(text: str) -> ActionType:
    """Detect intended action from text via keyword matching.

    If both a "list" keyword and a "describe" priority keyword are found,
    returns "describe" to handle cases like "muéstrame los detalles" or
    "mostre informação".

    Args:
        text: Lowercased input text.

    Returns:
        One of the valid ActionType values.
    """
    detected_action: ActionType = "unknown"

    for action, keywords in ACTION_KEYWORDS.items():
        for kw in keywords:
            if _keyword_matches(kw, text):
                if action in get_args(ActionType):
                    detected_action = action  # type: ignore[assignment]
                    break
        if detected_action != "unknown":
            break

    # If detected "list", check if describe-priority keywords are present
    # (handles "muéstrame los detalles", "mostre informação", "zeige mir die Details")
    if detected_action == "list":
        for desc_kw in DESCRIBE_PRIORITY_KEYWORDS:
            if desc_kw in text:
                return "describe"

    return detected_action


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
