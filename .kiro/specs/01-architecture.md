# CloudShellGPT — Arquitectura Técnica

## Diagrama de Alto Nivel

```
User input (natural language, any language)
    │
    ▼
IntentParser (src/cloudshellgpt/intent.py)
    → Detecta idioma (langdetect), servicio, acción
    → Returns Intent (Pydantic model)
    │
    ▼
BedrockTranslator (src/cloudshellgpt/bedrock_translator.py)
    → Envía Intent a Claude 3.5 Sonnet via Converse API
    → Returns Translation (command + metadata)
    │
    ▼
SafetyLayer (src/cloudshellgpt/safety.py)
    → Evalúa risk level independientemente del LLM
    → Detecta patrones destructivos
    → Consume CostEstimate para decidir alertas
    → Returns SafetyCheck
    │
    ▼
CostTracker (src/cloudshellgpt/cost.py)
    → Consulta Cost Explorer, estima por servicio
    → Genera breakdown por componente
    → Returns CostEstimate
    │
    ▼
AWSExecutor (src/cloudshellgpt/executor.py)
    → Valida: solo `aws`, sin shell metacharacters
    → Ejecuta via subprocess con timeout
    → Returns ExecutionResult
    │
    ▼
Formatter (src/cloudshellgpt/formatter.py)
    → Renderiza output como table/json/yaml/csv
    → Auto-detecta TTY vs pipe
    │
    ▼
AuditLogger (src/cloudshellgpt/audit.py)
    → Log ANTES de ejecución a ~/.csgpt/audit.log
    → Nunca crashea el flujo del usuario

LearningMode (src/cloudshellgpt/learning.py) [opcional, paralelo]
    → Tips educativos post-ejecución
    → Sugerencias de comandos relacionados
    → Explicación de flags usados

MCP Server (src/cloudshellgpt/mcp_server.py) [modo alternativo]
    → stdio transport, stateless
    → Tools: aws_translate, aws_execute, aws_cost_preview, aws_explain
```

## Stack Tecnológico

### Dependencies Core

| Paquete | Propósito |
|---------|-----------|
| `typer>=0.12.0` | CLI framework (commands, flags, help text) |
| `rich>=13.7.0` | Terminal UI (tables, panels, colors, progress) |
| `boto3>=1.34.0` | AWS SDK (Bedrock, Cost Explorer) |
| `pydantic>=2.5.0` | Data validation y modelos entre módulos |
| `pydantic-settings>=2.1.0` | Settings management |
| `mcp>=1.0.0` | Model Context Protocol server |
| `langdetect>=1.0.9` | Detección de idioma para multi-lang |
| `pyyaml>=6.0.1` | Config file (`~/.csgpt/config.yaml`) |
| `httpx>=0.27.0` | HTTP async client |

### Dependencies Dev

| Paquete | Propósito |
|---------|-----------|
| `pytest>=8.0.0` | Test runner |
| `pytest-cov>=4.1.0` | Coverage reporting |
| `pytest-asyncio>=0.23.0` | Async test support |
| `moto[all]>=5.0.0` | AWS mocking (nunca hit real AWS en unit tests) |
| `ruff>=0.4.0` | Linter + formatter |
| `mypy>=1.10.0` | Type checker strict mode |
| `pre-commit>=3.7.0` | Git hooks |

### AWS Services Consumidos

| Servicio | Propósito | Región |
|----------|-----------|--------|
| Amazon Bedrock | Traducción intent → CLI (Converse API) | us-east-1 |
| AWS Cost Explorer | Predicción/estimación de costos | us-east-1 |
| Amazon Comprehend | Detección de PII en outputs (opt-in) | us-east-1 |

### IAM Permissions Requeridas (para CloudShellGPT)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BedrockAccess",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": "arn:aws:bedrock:*::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0"
    },
    {
      "Sid": "CostExplorer",
      "Effect": "Allow",
      "Action": [
        "ce:GetCostAndUsage",
        "ce:GetCostForecast"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ComprehendPII",
      "Effect": "Allow",
      "Action": [
        "comprehend:DetectPiiEntities"
      ],
      "Resource": "*"
    }
  ]
}
```

> Los permisos para los servicios que el usuario opera (S3, EC2, etc.) son SEPARADOS — son los que ya tiene en su environment.

## Componentes Detallados

### 1. CLI Entry Point (`src/cloudshellgpt/cli.py`)

Framework: Typer. Entry point registrado como `csgpt` en pyproject.toml.

Comandos principales:
- `csgpt "<natural language>"` — flujo completo (parse → translate → safety → execute)
- `csgpt explain <command>` — explica un comando AWS
- `csgpt cost-summary` — resumen de costos de la sesión
- `csgpt learn <service>` — tutorial interactivo
- `csgpt mcp serve` — inicia MCP server

### 2. Intent Parser (`src/cloudshellgpt/intent.py`)

Recibe input en lenguaje natural, detecta idioma con `langdetect`, extrae entidades.

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

### 3. Bedrock Translator (`src/cloudshellgpt/bedrock_translator.py`)

Convierte Intent → AWS CLI command via Amazon Bedrock.

**Reglas de configuración (aws-conventions steering):**
- Model ID: `anthropic.claude-3-5-sonnet-20241022-v2:0`
- API: Siempre Converse API (`client.converse()`), nunca `invoke_model`
- SDK: `boto3.client("bedrock-runtime", region_name=self.region)` — siempre region explícita
- Temperature por caso de uso:
  - 0.2 → translation (precisión máxima)
  - 0.3 → explanation (más creativo)
- Max tokens por tipo de intención:
  - `translation` (NL → AWS CLI): 2048
  - `explanation`: 1024
  - `code_generation` (Lambda, IaC): 4096
  - `architecture_review`: 4096
  - Default para intenciones nuevas: 4096
- System prompts: definidos como constantes de clase, nunca hardcoded inline
- Manejo de `BedrockError` con mensaje user-facing

```python
class Translation(BaseModel):
    command: str
    explanation: str
    detailed_explanation: str
    risk_level: Literal["low", "medium", "high", "critical"]
    estimated_cost: str
    requires_dry_run: bool
    affected_resources: list[str]
    flags_used: list[str]
```

### 4. Safety Layer (`src/cloudshellgpt/safety.py`)

Clasificador de riesgo INDEPENDIENTE del LLM. Nunca confiar ciegamente en `risk_level` de Bedrock — verificar con pattern matching propio.

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

**Regla clave:** Puede UPGRADAR el risk respecto al LLM, nunca DOWNGRADAR.

Ver spec `04-safety-security.md` para detalle completo.

### 5. Cost Tracker (`src/cloudshellgpt/cost.py`)

Responsabilidad compartida con safety:
- **cost.py** — lógica de cálculo: Cost Explorer API, estimación por servicio, breakdown
- **safety.py** — consume resultado para alertar/bloquear según `max_cost_alert` en config

Si Cost Explorer API falla → retorna estado "unknown" → safety muestra "costo desconocido — proceder con precaución".

```python
class CostEstimate(BaseModel):
    estimated_monthly_cost: float
    breakdown: list[dict[str, Any]]  # componente por componente
    warnings: list[str]
    status: Literal["estimated", "unknown"]
```

### 6. AWS Executor (`src/cloudshellgpt/executor.py`)

Ejecuta SOLO comandos que comienzan con `aws`. Validaciones estrictas antes de ejecución.

```python
class ExecutionResult(BaseModel):
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    dry_run: bool
```

**Reglas del executor (aws-conventions + safety-patterns steerings):**
- Solo comandos `aws ...` puros
- Timeout: 30s default, configurable
- Shell injection prevention: rechaza `|`, `&&`, `||`, `;`, `` ` ``, `$()`, `>`, `>>`, `<`, `&`, `\n`, `\0`, `<<`, `<(...)`, `>(...)`, `$VAR`, `${VAR}`
- Excepción: argumento literal `-` (stdin/stdout) es válido
- Retry exponencial para throttling/timeouts transitorios
- Dry-run injection para servicios que lo soportan
- **Audit ANTES de ejecución** (log intent antes de correr el comando)

### 7. Formatter (`src/cloudshellgpt/formatter.py`)

Output con Rich. Modos: `table` (default), `json`, `yaml`, `csv`.
- Auto-detección de TTY vs pipe
- Color coding según contexto
- Soporte para paginación

### 8. Audit Logger (`src/cloudshellgpt/audit.py`)

Log a `~/.csgpt/audit.log`.

**Reglas críticas:**
- Escribe ANTES de ejecutar el comando (log → execute, nunca al revés)
- NUNCA debe crashear el flujo del usuario (catch all exceptions silently)
- Nunca loguear PII

```python
# Orden correcto:
audit.log(intent, command, risk)  # 1. Log first
result = executor.run(command)  # 2. Execute second
```

### 9. Learning Mode (`src/cloudshellgpt/learning.py`)

Opcional (config: `enable_learning_mode`). Paralelo al flujo principal.
- Tips educativos post-ejecución
- Sugerencias de comandos relacionados
- Explicación de flags usados en el comando traducido
- Tutorial interactivo por servicio (`csgpt learn s3`)

### 10. Config Manager (`src/cloudshellgpt/config.py`)

Configuración en `~/.csgpt/config.yaml`. Usa Pydantic Settings para validación.

```yaml
region: us-east-1          # default Bedrock region
language: auto             # auto-detect con langdetect
default_output: table      # table|json|yaml|csv
bedrock_model: anthropic.claude-3-5-sonnet-20241022-v2:0
require_confirmation_for: [high, critical]
enable_cost_preview: true
enable_learning_mode: true
max_cost_alert: 100        # USD, int sin símbolo
```

### 11. MCP Server (`src/cloudshellgpt/mcp_server.py`)

Servidor MCP via stdio transport. Ver spec `05-mcp-server.md` para detalle completo.

**Reglas fundamentales:**
- Stateless — sin contexto entre tool calls
- Cada handler instancia sus propias dependencias
- Siempre retorna `list[TextContent]` con JSON string
- Catch ALL exceptions — nunca crashear el server
- Handlers son `async`

## Key Data Models (Contratos entre módulos)

| Modelo | Produce | Consume |
|--------|---------|---------|
| `Intent` | IntentParser | BedrockTranslator |
| `Translation` | BedrockTranslator | SafetyLayer, CLI |
| `SafetyCheck` | SafetyLayer | CLI (confirmation flow) |
| `CostEstimate` | CostTracker | SafetyLayer, CLI |
| `ExecutionResult` | AWSExecutor | Formatter |
| `Config` | ConfigManager | Todos los módulos |

> Todos deben ser Pydantic BaseModel. Cambiar campos requiere coordinación con owner del módulo consumidor.

## Module Structure (code-style steering)

Cada módulo sigue este orden:
1. Module docstring (una línea)
2. `from __future__ import annotations`
3. Standard library imports
4. Third-party imports
5. Local imports (`from cloudshellgpt.*`)
6. Constants (UPPER_SNAKE_CASE)
7. Pydantic models
8. Classes (PascalCase)
9. Public functions (snake_case)
10. Private helpers (`_prefixed`)

## Data Flow — Ejemplo Completo

```
USER: csgpt "lista los buckets de S3 que nadie ha tocado en 6 meses"

1. CLI (cli.py)
   - Recibe input, invoca IntentParser

2. IntentParser (intent.py)
   - langdetect → idioma: ES
   - Extrae: service=s3, action=list, filter=last_modified<=6_months_ago
   - Confidence: 0.94
   - Output: Intent

3. BedrockTranslator (bedrock_translator.py)
   - Converse API, temperature=0.2, max_tokens=2048
   - Recibe: command + explanation + risk_level + flags
   - Output: Translation

4. SafetyLayer (safety.py)
   - Verifica INDEPENDIENTEMENTE del LLM
   - Risk: low (list = read-only)
   - No confirmation needed, no dry-run
   - Output: SafetyCheck

5. CostTracker (cost.py)
   - Sin costo de recursos (read-only)
   - Output: CostEstimate(status="estimated", cost=0.0)

6. AuditLogger (audit.py)
   - Log ANTES de ejecutar

7. AWSExecutor (executor.py)
   - Valida: empieza con `aws` ✓, no metacharacters ✓
   - Ejecuta, timeout 30s
   - Output: ExecutionResult

8. Formatter (formatter.py)
   - Renderiza tabla Rich: Bucket | LastModified | Size
   - Color coding por antigüedad

9. LearningMode (learning.py) [si enabled]
   - Tip: "Usa `aws s3api list-objects-v2 --query` para filtrar server-side"
```

## Performance

| Aspecto | Target |
|---------|--------|
| P50 latency (parse + translate) | < 1.5s |
| P95 latency (flujo completo) | < 5s |
| Memory footprint | < 150MB |
| Startup time | < 500ms |
| Timeout por comando AWS | 30s (configurable) |

## Security Model

- **Credentials:** Solo usa AWS credentials del environment — nunca gestiona propias
- **Least privilege:** Documenta IAM permissions necesarias vs permisos del usuario
- **Shell injection:** Rechaza todos los metacharacters — solo `aws ...` puro
- **LLM distrust:** Safety Layer siempre verifica independientemente, puede upgradar risk, nunca downgradar
- **Audit first:** Log ANTES de ejecutar — registro incluso si el comando crashea
- **PII protection:** Comprehend detection opt-in, redacta antes de mostrar, nunca loguea PII
- **MCP stateless:** Sin state entre calls, cada request es independiente

## Region Strategy

- Default: us-east-1 (donde Bedrock Claude está disponible)
- Override: `--region` flag o `region` en config
- Calls propias de CloudShellGPT (Bedrock, Cost Explorer) → región configurada
- Comandos del usuario → respetan su propia región (env o flag)

## CDK Infrastructure (`infrastructure/`)

- Stack naming: `CloudShellGPT-{Environment}` (e.g., `CloudShellGPT-Prod`)
- Resource naming: `csgpt-{resource}-{environment}`
- DynamoDB: PAY_PER_REQUEST billing
- Lambda: ARM_64, Python 3.12, X-Ray tracing
- Removal policy: RETAIN para prod, DESTROY para dev
- Encryption: AWS_MANAGED para DynamoDB, S3_MANAGED para buckets
