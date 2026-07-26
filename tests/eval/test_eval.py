"""Eval runner — mide precisión del IntentParser sobre el eval set completo."""

from __future__ import annotations

from collections import Counter
from typing import Any

import pytest

from cloudshellgpt.intent import IntentParser

from .validate_distribution import EVAL_FILE, load_eval_cases, normalize_language

# ============================================================
# Constantes
# ============================================================

# Umbrales mínimos de precisión
GLOBAL_PRECISION_THRESHOLD = 0.90
PER_LANGUAGE_PRECISION_THRESHOLD = 0.85

# Idiomas especiales que no se comparan directamente
SPECIAL_LANGUAGES = {"unknown", "mixed"}

# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(scope="module")
def eval_cases() -> list[dict[str, Any]]:
    """Carga todos los casos del eval set.

    Returns:
        Lista de diccionarios con los casos de evaluación.
    """
    return load_eval_cases(EVAL_FILE)


@pytest.fixture(scope="module")
def parser() -> IntentParser:
    """Proporciona una instancia de IntentParser compartida.

    Returns:
        Instancia del parser para ejecutar sobre cada caso.
    """
    return IntentParser()


@pytest.fixture(scope="module")
def eval_results(
    eval_cases: list[dict[str, Any]],
    parser: IntentParser,
) -> list[dict[str, Any]]:
    """Ejecuta IntentParser sobre todos los casos y recopila resultados.

    Args:
        eval_cases: Los casos cargados del YAML.
        parser: Instancia del IntentParser.

    Returns:
        Lista de resultados con campos de comparación por caso.
    """
    results: list[dict[str, Any]] = []
    for case in eval_cases:
        intent = parser.parse(case["input"])
        results.append(
            {
                "id": case["id"],
                "input": case["input"],
                "expected_language": case.get("language", ""),
                "expected_service": case.get("expected_service", ""),
                "expected_action": case.get("expected_action", ""),
                "detected_language": intent.detected_language,
                "detected_service": intent.service,
                "detected_action": intent.action,
                "confidence": intent.confidence,
            }
        )
    return results


# ============================================================
# Helpers
# ============================================================


def _languages_match(expected: str, detected: str) -> bool:
    """Compara idiomas con normalización.

    Maneja variantes como zh-cn/zh-tw → zh y viceversa.

    Args:
        expected: Idioma esperado del caso de evaluación.
        detected: Idioma detectado por langdetect.

    Returns:
        True si los idiomas coinciden tras normalización.
    """
    if expected.lower() in SPECIAL_LANGUAGES:
        # Para idiomas "unknown" o "mixed", aceptamos cualquier detección no vacía
        return bool(detected)
    return normalize_language(expected) == normalize_language(detected)


def _is_edge_case(case_id: str) -> bool:
    """Determina si un caso es un edge case basándose en su ID.

    Args:
        case_id: Identificador del caso.

    Returns:
        True si el caso es un edge case.
    """
    return case_id.upper().startswith("EDGE-")


# ============================================================
# Tests parametrizados por caso individual
# ============================================================


def _get_eval_case_ids() -> list[str]:
    """Carga los IDs de los casos para parametrización.

    Returns:
        Lista de IDs de los casos del eval set.
    """
    cases = load_eval_cases(EVAL_FILE)
    return [case["id"] for case in cases]


def _get_eval_cases_map() -> dict[str, dict[str, Any]]:
    """Carga los casos indexados por ID.

    Returns:
        Diccionario id → caso.
    """
    cases = load_eval_cases(EVAL_FILE)
    return {case["id"]: case for case in cases}


# Precarga para parametrización estática
_CASES_MAP = _get_eval_cases_map()
_CASE_IDS = list(_CASES_MAP.keys())


@pytest.mark.eval
@pytest.mark.parametrize("case_id", _CASE_IDS)
def test_eval_service_detection(case_id: str) -> None:
    """Verifica que IntentParser detecta el servicio correcto para cada caso.

    Args:
        case_id: Identificador del caso de evaluación.
    """
    case = _CASES_MAP[case_id]
    parser = IntentParser()
    intent = parser.parse(case["input"])

    expected_service = case.get("expected_service", "").lower()
    detected_service = intent.service.lower() if intent.service else ""

    # Los edge cases con input vacío/whitespace retornan "unknown" — es aceptable
    if _is_edge_case(case_id) and not case["input"].strip():
        return

    assert detected_service == expected_service, (
        f"[{case_id}] Service mismatch: "
        f"expected='{expected_service}', got='{detected_service}' "
        f"for input: '{case['input'][:80]}...'"
    )


@pytest.mark.eval
@pytest.mark.parametrize("case_id", _CASE_IDS)
def test_eval_action_detection(case_id: str) -> None:
    """Verifica que IntentParser detecta la acción correcta para cada caso.

    Args:
        case_id: Identificador del caso de evaluación.
    """
    case = _CASES_MAP[case_id]
    parser = IntentParser()
    intent = parser.parse(case["input"])

    expected_action = case.get("expected_action", "").lower()
    detected_action = intent.action.lower() if intent.action else ""

    # Los edge cases con input vacío/whitespace retornan "unknown" — es aceptable
    if _is_edge_case(case_id) and not case["input"].strip():
        return

    assert detected_action == expected_action, (
        f"[{case_id}] Action mismatch: "
        f"expected='{expected_action}', got='{detected_action}' "
        f"for input: '{case['input'][:80]}...'"
    )


@pytest.mark.eval
@pytest.mark.parametrize("case_id", _CASE_IDS)
def test_eval_language_detection(case_id: str) -> None:
    """Verifica que IntentParser detecta el idioma correcto para cada caso.

    Args:
        case_id: Identificador del caso de evaluación.
    """
    case = _CASES_MAP[case_id]
    parser = IntentParser()
    intent = parser.parse(case["input"])

    expected_lang = case.get("language", "")
    detected_lang = intent.detected_language or ""

    # Los edge cases con input vacío/whitespace tienen detección trivial
    if _is_edge_case(case_id) and not case["input"].strip():
        return

    assert _languages_match(expected_lang, detected_lang), (
        f"[{case_id}] Language mismatch: "
        f"expected='{expected_lang}' (normalized: '{normalize_language(expected_lang)}'), "
        f"got='{detected_lang}' (normalized: '{normalize_language(detected_lang)}') "
        f"for input: '{case['input'][:80]}...'"
    )


# ============================================================
# Tests agregados — precisión global y por dimensión
# ============================================================


@pytest.mark.eval
def test_eval_aggregate_precision(
    eval_cases: list[dict[str, Any]],
    eval_results: list[dict[str, Any]],
) -> None:
    """Verifica que la precisión global cumple los umbrales mínimos.

    Reporta un resumen con precisión por dimensión (servicio, acción, idioma).
    La precisión de riesgo se excluye porque IntentParser no evalúa riesgo.

    Args:
        eval_cases: Los casos cargados del YAML.
        eval_results: Resultados de ejecutar IntentParser sobre cada caso.
    """
    total = 0
    service_correct = 0
    action_correct = 0
    language_correct = 0

    # Contadores por idioma
    lang_total: Counter[str] = Counter()
    lang_correct_count: Counter[str] = Counter()

    # Contadores por servicio
    svc_total: Counter[str] = Counter()
    svc_correct_count: Counter[str] = Counter()

    # Contadores por acción
    act_total: Counter[str] = Counter()
    act_correct_count: Counter[str] = Counter()

    for result in eval_results:
        case_id = result["id"]

        # Excluir edge cases con input vacío de los agregados
        if _is_edge_case(case_id):
            case = _CASES_MAP.get(case_id, {})
            if not case.get("input", "").strip():
                continue

        total += 1
        expected_lang = result["expected_language"]
        norm_lang = normalize_language(expected_lang)

        # Servicio
        expected_svc = result["expected_service"].lower()
        detected_svc = result["detected_service"].lower()
        svc_match = detected_svc == expected_svc
        if svc_match:
            service_correct += 1
            svc_correct_count[expected_svc] += 1
        svc_total[expected_svc] += 1

        # Acción
        expected_act = result["expected_action"].lower()
        detected_act = result["detected_action"].lower()
        act_match = detected_act == expected_act
        if act_match:
            action_correct += 1
            act_correct_count[expected_act] += 1
        act_total[expected_act] += 1

        # Idioma
        lang_match = _languages_match(expected_lang, result["detected_language"])
        if lang_match:
            language_correct += 1
            lang_correct_count[norm_lang] += 1
        lang_total[norm_lang] += 1

    # Calcular precisiones
    service_precision = service_correct / total if total > 0 else 0.0
    action_precision = action_correct / total if total > 0 else 0.0
    language_precision = language_correct / total if total > 0 else 0.0
    global_precision = (service_precision + action_precision + language_precision) / 3

    # Reporte detallado
    report_lines: list[str] = []
    report_lines.append("")
    report_lines.append("=" * 60)
    report_lines.append("  EVAL PRECISION REPORT - IntentParser")
    report_lines.append("=" * 60)
    report_lines.append(f"  Total cases evaluated: {total}")
    report_lines.append("")
    report_lines.append(f"  Global precision (avg): {global_precision:.1%}")
    report_lines.append(f"    Service precision:    {service_precision:.1%}")
    report_lines.append(f"    Action precision:     {action_precision:.1%}")
    report_lines.append(f"    Language precision:   {language_precision:.1%}")
    report_lines.append("    Risk precision:       N/A (SafetyLayer's job)")
    report_lines.append("")

    # Per-language breakdown
    report_lines.append("  Language breakdown:")
    for lang in sorted(lang_total.keys()):
        lt = lang_total[lang]
        lc = lang_correct_count[lang]
        pct = lc / lt if lt > 0 else 0.0
        status = "PASS" if pct >= PER_LANGUAGE_PRECISION_THRESHOLD else "FAIL"
        report_lines.append(f"    [{status}] {lang}: {lc}/{lt} ({pct:.1%})")
    report_lines.append("")

    # Per-service breakdown
    report_lines.append("  Service breakdown:")
    for svc in sorted(svc_total.keys()):
        st = svc_total[svc]
        sc = svc_correct_count[svc]
        pct = sc / st if st > 0 else 0.0
        report_lines.append(f"    {svc}: {sc}/{st} ({pct:.1%})")
    report_lines.append("")

    # Per-action breakdown
    report_lines.append("  Action breakdown:")
    for act in sorted(act_total.keys()):
        at = act_total[act]
        ac = act_correct_count[act]
        pct = ac / at if at > 0 else 0.0
        report_lines.append(f"    {act}: {ac}/{at} ({pct:.1%})")
    report_lines.append("")
    report_lines.append("=" * 60)

    report = "\n".join(report_lines)
    print(report)

    # Assertions de umbral
    assert global_precision >= GLOBAL_PRECISION_THRESHOLD, (
        f"Global precision {global_precision:.1%} < {GLOBAL_PRECISION_THRESHOLD:.0%} threshold"
    )


@pytest.mark.eval
def test_eval_per_language_precision(
    eval_results: list[dict[str, Any]],
) -> None:
    """Verifica que cada idioma supera el umbral mínimo de precisión.

    Args:
        eval_results: Resultados de ejecutar IntentParser sobre cada caso.
    """
    lang_total: Counter[str] = Counter()
    lang_correct: Counter[str] = Counter()

    for result in eval_results:
        case_id = result["id"]
        if _is_edge_case(case_id):
            case = _CASES_MAP.get(case_id, {})
            if not case.get("input", "").strip():
                continue

        expected_lang = result["expected_language"]
        if expected_lang.lower() in SPECIAL_LANGUAGES:
            continue

        norm_lang = normalize_language(expected_lang)
        lang_total[norm_lang] += 1
        if _languages_match(expected_lang, result["detected_language"]):
            lang_correct[norm_lang] += 1

    failures: list[str] = []
    for lang in sorted(lang_total.keys()):
        lt = lang_total[lang]
        lc = lang_correct[lang]
        precision = lc / lt if lt > 0 else 0.0
        if precision < PER_LANGUAGE_PRECISION_THRESHOLD:
            failures.append(
                f"{lang}: {precision:.1%} ({lc}/{lt}) < {PER_LANGUAGE_PRECISION_THRESHOLD:.0%}"
            )

    assert not failures, (
        f"Languages below {PER_LANGUAGE_PRECISION_THRESHOLD:.0%} threshold:\n"
        + "\n".join(f"  - {f}" for f in failures)
    )
