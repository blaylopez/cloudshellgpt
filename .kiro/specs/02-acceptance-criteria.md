# CloudShellGPT — Acceptance Criteria

## Definition of Done (DoD)

El proyecto está completo cuando:

- [x] CLI instalable con `pip install cloudshellgpt` o `uv tool install`
- [x] Funciona offline (con cache) si Bedrock no está disponible
- [x] README claro con quick start < 5 minutos
- [x] Tests unitarios con > 80% coverage
- [x] Tests E2E con AWS real (sandbox account)
- [x] Documentación de IAM permissions necesarias
- [x] Licencia clara (Apache 2.0)
- [x] CI/CD con GitHub Actions
- [x] Demo video de 5 minutos grabado

---

## Feature 1: Natural Language Translation

### AC-1.1: Basic intent parsing
- **Given:** Input "lista los buckets de S3"
- **When:** Parser processes
- **Then:** Retorna Intent con action=list, service=s3, confidence > 0.85

### AC-1.2: Multi-language support
- **Given:** Input en ES, EN, PT, FR, DE, ZH
- **When:** Parser processes
- **Then:** Detecta idioma correctamente y mantiene intención

### AC-1.3: Ambiguity handling
- **Given:** Input ambiguo como "muéstrame las cosas"
- **When:** Parser processes
- **Then:** Retorna clarification_needed con pregunta específica

### AC-1.4: Context preservation
- **Given:** Comando previo: "lista lambdas"
- **When:** Usuario dice "muéstrame solo las que fallaron"
- **Then:** Contexto se preserva, genera filtro --status=Failed

---

## Feature 2: AWS Execution

### AC-2.1: Subprocess execution
- **Given:** Comando AWS CLI generado
- **When:** Executor runs
- **Then:** Output retornado en < 30s, errores capturados

### AC-2.2: Streaming output
- **Given:** Comando de larga duración (S3 sync)
- **When:** Executor runs
- **Then:** Output se streama en tiempo real (no buffering)

### AC-2.3: Timeout handling
- **Given:** Comando que excede timeout
- **When:** Timeout reached
- **Then:** Proceso se mata, error claro al usuario

### AC-2.4: Boto3 fallback
- **Given:** Comando CLI falla
- **When:** Fallback triggered
- **Then:** Reintenta con Boto3 equivalente

---

## Feature 3: Safety Layer

### AC-3.1: Destructive command detection
- **Given:** Comando `aws s3 rm --bucket prod-data --recursive`
- **When:** Safety check runs
- **Then:** Risk level = critical, requires confirmation = true

### AC-3.2: Cost estimation
- **Given:** Comando que crea recursos (EC2, RDS)
- **When:** Cost preview runs
- **Then:** Muestra costo mensual estimado antes de ejecutar

### AC-3.3: Dry-run mode
- **Given:** Comando con side effects
- **When:** --dry-run flag set
- **Then:** Ejecuta con flags de dry-run del servicio, no modifica nada

### AC-3.4: Confirmation prompt
- **Given:** Riesgo = high
- **When:** Pre-execution
- **Then:** Muestra diff, espera confirmación typed (no solo Y/N)

### AC-3.5: PII detection
- **Given:** Output contiene emails, SSN, tarjetas de crédito
- **When:** Comprehend check enabled
- **Then:** Redacta PII y muestra warning

---

## Feature 4: Cost Preview

### AC-4.1: Real-time cost
- **Given:** Comando que crea EC2 t3.medium
- **When:** Cost preview runs
- **Then:** Muestra "$30.37/month" basado en Cost Explorer

### AC-4.2: Cumulative tracking
- **Given:** Sesión con 5 comandos que crean recursos
- **When:** User runs `csgpt cost-summary`
- **Then:** Muestra total acumulado de la sesión

### AC-4.3: Budget alert
- **Given:** Costo estimado > $100
- **When:** Pre-execution
- **Then:** Warning explícito + doble confirmación

---

## Feature 5: Learning Mode

### AC-5.1: Explain command
- **Given:** Comando ejecutado exitosamente
- **When:** User runs `csgpt explain last`
- **Then:** Muestra qué hace cada flag, link a docs

### AC-5.2: Interactive tutorial
- **Given:** User corre `csgpt learn s3`
- **When:** Tutorial starts
- **Then:** Secuencia de 5 ejemplos con explicaciones

### AC-5.3: Quiz mode
- **Given:** User complete tutorial
- **When:** Quiz starts
- **Then:** 10 preguntas, feedback inmediato

---

## Feature 6: MCP Server (para Kiro/Claude/Cursor)

### AC-6.1: Server startup
- **Given:** `csgpt mcp serve`
- **When:** Server starts
- **Then:** Expone tools via stdio transport

### AC-6.2: Tool: aws_translate
- **Input:** `{intent: string, language?: string}`
- **Output:** `{command, explanation, risk_level, estimated_cost}`

### AC-6.3: Tool: aws_execute
- **Input:** `{command: string, dry_run?: bool}`
- **Output:** `{stdout, stderr, exit_code, duration_ms}`

### AC-6.4: Tool: aws_cost_preview
- **Input:** `{command: string}`
- **Output:** `{estimated_monthly_cost, breakdown, warnings}`

### AC-6.5: Tool: aws_explain
- **Input:** `{command: string}`
- **Output:** `{explanation, flags_breakdown, docs_links}`

---

## Feature 7: Output Formatting

### AC-7.1: Table format
- **Given:** Output de list operation
- **When:** TTY detected
- **Then:** Renderiza tabla Rich con colores

### AC-7.2: JSON output
- **Given:** Pipe o flag --output json
- **When:** Formatter runs
- **Then:** Output es JSON válido parseable

### AC-7.3: CSV export
- **Given:** Flag --output csv
- **When:** Formatter runs
- **Then:** Output es CSV con headers

### AC-7.4: Search/filter
- **Given:** Output largo + user types `/`
- **When:** Interactive mode
- **Then:** Activa search fuzzy

---

## Quality Gates

### Performance
- P50 latency < 1.5s (parse + translate + execute)
- P95 latency < 5s
- Memory footprint < 150MB
- Startup time < 500ms

### Reliability
- Uptime del servicio Bedrock asumido 99.9%
- Graceful degradation si Bedrock down (cache local)
- No data loss: audit log siempre escribe antes de ejecutar

### Compatibility
- Python 3.12+
- macOS, Linux, Windows (WSL2)
- bash, zsh, fish shells
- AWS CLI v2 instalado (recomendado pero no requerido)

### Observability
- Audit log local en `~/.csgpt/audit.log`
- Opcional: CloudWatch Logs via SDK
- Métricas opcionales (opt-in): comandos ejecutados, costos estimados

---

## Out of Scope (v1.0)

- ❌ GUI / TUI interactivo (solo CLI)
- ❌ Multi-cuenta simultáneo
- ❌ Terraform / CDK generation
- ❌ Deploy automation
- ❌ Cost optimization recommendations
- ❌ Security posture assessment
- ❌ Custom LLM fine-tuning
