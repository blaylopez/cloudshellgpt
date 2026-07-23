# CloudShellGPT — Implementation Plan & Timeline

## Sprint Breakdown (48 horas)

### Sprint 0: Foundation (Hours 0-6)

**Goal:** Repositorio funcional + CI básico + skeleton CLI

#### Tareas
- [ ] Configurar pyproject.toml con todas las deps (typer, rich, boto3, pydantic, mcp, langdetect, pyyaml, httpx)
- [ ] Setup de `uv` como package manager
- [ ] Crear estructura de módulos en `src/cloudshellgpt/`
- [ ] Crear CLI skeleton con Typer (`cli.py` → entry point `csgpt`)
- [ ] Configurar ruff (line-length=100, rules: E, F, I, N, W, UP, Y, B, A, C4, PT)
- [ ] Configurar mypy strict mode
- [ ] Setup de GitHub Actions workflow (ruff check + ruff format + mypy + pytest)
- [ ] Configurar pre-commit hooks
- [ ] Setup de pytest con moto + pytest-cov + pytest-asyncio
- [ ] Crear `tests/conftest.py` con fixtures compartidas
- [ ] **Checkpoint:** `csgpt --help` muestra comandos disponibles

---

### Sprint 1: Intent Parsing + Bedrock Integration (Hours 6-14)

**Goal:** Traducción natural language → AWS CLI funcionando end-to-end

#### Tareas
- [ ] Implementar `Intent` model (Pydantic BaseModel) en `src/cloudshellgpt/intent.py`
- [ ] Implementar IntentParser con langdetect para detección de idioma
- [ ] Implementar `Translation` model en `src/cloudshellgpt/bedrock_translator.py`
- [ ] Cliente Bedrock con Converse API (`client.converse()`, nunca `invoke_model`)
- [ ] System prompts como constantes de clase (nunca inline)
- [ ] Configurar temperature=0.2 para translation, max_tokens=2048
- [ ] Manejo de BedrockError con mensaje user-facing
- [ ] Retry exponencial para errores transitorios
- [ ] Implementar `ConfigManager` en `src/cloudshellgpt/config.py` (Pydantic Settings)
- [ ] Config file: `~/.csgpt/config.yaml` con defaults
- [ ] Tests unitarios para IntentParser (sin mocks AWS)
- [ ] Tests unitarios para BedrockTranslator (mocked boto3)
- [ ] Crear eval set inicial (`tests/eval/translation_eval.jsonl`, 20 casos mínimo)
- [ ] **Checkpoint:** `csgpt "lista los buckets de S3"` traduce correctamente

---

### Sprint 2: Safety Layer + Cost (Hours 14-22)

**Goal:** Sistema de seguridad robusto con cost preview

#### Tareas
- [ ] Implementar `SafetyCheck` model en `src/cloudshellgpt/safety.py`
- [ ] Risk classifier rule-based (low/medium/high/critical)
- [ ] Implementar DESTRUCTIVE_PATTERNS list completa
- [ ] Heurística: inverso directo → medium, destruye datos → high, duda → upgrade
- [ ] LLM independence: upgradar risk vs Bedrock, nunca downgradar
- [ ] Implementar `CostEstimate` model en `src/cloudshellgpt/cost.py`
- [ ] Cost estimator con AWS Cost Explorer API
- [ ] Integración safety ↔ cost: safety consume CostEstimate para alertar según max_cost_alert
- [ ] Fallback si Cost Explorer falla: status="unknown", warning al usuario
- [ ] Dry-run injection para servicios soportados (ec2, rds, s3api, iam, cloudformation, lambda)
- [ ] Confirmation flow: low→execute, medium→Y/N, high→typed, critical→dry-run+"yes-i-understand"
- [ ] Implementar AuditLogger en `src/cloudshellgpt/audit.py` (log ANTES de ejecutar)
- [ ] Tests unitarios para SafetyLayer (patterns, classification, upgrade logic)
- [ ] Tests unitarios para CostTracker (moto mock de Cost Explorer)
- [ ] **Checkpoint:** Comando destructivo requiere confirmación + muestra costo

---

### Sprint 3: Executor + Formatter (Hours 22-30)

**Goal:** Ejecución segura + output beautiful

#### Tareas
- [ ] Implementar `ExecutionResult` model en `src/cloudshellgpt/executor.py`
- [ ] AWSExecutor con validación estricta: solo `aws`, sin shell metacharacters
- [ ] Shell injection prevention completa (|, &&, ||, ;, backticks, $(), >, >>, <, &, \n, \0, <<, <(…), >(…), $VAR, ${VAR})
- [ ] Excepción: argumento literal `-` es válido
- [ ] Timeout configurable (30s default)
- [ ] Retry exponencial para throttling/timeouts
- [ ] Orden correcto: audit.log() → executor.run()
- [ ] Implementar Formatter en `src/cloudshellgpt/formatter.py`
- [ ] Rich integration: tablas, panels, colors, progress
- [ ] Multi-format output: table (default), json, yaml, csv
- [ ] Auto-detección TTY vs pipe (no-TTY → JSON sin colores)
- [ ] Error messages humanizados en español
- [ ] Tests unitarios para AWSExecutor (subprocess mocked)
- [ ] Tests unitarios para Formatter
- [ ] **Checkpoint:** `csgpt "lista buckets"` muestra tabla bonita + colores

---

### Sprint 4: MCP Server + Learning (Hours 30-38)

**Goal:** MCP server funcional + modo educativo

#### Tareas
- [ ] Implementar MCP server en `src/cloudshellgpt/mcp_server.py`
- [ ] Setup stdio transport
- [ ] Tool definitions con name, description, inputSchema
- [ ] Implementar handler `aws_translate`: input={intent, region?}, output={command, explanation, detailed_explanation, risk_level, estimated_cost, requires_dry_run, affected_resources, flags_used}
- [ ] Implementar handler `aws_execute`: input={command, dry_run?}, output={command, exit_code, stdout, stderr, duration_ms, dry_run}
- [ ] Implementar handler `aws_cost_preview`: input={command}, output={command, estimated_cost, risk_level, warnings}
- [ ] Implementar handler `aws_explain`: input={command}, output=markdown explanation
- [ ] Cada handler instancia propias dependencias (stateless)
- [ ] Catch ALL exceptions → retorna error como TextContent
- [ ] aws_execute description DEBE decir que confirme con usuario
- [ ] Implementar LearningMode en `src/cloudshellgpt/learning.py`
- [ ] Tips educativos post-ejecución
- [ ] Explicación de flags del comando traducido
- [ ] Sugerencias de comandos relacionados
- [ ] `csgpt explain <command>` (Bedrock temperature=0.3, max_tokens=1024)
- [ ] `csgpt learn <service>` — tutorial interactivo
- [ ] Tests del MCP server (protocol compliance)
- [ ] Tests de LearningMode
- [ ] **Checkpoint:** Kiro puede usar csgpt como MCP server

---

### Sprint 5: Polish + Docs + Demo (Hours 38-48)

**Goal:** Documentación profesional + video + entrega

#### Tareas
- [ ] Completar eval set a 100 casos (`tests/eval/translation_eval.jsonl`)
- [ ] Verificar > 90% precisión en eval set
- [ ] Coverage global > 80%, safety/executor > 90%
- [ ] README profesional con badges, quick start, examples
- [ ] Documentación de IAM permissions
- [ ] Contributing guide
- [ ] PII detection opt-in con Comprehend (si tiempo permite)
- [ ] Grabar video demo 5-7 minutos
- [ ] Demo script con casos impactantes (multi-idioma, safety prevention, cost alert)
- [ ] GitHub release v1.0.0
- [ ] Submit al hackathon
- [ ] **Final Checkpoint:** Todo entregado y funcional

---

## Estructura del Repositorio

```
cloudshellgpt/
├── .kiro/
│   ├── specs/
│   │   ├── 00-overview.md
│   │   ├── 01-architecture.md
│   │   ├── 02-acceptance-criteria.md
│   │   ├── 03-implementation-plan.md
│   │   ├── 04-safety-security.md
│   │   └── 05-mcp-server.md
│   ├── steering/
│   │   ├── aws-conventions.md
│   │   ├── code-style.md
│   │   ├── commit-conventions.md
│   │   ├── mcp-development.md
│   │   ├── project-context.md
│   │   ├── safety-patterns.md
│   │   └── testing-guide.md
│   └── hooks/
├── src/
│   └── cloudshellgpt/
│       ├── __init__.py
│       ├── cli.py                  # Entry point (Typer) → `csgpt`
│       ├── intent.py               # IntentParser + Intent model
│       ├── bedrock_translator.py   # BedrockTranslator + Translation model
│       ├── safety.py               # SafetyLayer + SafetyCheck model
│       ├── cost.py                 # CostTracker + CostEstimate model
│       ├── executor.py             # AWSExecutor + ExecutionResult model
│       ├── formatter.py            # Formatter (Rich, multi-format)
│       ├── audit.py                # AuditLogger (log before execute)
│       ├── learning.py             # LearningMode (tips, explain, tutorials)
│       ├── config.py               # ConfigManager (Pydantic Settings)
│       └── mcp_server.py           # MCP Server (stdio, stateless)
├── tests/
│   ├── conftest.py                 # Fixtures compartidas
│   ├── unit/
│   │   ├── test_intent.py
│   │   ├── test_bedrock.py
│   │   ├── test_safety.py
│   │   ├── test_cost.py
│   │   ├── test_executor.py
│   │   ├── test_formatter.py
│   │   ├── test_audit.py
│   │   ├── test_learning.py
│   │   └── test_config.py
│   ├── integration/
│   │   ├── test_bedrock.py
│   │   ├── test_mcp.py
│   │   └── test_e2e.py
│   └── eval/
│       └── translation_eval.jsonl  # 100 casos de prueba
├── infrastructure/
│   ├── app.py                      # CDK app
│   ├── cdk.json
│   └── lib/
│       └── cloudshellgpt_stack.py  # Stack: CloudShellGPT-{Environment}
├── .github/
│   └── workflows/
│       ├── ci.yml                  # ruff + mypy + pytest on PR to dev
│       └── release.yml             # Deploy on merge to main
├── pyproject.toml
├── README.md
├── LICENSE
├── CONTRIBUTING.md
└── CHANGELOG.md
```

---

## Git Workflow (commit-conventions steering)

### Branch Strategy
- `main` — protegida, siempre deployable (producción)
- `dev` — protegida, rama de integración (QA/staging)
- `feature/<short-description>` — features (desde `dev`)
- `fix/<short-description>` — bug fixes (desde `dev`)
- `infra/<short-description>` — infrastructure (desde `dev`)
- `docs/<short-description>` — documentation (desde `dev`)

### Merge Flow
1. Ramas de trabajo → merge a `dev` via PR (CI obligatorio: lint + tests)
2. `dev` estable → merge a `main` via PR (requiere aprobación del equipo)

### Commit Format
```
<type>(<scope>): <description>
```

Types: feat, fix, test, docs, refactor, ci, infra, chore, perf
Scopes: cli, intent, bedrock, safety, executor, formatter, audit, cost, learning, mcp, config, cdk

### PR Rules
- Never push directly to `main` or `dev`
- Minimum 1 review
- Squash merge preferred
- Delete branch after merge
- CI verde obligatorio

---

## File Ownership (para trabajo en paralelo)

| Persona | Archivos |
|---------|----------|
| Persona 1 (Core + Tests) | `tests/`, `intent.py`, `config.py` |
| Persona 2 (Infra + CI/CD) | `infrastructure/`, `.github/`, LICENSE, CONTRIBUTING |
| Persona 3 (UX + Safety) | `executor.py`, `safety.py`, `formatter.py`, `mcp_server.py` |
| Persona 4 (Docs + Demo) | `docs/`, `README.md`, eval set, video |

> Si necesitas tocar un archivo de otra persona, avisa en el canal del equipo antes de commitear.

---

## Development Commands

```bash
# Install all deps (including dev)
uv sync --all-extras

# Run CLI
csgpt --help
csgpt "lista los buckets de S3"

# Run tests
pytest
pytest tests/unit/ -v          # solo unit
pytest -m integration          # solo integración
pytest --cov=cloudshellgpt --cov-report=html

# Lint + format
ruff check . --fix
ruff format .

# Type check
mypy src/

# Pre-commit completo
ruff check . --fix && ruff format . && mypy src/

# CDK deploy (dev)
cd infrastructure && cdk deploy -c environment=dev
```

---

## Risk Mitigation

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| Bedrock latency > 5s | Media | Alto | Cache local futuro, timeout + mensaje claro |
| Cost Explorer no retorna datos | Baja | Medio | Fallback status="unknown" + warning |
| Shell injection attempt | Baja | Crítico | Validation estricta, reject all metacharacters |
| LLM genera comando destructivo con risk="low" | Media | Crítico | Safety verifica independientemente, nunca downgrda |
| Conflictos de merge en equipo | Media | Bajo | File ownership + comunicación en canal |
| Tests flaky con moto | Baja | Bajo | Fixtures limpias, no shared state |
