# CloudShellGPT — Arquitectura Técnica

## Diagrama de Alto Nivel

```
┌─────────────────────────────────────────────────────────────────┐
│                     USER TERMINAL (bash/zsh/fish)                │
│                              │                                    │
│                              ▼                                    │
│                  ┌───────────────────────┐                        │
│                  │   csgpt CLI (Python)  │                        │
│                  │  ┌─────────────────┐  │                        │
│                  │  │  Intent Parser  │  │                        │
│                  │  └────────┬────────┘  │                        │
│                  │           │           │                        │
│                  │  ┌────────▼────────┐  │                        │
│                  │  │  Context Mgr    │  │                        │
│                  │  │  (creds, region, │  │                        │
│                  │  │   last commands)│  │                        │
│                  │  └────────┬────────┘  │                        │
│                  └───────────┼───────────┘                        │
│                              │                                    │
│                              ▼                                    │
│                  ┌───────────────────────┐                        │
│                  │  Bedrock Translator   │                        │
│                  │  (Claude 3.5 Sonnet)  │                        │
│                  └───────────┬───────────┘                        │
│                              │                                    │
│                              ▼                                    │
│                  ┌───────────────────────┐                        │
│                  │   Safety Layer        │                        │
│                  │  • Risk classifier    │                        │
│                  │  • Cost estimator     │                        │
│                  │  • Dry-run validator  │                        │
│                  └───────────┬───────────┘                        │
│                              │                                    │
│                              ▼                                    │
│                  ┌───────────────────────┐                        │
│                  │   AWS Executor        │                        │
│                  │  • subprocess (CLI)   │                        │
│                  │  • boto3 (fallback)   │                        │
│                  │  • timeout + retry    │                        │
│                  └───────────┬───────────┘                        │
│                              │                                    │
│                              ▼                                    │
│                  ┌───────────────────────┐                        │
│                  │   Formatter & Logger  │                        │
│                  │  • Rich output        │                        │
│                  │  • JSON / Table       │                        │
│                  │  • Audit log (local)  │                        │
│                  └───────────────────────┘                        │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Stack Tecnológico Detallado

### Core (Local)
```toml
[project]
name = "cloudshellgpt"
version = "1.0.0"
requires-python = ">=3.12"
dependencies = [
    "typer>=0.12.0",          # CLI framework
    "rich>=13.7.0",           # Terminal UI
    "boto3>=1.34.0",          # AWS SDK
    "botocore>=1.34.0",
    "mcp>=1.0.0",             # Model Context Protocol
    "pydantic>=2.5.0",        # Validación
    "httpx>=0.27.0",          # HTTP async
    "pyyaml>=6.0.1",          # Config
]
```

### AWS Services Consumidos
| Servicio | Propósito | Región |
|---|---|---|
| Amazon Bedrock | Traducción intent → CLI | us-east-1 (Claude 3.5 Sonnet) |
| AWS Cost Explorer | Predicción de costos | us-east-1 |
| AWS CloudTrail | Audit de comandos ejecutados | Multi-region |
| Amazon Comprehend | Detección de PII en outputs | us-east-1 |
| Amazon Translate | Multi-idioma (fallback si Bedrock falla) | us-east-1 |

## Componentes Detallados

### 1. Intent Parser (`csgpt/intent.py`)
- Recibe input en lenguaje natural
- Detecta idioma automáticamente
- Extrae entidades (recurso, región, filtros, acción)
- Genera un "intent object" estructurado

```python
class Intent(BaseModel):
    action: Literal["list", "create", "delete", "update", "describe", "invoke"]
    service: str  # "s3", "ec2", "lambda", "dynamodb"
    resource_type: str | None
    filters: dict[str, Any]
    region: str | None
    confidence: float  # 0.0-1.0
    raw_input: str
    detected_language: str
```

### 2. Bedrock Translator (`csgpt/bedrock_translator.py`)
- Convierte Intent → AWS CLI command
- Sistema de prompts con few-shot examples
- Manejo de errores y re-prompting
- Cache de traducciones comunes (DynamoDB o local)

```python
SYSTEM_PROMPT = """
Eres un experto en AWS. Tu trabajo es traducir intenciones en lenguaje natural
a comandos AWS CLI exactos.

Reglas:
1. SIEMPRE devuelve un JSON con: {command, explanation, risk_level, estimated_cost}
2. Si la intención es ambigua, pide clarificación (return clarification_needed: true)
3. Si la acción es destructiva, marca risk_level: "high"
4. Usa flags modernos (--output json, --no-paginate cuando aplique)
5. Prefiere queries con filtros server-side sobre client-side

Ejemplo:
Input: "lista los buckets de S3 que nadie ha tocado en 6 meses"
Output: {
  "command": "aws s3api list-objects-v2 --bucket $BUCKET --query 'Contents[?LastModified<=`2024-01-01`].[Key]'",
  "explanation": "Lista objetos modificados por última vez antes del 1 de enero 2024",
  "risk_level": "low",
  "estimated_cost": "$0.00"
}
"""
```

### 3. Safety Layer (`csgpt/safety.py`)
- Clasificador de riesgo (low/medium/high/critical)
- Estimador de costos via Cost Explorer
- Generador de dry-run commands
- Detector de PII en outputs (Comprehend)

```python
class SafetyCheck(BaseModel):
    risk_level: Literal["low", "medium", "high", "critical"]
    requires_confirmation: bool
    requires_dry_run: bool
    estimated_cost_usd: float
    warnings: list[str]
    affected_resources: list[str]
    reversible: bool
```

### 4. AWS Executor (`csgpt/executor.py`)
- Wrapper sobre subprocess con timeouts
- Streaming de output en tiempo real
- Captura de errores estructurados
- Retry exponencial para errores transitorios

### 5. Formatter (`csgpt/formatter.py`)
- Output con Rich (tablas, syntax highlighting, progress bars)
- Modos: human (default), json, yaml, csv
- Auto-detección de TTY vs pipe
- Soporte para paginación (less-compatible)

## Data Flow — Caso de Uso Completo

```
USER: csgpt "lista los buckets de S3 que nadie ha tocado en 6 meses"

1. Intent Parser
   - Detecta idioma: ES
   - Extrae: service=s3, action=list, filter=last_modified<=6_months_ago
   - Confidence: 0.94

2. Bedrock Translator
   - Envía a Claude 3.5 Sonnet con few-shot
   - Recibe: aws s3api list-buckets + loop con head-object
   - Risk: low, Cost: $0.00

3. Safety Layer
   - Risk: low (read-only)
   - No confirmation needed
   - No dry-run needed

4. AWS Executor
   - Ejecuta: aws s3api list-buckets
   - Para cada bucket: aws s3api list-objects-v2 --max-items 1
   - Filtra por LastModified

5. Formatter
   - Renderiza tabla Rich con columnas: Bucket, LastModified, Size
   - Color coding: rojo si > 6 meses
   - Opción de exportar a CSV

OUTPUT:
┌──────────────────────┬─────────────────────┬──────────┐
│ Bucket               │ Last Modified       │ Size     │
├──────────────────────┼─────────────────────┼──────────┤
│ old-logs-prod        │ 2023-04-12 10:23:01 │ 4.2 GB   │
│ archive-2019         │ 2019-11-03 08:15:44 │ 1.1 TB   │
│ dev-test-bucket      │ 2025-07-15 14:22:09 │ 2.1 MB   │
└──────────────────────┴─────────────────────┴──────────┘
3 buckets found. 2 have not been modified in > 6 months.
```

## Performance Considerations

- **Latency target:** P95 < 3s para traducción simple
- **Concurrency:** Async I/O para múltiples AWS calls
- **Caching:** Local SQLite para traducciones recurrentes
- **Streaming:** Output chunks tan pronto lleguen
- **Timeout:** 30s por comando AWS (configurable)

## Security Model

- **Credentials:** Solo usa AWS credentials del environment (no nuevas)
- **Least privilege:** Documenta IAM permissions recomendadas
- **Audit:** Todos los comandos ejecutados se loguean local + opcionalmente CloudTrail
- **No data exfiltration:** Comprehend PII detection es opcional y opt-in
- **MCP server:** Si se expone, requiere auth token (Bearer)

## Extensibilidad

- **Plugins:** Comandos custom via entry_points
- **Custom prompts:** Los usuarios pueden añadir system prompts
- **Aliases:** `csgpt ls buckets` = `csgpt "lista los buckets"`
- **Themes:** Colores customizables para el formatter
