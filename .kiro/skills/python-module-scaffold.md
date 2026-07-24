---
inclusion: fileMatch
fileMatchPattern: "src/cloudshellgpt/**/*.py"
---

# Skill: Python Module Scaffold

Genera un nuevo módulo Python para CloudShellGPT siguiendo la estructura y convenciones del proyecto.

## Cuándo usar

Cuando necesites crear un nuevo archivo `.py` en `src/cloudshellgpt/` o agregar estructura base a un módulo existente.

## Estructura obligatoria del módulo

Todo módulo DEBE seguir este orden exacto:

```python
"""<Descripción en una línea del propósito del módulo.>"""

from __future__ import annotations

# Standard library imports
import logging
from typing import Any

# Third-party imports
import boto3
from pydantic import BaseModel, Field

# Local imports
from cloudshellgpt.config import Config

# Constants (UPPER_SNAKE_CASE)
DEFAULT_TIMEOUT: int = 30
MODULE_NAME: str = "module_name"


# Pydantic models
class MyModel(BaseModel):
    """Descripción del modelo.

    Attributes:
        field_name: Descripción del campo.
    """

    field_name: str = Field(..., description="Descripción del campo")
    optional_field: str | None = Field(default=None, description="Campo opcional")


# Classes (PascalCase)
class MyClass:
    """Descripción de la clase.

    Args:
        config: Configuración del módulo.
    """

    def __init__(self, config: Config | None = None) -> None:
        """Initialize MyClass."""
        self._config = config

    def public_method(self, arg: str) -> str:
        """Descripción del método público.

        Args:
            arg: Descripción del argumento.

        Returns:
            Descripción del retorno.

        Raises:
            MyModuleError: Si algo falla.
        """
        return self._helper(arg)

    def _helper(self, arg: str) -> str:
        """Helper privado."""
        return arg


# Public functions (snake_case)
def public_function(param: str) -> str:
    """Descripción de la función pública.

    Args:
        param: Descripción del parámetro.

    Returns:
        Descripción del retorno.
    """
    return _private_helper(param)


# Private helpers (_prefixed)
def _private_helper(param: str) -> str:
    """Helper privado."""
    return param
```

## Reglas obligatorias

1. **`from __future__ import annotations`** en la primera línea después del docstring
2. **Type annotations** en TODAS las funciones (parámetros + retorno)
3. **Docstrings Google style** en todas las clases y métodos públicos (Args, Returns, Raises)
4. **Pydantic BaseModel** para todo dato que cruza fronteras entre módulos
5. **`Field(..., description="...")`** para campos no obvios
6. **Excepciones custom** por módulo (ej: `BedrockError`, `ExecutorError`)
7. **Nunca swallow exceptions** silently — log o re-raise
8. **Line length:** máximo 100 caracteres
9. **Naming:**
   - Classes: PascalCase
   - Functions/methods: snake_case
   - Constants: UPPER_SNAKE_CASE
   - Private: prefijo `_`
   - Modules: snake_case
10. **Tipos modernos:** `str | None`, `list[str]`, `dict[str, Any]` (no Optional, List, Dict)

## Excepciones custom — patrón

```python
class ModuleNameError(Exception):
    """Error base del módulo."""

    def __init__(self, message: str, details: str | None = None) -> None:
        self.details = details
        super().__init__(message)
```

## Boto3 — patrón

```python
# Siempre especificar region_name explícitamente
client = boto3.client("service-name", region_name=self._region)

# Nunca usar boto3.resource() — usar boto3.client()
# Manejar botocore.exceptions.ClientError con mensajes claros
```
