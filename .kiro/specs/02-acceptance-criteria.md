# CloudShellGPT — Acceptance Criteria

## Definition of Done (DoD)

El proyecto está completo cuando:

- [ ] CLI instalable con `pip install cloudshellgpt` o `uv tool install cloudshellgpt`
- [ ] `csgpt --help` muestra todos los comandos disponibles
- [ ] Funciona con AWS credentials del environment (no gestiona propias)
- [ ] README claro con quick start < 5 minutos
- [ ] Tests unitarios con > 80% coverage global, > 90% en safety/executor
- [ ] Tests de integración con AWS real (sandbox account)
- [ ] Documentación de IAM permissions necesarias
- [ ] Licencia Apache 2.0
- [ ] CI/CD con GitHub Actions (ruff + mypy + pytest antes de merge a `dev`)
- [ ] Eval set de 100 casos con > 90% precisión
- [ ] Demo video de 5-7 minutos grabado

---

## Feature 1: Natural Language Translation

### AC-1.1: Basic intent parsing
- **Given:** Input "lista los buckets de S3"
- **When:** IntentParser processes
- **Then:** Retorna Intent con action=list, service=s3, confidence > 0.85, detected_language="es"

### AC-1.2: Multi-language support
- **Given:** Input en ES, EN, PT, FR, DE, ZH
- **When:** IntentParser processes (langdetect)
- **Then:** Detecta idioma correctamente y mantiene la intención original

### AC-1.3: Ambiguity handling
- **Given:** Input ambiguo como "muéstrame las cosas"
- **When:** IntentParser processes
- **Then:** Retorna confidence < 0.7 y `clarification_needed: true` con pregunta específica

### AC-1.4: Bedrock translation accuracy
- **Given:** Intent válido con confidence > 0.85
- **When:** BedrockTranslator traduce via Converse API (temperature=0.2, max_tokens=2048)
- **Then:** Retorna Translation con comando AWS CLI correcto, explanation, risk_level y flags_used

### AC-1.5: Bedrock error handling
- **Given:** Bedrock API falla (timeout, throttling, error)
- **When:** BedrockTranslator catches BedrockError
- **Then:** Muestra mensaje user-facing en español, retry con exponential backoff para transitorios

---

## Feature 2: AWS Execution

### AC-2.1: Command validation
- **Given:** Comando generado por BedrockTranslator
- **When:** AWSExecutor valida
- **Then:** Acepta SOLO si empieza con `aws` y NO contiene shell metacharacters (`|`, `&&`, `||`, `;`, `` ` ``, `$()`, `>`, `>>`, `<`, `&`, `\n`, `\0`, `<<`, `<(...)`, `>(...)`, `$VAR`, `${VAR}`)

### AC-2.2: Valid exception for stdin argument
- **Given:** Comando con argumento literal `-` (ej: `aws s3 cp - s3://bucket/file`)
- **When:** AWSExecutor valida
- **Then:** Acepta el `-` como argumento válido, no lo rechaza como operador shell

### AC-2.3: Subprocess execution
- **Given:** Comando validado
- **When:** AWSExecutor ejecuta via subprocess
- **Then:** Retorna ExecutionResult con stdout, stderr, exit_code, duration_ms en < 30s

### AC-2.4: Timeout handling
- **Given:** Comando que excede timeout (30s default, configurable)
- **When:** Timeout alcanzado
- **Then:** Proceso se mata, retorna error claro con duración excedida

### AC-2.5: Audit before execution
- **Given:** Cualquier comando a ejecutar
- **When:** Pre-ejecución
- **Then:** AuditLogger escribe entrada a `~/.csgpt/audit.log` ANTES de ejecutar el comando

### AC-2.6: Transient error retry
- **Given:** Error transitorio (throttling, timeout de AWS)
- **When:** Executor detecta error transitorio
- **Then:** Retry con exponential backoff, máximo 3 intentos

---

## Feature 3: Safety Layer

### AC-3.1: Risk classification — low
- **Given:** Comando read-only (list, describe, get, head, wait)
- **When:** SafetyLayer evalúa
- **Then:** risk_level="low", requires_confirmation=false, ejecuta directamente

### AC-3.2: Risk classification — medium
- **Given:** Comando create/update con rollback fácil (create-bucket, tag-resource, put-metric-alarm)
- **When:** SafetyLayer evalúa
- **Then:** risk_level="medium", muestra plan + Y/N antes de ejecutar

### AC-3.3: Risk classification — high
- **Given:** Comando delete/terminate/revoke en recurso individual (delete-bucket, terminate-instances)
- **When:** SafetyLayer evalúa
- **Then:** risk_level="high", requires_confirmation=true, muestra recursos afectados + costo, pide confirmación typed

### AC-3.4: Risk classification — critical
- **Given:** Comando con recursive/batch delete o flags force (`--recursive`, `--force-delete`, `--skip-final-snapshot`)
- **When:** SafetyLayer evalúa
- **Then:** risk_level="critical", requires_dry_run=true primero, luego pide "yes-i-understand"

### AC-3.5: Destructive pattern detection
- **Given:** Comando `aws s3 rm s3://prod-data --recursive`
- **When:** SafetyLayer detecta patterns ("delete", "rm", "terminate", "--recursive", "--force")
- **Then:** Upgrada risk independientemente del risk_level que devolvió Bedrock

### AC-3.6: LLM risk independence
- **Given:** Bedrock devuelve risk_level="low" para un comando destructivo
- **When:** SafetyLayer verifica con pattern matching propio
- **Then:** Upgrada a high/critical. NUNCA downgrda por debajo de lo que sugirió el LLM

### AC-3.7: Heurística medium vs high
- **Given:** Operación con inverso directo que no destruye datos (create → delete, attach → detach)
- **When:** SafetyLayer clasifica
- **Then:** Clasifica como "medium"
- **Given:** Operación que elimina datos o acceso y requiere recreación manual
- **When:** SafetyLayer clasifica
- **Then:** Clasifica como "high". En caso de duda, clasificar hacia arriba.

### AC-3.8: Dry-run injection
- **Given:** Comando en lista de servicios con soporte dry-run (ec2, rds, s3api, iam, cloudformation, lambda)
- **When:** Risk es critical
- **Then:** Inyecta `--dry-run` o usa change sets antes de ejecución real

### AC-3.9: Dry-run not supported
- **Given:** Comando para servicio sin soporte nativo de dry-run
- **When:** Risk es high/critical
- **Then:** Muestra el comando SIN ejecutar, pide confirmación explícita

---

## Feature 4: Cost Preview

### AC-4.1: Cost estimation before create
- **Given:** Comando que crea recursos (EC2, RDS, etc.)
- **When:** CostTracker consulta Cost Explorer
- **Then:** Muestra costo mensual estimado con breakdown por componente ANTES de ejecutar

### AC-4.2: Cost Explorer failure
- **Given:** Cost Explorer API falla o no retorna datos
- **When:** CostTracker catches error
- **Then:** Retorna status="unknown", safety muestra "costo desconocido — proceder con precaución"

### AC-4.3: Budget alert
- **Given:** Costo estimado > max_cost_alert (default $100 USD)
- **When:** SafetyLayer consume CostEstimate
- **Then:** Warning explícito + doble confirmación requerida

### AC-4.4: Session tracking
- **Given:** Sesión con múltiples comandos que crean recursos
- **When:** User ejecuta `csgpt cost-summary`
- **Then:** Muestra total acumulado de la sesión

### AC-4.5: Bedrock API cost tracking
- **Given:** Cada request a Bedrock
- **When:** CostTracker registra tokens usados
- **Then:** Incluye costo de API (~$0.003/1K input, ~$0.015/1K output) en session tracking

---

## Feature 5: Learning Mode

### AC-5.1: Post-execution tips
- **Given:** Comando ejecutado exitosamente + `enable_learning_mode: true`
- **When:** LearningMode procesa
- **Then:** Muestra tip educativo, sugiere comandos relacionados, explica flags usados

### AC-5.2: Explain command
- **Given:** `csgpt explain "aws s3api list-objects-v2 --bucket X --query ..."`
- **When:** BedrockTranslator genera explanation (temperature=0.3, max_tokens=1024)
- **Then:** Muestra qué hace cada flag, link a docs

### AC-5.3: Interactive tutorial
- **Given:** `csgpt learn s3`
- **When:** Tutorial inicia
- **Then:** Secuencia de ejemplos con explicaciones progresivas

---

## Feature 6: MCP Server

### AC-6.1: Server startup
- **Given:** `csgpt mcp serve`
- **When:** Server inicia
- **Then:** Expone tools via stdio transport, stateless, handlers async

### AC-6.2: Tool aws_translate
- **Input:** `{intent: string, region?: string}`
- **Output:** `{command, explanation, detailed_explanation, risk_level, estimated_cost, requires_dry_run, affected_resources, flags_used}`
- **Side effects:** Ninguno (read-only translation)

### AC-6.3: Tool aws_execute
- **Input:** `{command: string, dry_run?: boolean}`
- **Output:** `{command, exit_code, stdout, stderr, duration_ms, dry_run}`
- **Side effects:** Ejecuta AWS CLI (potencialmente destructivo)
- **Requisito:** Description DEBE indicar al client que confirme con usuario antes de llamar

### AC-6.4: Tool aws_cost_preview
- **Input:** `{command: string}`
- **Output:** `{command, estimated_cost, risk_level, warnings}`
- **Side effects:** Ninguno

### AC-6.5: Tool aws_explain
- **Input:** `{command: string}`
- **Output:** Markdown explanation text
- **Side effects:** Llama a Bedrock para generar explicación

### AC-6.6: Error handling in MCP
- **Given:** Cualquier excepción en un tool handler
- **When:** Error ocurre
- **Then:** Retorna error como TextContent (never crash the server)

### AC-6.7: Stateless behavior
- **Given:** Múltiples tool calls secuenciales
- **When:** MCP server recibe cada call
- **Then:** Cada handler instancia sus propias dependencias, sin shared state entre calls

---

## Feature 7: Output Formatting

### AC-7.1: Table format (default)
- **Given:** Output de list operation + TTY detectado
- **When:** Formatter procesa con `default_output: table`
- **Then:** Renderiza tabla Rich con colores y headers

### AC-7.2: JSON output
- **Given:** Flag `--output json` o pipe detectado (no TTY)
- **When:** Formatter procesa
- **Then:** Output es JSON válido parseable

### AC-7.3: YAML output
- **Given:** Flag `--output yaml`
- **When:** Formatter procesa
- **Then:** Output es YAML válido

### AC-7.4: CSV export
- **Given:** Flag `--output csv`
- **When:** Formatter procesa
- **Then:** Output es CSV con headers

### AC-7.5: Auto-detect TTY vs pipe
- **Given:** Output se redirige a pipe (`csgpt ... | jq`)
- **When:** Formatter detecta no-TTY
- **Then:** Output automáticamente en JSON sin colores

---

## Feature 8: PII Detection (opt-in)

### AC-8.1: PII redaction
- **Given:** Output contiene PII (emails, SSN, tarjetas) + `enable_pii_detection: true`
- **When:** Comprehend scans stdout post-ejecución
- **Then:** Redacta PII antes de mostrar al usuario

### AC-8.2: PII warning
- **Given:** PII detectado y redactado
- **When:** Formatter muestra output
- **Then:** Warning: "PII detectado y redactado. Usa --show-pii para ver completo."

### AC-8.3: PII never logged
- **Given:** PII detectado en output
- **When:** AuditLogger registra
- **Then:** NUNCA incluye PII en audit.log

---

## Feature 9: Configuration

### AC-9.1: Default config
- **Given:** No existe `~/.csgpt/config.yaml`
- **When:** ConfigManager carga
- **Then:** Usa defaults: region=us-east-1, language=auto, output=table, confirmations=[high, critical]

### AC-9.2: Custom config
- **Given:** `~/.csgpt/config.yaml` con override de region y output
- **When:** ConfigManager carga
- **Then:** Aplica overrides del usuario, mantiene defaults para lo no especificado

### AC-9.3: CLI flag override
- **Given:** Config tiene `region: us-east-1` pero CLI tiene `--region eu-west-1`
- **When:** Comando se ejecuta
- **Then:** Flag CLI tiene precedencia sobre config file

---

## Quality Gates

### Performance
| Aspecto | Target |
|---------|--------|
| P50 latency (parse + translate + execute) | < 1.5s |
| P95 latency | < 5s |
| Memory footprint | < 150MB |
| Startup time | < 500ms |
| Timeout por comando | 30s (configurable) |

### Reliability
- Graceful degradation si Bedrock no disponible (error claro, no crash)
- No data loss: audit log siempre escribe ANTES de ejecutar
- AuditLogger nunca crashea el flujo del usuario
- Retry automático para errores transitorios

### Code Quality (code-style steering)
- Python 3.12+ con type annotations en todas las funciones
- `from __future__ import annotations` en cada módulo
- mypy strict mode sin errores
- ruff sin warnings (rules: E, F, I, N, W, UP, Y, B, A, C4, PT)
- Line length: 100 chars max
- Docstrings Google style en todas las clases y métodos públicos
- Todos los data models son Pydantic BaseModel

### Testing (testing-guide steering)
- Unit tests: pytest + moto (nunca hit real AWS)
- Archivos mirror: `src/cloudshellgpt/intent.py` → `tests/unit/test_intent.py`
- Integration tests marcados con `@pytest.mark.integration`
- Coverage > 80% global, > 90% para safety y executor
- Fixtures en `tests/conftest.py`
- Eval set: 100 casos en `tests/eval/translation_eval.jsonl`

### Compatibility
- Python 3.12+
- macOS, Linux, Windows (WSL2)
- bash, zsh, fish shells
- AWS CLI v2 (recomendado pero no requerido — solo necesario si executor usa subprocess)

---

## Out of Scope (v1.0)

- GUI / TUI interactivo
- Multi-cuenta simultáneo
- Terraform / CDK generation
- Deploy automation
- Cost optimization recommendations
- Security posture assessment
- Custom LLM fine-tuning
- Streaming output (futuro)
- Local translation cache SQLite (futuro)
- Context preservation entre comandos (futuro)
- Boto3 fallback en executor (futuro)
- Quiz mode en learning (futuro)
