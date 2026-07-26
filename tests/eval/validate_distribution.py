"""Valida que el eval set cumple los mínimos de distribución antes de correr el eval."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

# ============================================================
# Constantes — umbrales mínimos de distribución
# ============================================================

EVAL_FILE = Path(__file__).parent / "translation_eval.yaml"

MIN_TOTAL_CASES = 100

MIN_PER_LANGUAGE: dict[str, int] = {
    "es": 15,
    "en": 15,
    "pt": 15,
    "fr": 15,
    "de": 15,
    "zh": 15,
}

MIN_PER_SERVICE: dict[str, int] = {
    "s3": 8,
    "ec2": 8,
    "lambda": 8,
    "iam": 8,
    "rds": 8,
    "dynamodb": 8,
    "vpc": 8,
    "sqs": 8,
    "sns": 8,
    "cloudfront": 8,
}

MIN_PER_ACTION: dict[str, int] = {
    "list": 12,
    "create": 12,
    "delete": 12,
    "update": 8,
    "describe": 8,
    "invoke": 5,
}

MIN_PER_RISK: dict[str, int] = {
    "low": 25,
    "medium": 25,
    "high": 25,
    "critical": 15,
}

MIN_EDGE_CASES = 10


# ============================================================
# Funciones
# ============================================================


def load_eval_cases(path: Path) -> list[dict[str, Any]]:
    """Carga los casos del eval set desde un archivo YAML.

    Args:
        path: Ruta al archivo YAML del eval set.

    Returns:
        Lista de diccionarios con los casos de evaluación.

    Raises:
        FileNotFoundError: Si el archivo no existe.
        yaml.YAMLError: Si el YAML es inválido.
    """
    with path.open("r", encoding="utf-8") as f:
        cases = yaml.safe_load(f)
    if not isinstance(cases, list):
        raise ValueError(f"Se esperaba una lista de casos, se obtuvo: {type(cases).__name__}")
    return cases


def normalize_language(lang: str) -> str:
    """Normaliza el código de idioma para conteo (zh-cn → zh).

    Args:
        lang: Código de idioma del caso.

    Returns:
        Código normalizado (primeras 2 letras en minúsculas).
    """
    return lang.lower().split("-")[0][:2]


def count_distributions(cases: list[dict[str, Any]]) -> dict[str, Counter[str]]:
    """Cuenta la distribución de casos por cada dimensión.

    Args:
        cases: Lista de casos del eval set.

    Returns:
        Diccionario con contadores por dimensión.
    """
    languages: Counter[str] = Counter()
    services: Counter[str] = Counter()
    actions: Counter[str] = Counter()
    risks: Counter[str] = Counter()
    edge_count = 0

    for case in cases:
        lang = normalize_language(case.get("language", ""))
        languages[lang] += 1

        service = case.get("expected_service", "").lower()
        services[service] += 1

        action = case.get("expected_action", "").lower()
        actions[action] += 1

        risk = case.get("expected_risk", "").lower()
        risks[risk] += 1

        case_id = case.get("id", "")
        if case_id.upper().startswith("EDGE-"):
            edge_count += 1

    return {
        "languages": languages,
        "services": services,
        "actions": actions,
        "risks": risks,
        "edge_cases": Counter({"edge": edge_count}),
    }


def validate_dimension(
    name: str,
    counts: Counter[str],
    minimums: dict[str, int],
) -> list[str]:
    """Valida una dimensión contra sus mínimos requeridos.

    Args:
        name: Nombre de la dimensión para reportar.
        counts: Conteos actuales por categoría.
        minimums: Mínimos requeridos por categoría.

    Returns:
        Lista de mensajes de fallo (vacía si todo pasa).
    """
    failures: list[str] = []
    for category, minimum in minimums.items():
        actual = counts.get(category, 0)
        if actual < minimum:
            deficit = minimum - actual
            failures.append(f"  ✗ {name}/{category}: {actual}/{minimum} (faltan {deficit})")
    return failures


def validate_distribution(cases: list[dict[str, Any]]) -> tuple[bool, str]:
    """Valida que los casos cumplen todos los mínimos de distribución.

    Args:
        cases: Lista de casos del eval set.

    Returns:
        Tupla (passed, report) donde passed es True si todos los mínimos se cumplen,
        y report es el texto del reporte completo.
    """
    total = len(cases)
    distributions = count_distributions(cases)
    all_failures: list[str] = []
    report_lines: list[str] = []

    report_lines.append("=" * 60)
    report_lines.append("  EVAL SET DISTRIBUTION VALIDATION REPORT")
    report_lines.append("=" * 60)
    report_lines.append("")

    # Total
    report_lines.append(f"Total cases: {total} (minimum: {MIN_TOTAL_CASES})")
    if total < MIN_TOTAL_CASES:
        msg = f"  ✗ total: {total}/{MIN_TOTAL_CASES} (faltan {MIN_TOTAL_CASES - total})"
        all_failures.append(msg)
        report_lines.append(msg)
    else:
        report_lines.append(f"  ✓ total: {total}/{MIN_TOTAL_CASES}")
    report_lines.append("")

    # Idiomas
    report_lines.append("Languages:")
    for lang, minimum in MIN_PER_LANGUAGE.items():
        actual = distributions["languages"].get(lang, 0)
        status = "✓" if actual >= minimum else "✗"
        report_lines.append(f"  {status} {lang}: {actual}/{minimum}")
    failures = validate_dimension("languages", distributions["languages"], MIN_PER_LANGUAGE)
    all_failures.extend(failures)
    report_lines.append("")

    # Servicios
    report_lines.append("Services:")
    for svc, minimum in MIN_PER_SERVICE.items():
        actual = distributions["services"].get(svc, 0)
        status = "✓" if actual >= minimum else "✗"
        report_lines.append(f"  {status} {svc}: {actual}/{minimum}")
    failures = validate_dimension("services", distributions["services"], MIN_PER_SERVICE)
    all_failures.extend(failures)
    report_lines.append("")

    # Acciones
    report_lines.append("Actions:")
    for action, minimum in MIN_PER_ACTION.items():
        actual = distributions["actions"].get(action, 0)
        status = "✓" if actual >= minimum else "✗"
        report_lines.append(f"  {status} {action}: {actual}/{minimum}")
    failures = validate_dimension("actions", distributions["actions"], MIN_PER_ACTION)
    all_failures.extend(failures)
    report_lines.append("")

    # Riesgo
    report_lines.append("Risk levels:")
    for risk, minimum in MIN_PER_RISK.items():
        actual = distributions["risks"].get(risk, 0)
        status = "✓" if actual >= minimum else "✗"
        report_lines.append(f"  {status} {risk}: {actual}/{minimum}")
    failures = validate_dimension("risks", distributions["risks"], MIN_PER_RISK)
    all_failures.extend(failures)
    report_lines.append("")

    # Edge cases
    edge_count = distributions["edge_cases"]["edge"]
    report_lines.append("Edge cases:")
    status = "✓" if edge_count >= MIN_EDGE_CASES else "✗"
    report_lines.append(f"  {status} edge: {edge_count}/{MIN_EDGE_CASES}")
    if edge_count < MIN_EDGE_CASES:
        deficit = MIN_EDGE_CASES - edge_count
        msg = f"  ✗ edge_cases/edge: {edge_count}/{MIN_EDGE_CASES} (faltan {deficit})"
        all_failures.append(msg)
    report_lines.append("")

    # Resultado final
    report_lines.append("-" * 60)
    passed = len(all_failures) == 0
    if passed:
        report_lines.append("✓ PASSED — All distribution minimums met.")
    else:
        report_lines.append(f"✗ FAILED — {len(all_failures)} dimension(s) below minimum:")
        report_lines.extend(all_failures)
    report_lines.append("")

    report = "\n".join(report_lines)
    return passed, report


def main() -> int:
    """Punto de entrada principal para ejecución standalone.

    Returns:
        0 si todos los mínimos se cumplen, 1 si alguno falla.
    """
    if not EVAL_FILE.exists():
        print(f"ERROR: Eval file not found: {EVAL_FILE}")
        return 1

    cases = load_eval_cases(EVAL_FILE)
    passed, report = validate_distribution(cases)
    print(report)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
