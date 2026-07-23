---
inclusion: manual
---

# Skill: Pydantic Model Generator

Genera modelos Pydantic que sirven como contratos entre módulos de CloudShellGPT.

## Cuándo usar

Cuando necesites crear o modificar un modelo de datos que cruce fronteras entre módulos (Intent, Translation, SafetyCheck, CostEstimate, ExecutionResult, Config, o cualquier modelo nuevo).

## Template base

```python
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ModelName(BaseModel):
    """Descripción clara del modelo y su propósito.

    Este modelo es producido por [ModuloA] y consumido por [ModuloB].

    Attributes:
        field_name: Descripción del campo.
    """

    # Campos requeridos primero
    required_field: str = Field(..., description="Qué representa este campo")
    action: Literal["list", "create", "delete", "update"] = Field(
        ..., description="Tipo de acción"
    )

    # Campos con default después
    optional_field: str | None = Field(default=None, description="Campo opcional")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Score de confianza 0-1")
    tags: list[str] = Field(default_factory=list, description="Lista de etiquetas")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Metadata adicional")
```

## Reglas obligatorias

1. **Siempre Pydantic BaseModel** — nunca dataclasses o dicts sueltos para contratos
2. **`Field(...)` con description** para todos los campos no triviales
3. **`Field(...)`** (sin default) para campos requeridos
4. **`default_factory`** para mutable defaults (list, dict, set)
5. **Tipos modernos:** `str | None`, `list[str]`, `dict[str, Any]` — nunca `Optional`, `List`, `Dict`
6. **`Literal[...]`** para enums simples con pocas opciones
7. **Validators con `ge`, `le`, `min_length`, `max_length`** cuando aplique
8. **Immutable donde sea posible** — usar `model_config = ConfigDict(frozen=True)` si el modelo no debe mutar
9. **Docstring de clase** con: descripción, quién produce, quién consume

## Modelos del proyecto — referencia

### Intent (IntentParser → BedrockTranslator)

```python
class Intent(BaseModel):
    """Intención parseada del input del usuario.

    Producido por IntentParser, consumido por BedrockTranslator.
    """

    action: Literal["list", "create", "delete", "update", "describe", "invoke"] = Field(
        ..., description="Acción detectada"
    )
    service: str = Field(..., description="Servicio AWS: s3, ec2, lambda, dynamodb")
    resource_type: str | None = Field(default=None, description="Tipo de recurso específico")
    filters: dict[str, Any] = Field(default_factory=dict, description="Filtros extraídos")
    region: str | None = Field(default=None, description="Región override del usuario")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confianza del parsing 0-1")
    raw_input: str = Field(..., description="Input original del usuario")
    detected_language: str = Field(..., description="Idioma detectado: es, en, pt, fr, de, zh")
```

### Translation (BedrockTranslator → SafetyLayer, CLI)

```python
class Translation(BaseModel):
    """Traducción de intent a comando AWS CLI.

    Producido por BedrockTranslator, consumido por SafetyLayer y CLI.
    """

    command: str = Field(..., description="Comando AWS CLI generado")
    explanation: str = Field(..., description="Explicación breve")
    detailed_explanation: str = Field(..., description="Explicación detallada")
    risk_level: Literal["low", "medium", "high", "critical"] = Field(
        ..., description="Nivel de riesgo evaluado por LLM"
    )
    estimated_cost: str = Field(..., description="Costo estimado como string: $0.00")
    requires_dry_run: bool = Field(default=False, description="Si requiere dry-run")
    affected_resources: list[str] = Field(default_factory=list, description="Recursos afectados")
    flags_used: list[str] = Field(default_factory=list, description="Flags usados en el comando")
```

### SafetyCheck (SafetyLayer → CLI)

```python
class SafetyCheck(BaseModel):
    """Resultado de evaluación de seguridad.

    Producido por SafetyLayer, consumido por CLI para confirmation flow.
    """

    risk_level: Literal["low", "medium", "high", "critical"] = Field(
        ..., description="Nivel de riesgo final (puede ser upgradado vs LLM)"
    )
    requires_confirmation: bool = Field(..., description="Si requiere confirmación del usuario")
    requires_dry_run: bool = Field(..., description="Si debe ejecutar dry-run primero")
    estimated_cost_usd: float = Field(default=0.0, ge=0.0, description="Costo estimado en USD")
    warnings: list[str] = Field(default_factory=list, description="Warnings para mostrar")
    affected_resources: list[str] = Field(default_factory=list, description="Recursos afectados")
    reversible: bool = Field(default=True, description="Si la operación es reversible")
```

### ExecutionResult (AWSExecutor → Formatter)

```python
class ExecutionResult(BaseModel):
    """Resultado de ejecución de comando AWS.

    Producido por AWSExecutor, consumido por Formatter.
    """

    command: str = Field(..., description="Comando ejecutado")
    exit_code: int = Field(..., description="Código de salida del proceso")
    stdout: str = Field(default="", description="Standard output")
    stderr: str = Field(default="", description="Standard error")
    duration_ms: int = Field(..., ge=0, description="Duración en milisegundos")
    dry_run: bool = Field(default=False, description="Si fue ejecución dry-run")
```

### CostEstimate (CostTracker → SafetyLayer, CLI)

```python
class CostEstimate(BaseModel):
    """Estimación de costo de un comando.

    Producido por CostTracker, consumido por SafetyLayer y CLI.
    """

    estimated_monthly_cost: float = Field(default=0.0, ge=0.0, description="Costo mensual USD")
    breakdown: list[dict[str, Any]] = Field(
        default_factory=list, description="Breakdown por componente"
    )
    warnings: list[str] = Field(default_factory=list, description="Advertencias de costo")
    status: Literal["estimated", "unknown"] = Field(
        default="unknown", description="Si el cálculo fue exitoso o falló"
    )
```

## Anti-patterns a evitar

```python
# MAL — dict suelto como contrato
def translate(intent: dict) -> dict: ...

# MAL — Optional de typing
from typing import Optional, List
field: Optional[str] = None
items: List[str] = []

# MAL — sin description en Field
name: str = Field(...)

# MAL — mutable default
tags: list[str] = []  # Bug! Shared entre instancias

# MAL — no usar Field para defaults mutables
data: dict[str, Any] = {}
```

## Cuándo crear un modelo nuevo

- Si un dato cruza de un módulo a otro → **siempre modelo Pydantic**
- Si es interno de un módulo y no sale → puede ser dict o namedtuple
- Si necesitas validación (ranges, patterns, enums) → modelo Pydantic
- Si cambiar el campo afecta a otro módulo → documentar owner + consumidor en docstring
