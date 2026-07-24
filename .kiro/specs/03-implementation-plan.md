# CloudShellGPT — Implementation Plan & Timeline

## Sprint Breakdown (70 horas, 4 integrantes)

### Sprint 0: Foundation (Hours 0-8)

**Goal:** Repositorio funcional + CI básico + skeleton CLI

#### Tareas
- [x] Configurar pyproject.toml con todas las deps (typer, rich, boto3, pydantic, mcp, langdetect, pyyaml, httpx)
- [x] Setup de `uv` como package manager
- [x] Crear estructura de módulos en `src/cloudshellgpt/`
- [x] Crear CLI skeleton con Typer (`cli.py` → entry point `csgpt`)
- [x] Configurar ruff (line-length=100, rules: E, F, I, N, W, UP, Y, B, A, C4, PT)
- [x] Configurar mypy strict mode
- [x] Setup de GitHub Actions workflow (ruff check + ruff format + mypy + pytest)
- [x] Configurar pre-commit hooks
- [x] Setup de pytest con moto + pytest-cov + pytest-asyncio
- [x] Crear `tests/conftest.py` con fixtures compartidas
- [x] **Checkpoint:** `csgpt --help` muestra comandos disponibles

---

### Sprint 1: Intent Parsing + Bedrock Integration (Hours 8-22)

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
- [ ] Tests parametrizados para IntentParser — detección de idioma (mínimo 5 inputs por cada uno de los 6 idiomas = 30 casos)
- [ ] Tests parametrizados para IntentParser — detección de servicio (mínimo 3 inputs por cada uno de los 10 servicios = 30 casos)
- [ ] Tests parametrizados para IntentParser — detección de acción (mínimo 3 inputs por cada una de las 6 acciones = 18 casos)
- [ ] Tests parametrizados para IntentParser — edge cases: input vacío, solo espacios, unicode raro, texto > 500 chars, idioma mixto (ES+EN), emojis
- [ ] Tests de confianza: verificar que confidence < 0.7 cuando input es ambiguo (mínimo 10 inputs ambiguos variados)
- [ ] Tests unitarios para BedrockTranslator (mocked boto3): response parsing, JSON extraction con/sin markdown fences, campos faltantes, response vacía
- [ ] Tests unitarios para BedrockTranslator — error handling: timeout, throttling, invalid JSON, response truncada
- [ ] Crear eval set inicial (`tests/eval/translation_eval.yaml`, 40 casos mínimo distribuidos: ≥ 5/idioma, ≥ 3/servicio, ≥ 5/riesgo)
- [ ] **Checkpoint:** `csgpt "lista los buckets de S3"` traduce correctamente + tests pasan con > 95% de los casos parametrizados

---

### Sprint 2: Safety Layer + Cost (Hours 22-38)

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
- [ ] Tests parametrizados para SafetyLayer — detección exhaustiva de TODOS los destructive patterns (parametrizar la lista completa: "delete", "terminate", "rm", "remove", "drop", "destroy", "force", "purge", "wipe", "nuke", "deregister", "revoke", "detach", "disable", "release", "empty", "--recursive", "--force", "-f", "--no-preserve", "--skip-final-snapshot", "--force-delete", "--permanently-delete", "--no-undo", "--force-destroy", "--delete-all-versions", "--bypass-governance-retention", "--no-preserve-root" = 28 casos mínimo)
- [ ] Tests de invariante: safety NUNCA downgrda — generar 50+ combinaciones de (LLM_risk_level, command) y verificar que `assess()` retorna risk ≥ LLM_risk_level en TODOS los casos
- [ ] Tests parametrizados para risk classification — mínimo 5 comandos por nivel (low: list/describe/get/head/wait, medium: create-bucket/tag-resource/put-metric-alarm/enable-*/create-snapshot, high: delete-bucket/terminate-instances/revoke-sg/detach-volume, critical: rm --recursive/--force-delete/--skip-final-snapshot)
- [ ] Tests para heurística medium vs high — mínimo 10 casos: 5 operaciones con inverso directo (→ medium) + 5 que destruyen datos (→ high)
- [ ] Tests para _upgrade_risk ladder — parametrizar todas las transiciones: low→high, medium→high, high→critical, critical→critical
- [ ] Tests para combinaciones peligrosas en contexto (ej: `update-stack` sin changeset, `put-bucket-policy` con "*")
- [ ] Tests unitarios para CostTracker — happy path: track + session_summary, fallback: Cost Explorer error retorna status="unknown", budget alert: costo > max_cost_alert trigger warning
- [ ] Tests para CostTracker — session tracking acumulativo: múltiples track() y verificar que session_summary refleja todos
- [ ] Tests para integración safety ↔ cost: safety consume CostEstimate y alerta según umbral configurado
- [ ] **Checkpoint:** Comando destructivo requiere confirmación + muestra costo + 100% de destructive patterns detectados

---

### Sprint 3: Executor + Formatter (Hours 38-52)

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
- [ ] Tests parametrizados para AWSExecutor — rechazo exhaustivo de TODOS los shell metacharacters (parametrizar cada uno individualmente: `|`, `&&`, `||`, `;`, `` ` ` ``, `$(...)`, `>`, `>>`, `<`, `2>`, `&` al final, `\n`, `\0`, `<<`, `<<<`, `<(...)`, `>(...)`, `$VAR`, `${VAR}` = 19 casos mínimo, cada uno en un comando que se vea legítimo ej: `aws s3 ls | grep prod`)
- [ ] Tests de invariante: executor SOLO ejecuta comandos que empiezan con `aws` — parametrizar mínimo 10 comandos no-aws: `curl`, `rm -rf /`, `ls`, `python`, `bash`, `sh -c`, `echo`, `cat`, comando vacío `""`, solo espacios `"   "`, `aws` como substring (`notaws s3 ls`)
- [ ] Tests para excepción del argumento `-` (AC-2.2) — verificar que `aws s3 cp - s3://bucket/file` es aceptado, pero `aws s3 ls > output.txt` es rechazado
- [ ] Tests parametrizados para metacharacters en posiciones variadas: al inicio (`| aws s3 ls`), al medio (`aws s3 ls | grep`), al final (`aws s3 ls &`), dentro de argumentos (`aws s3 cp s3://$(whoami)/file .`), entre comillas simples vs dobles
- [ ] Tests para timeout — subprocess que excede 30s retorna exit_code=124 con error claro
- [ ] Tests para dry-run injection — parametrizar todos los servicios soportados (ec2 run-instances, ec2 terminate-instances, ec2 delete-volume, rds delete-db-instance, s3api delete-bucket, iam delete-user) y verificar que se agrega `--dry-run`. Verificar que servicios NO soportados NO reciben `--dry-run`
- [ ] Tests para retry exponencial — simular 3 errores transitorios seguidos y verificar que reintenta con backoff
- [ ] Tests para AWS CLI not found (FileNotFoundError) — retorna exit_code=127 con mensaje claro
- [ ] Tests unitarios para Formatter — parametrizar los 5 formatos (table, json, yaml, csv, raw) con mismo input y verificar output válido en cada formato
- [ ] Tests para Formatter — auto-detección TTY vs pipe: mockear `sys.stdout.isatty()` como True/False y verificar cambio de comportamiento
- [ ] Tests para Formatter — edge cases: output vacío, JSON inválido como stdout, lista vacía, lista con > 50 items (verifica truncamiento), caracteres unicode en datos
- [ ] Tests para Formatter — error rendering: exit_code != 0 muestra mensaje humanizado con stderr
- [ ] **Checkpoint:** `csgpt "lista buckets"` muestra tabla bonita + 100% metacharacters rechazados + tests pasan

---

### Sprint 4: MCP Server + Learning (Hours 52-62)

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
- [ ] Tests de invariante: MCP server NUNCA crashea — parametrizar mínimo 10 tipos de excepciones inyectadas en handlers (ValueError, TypeError, KeyError, AttributeError, BedrockError, TimeoutError, ConnectionError, json.JSONDecodeError, boto3 ClientError, RuntimeError) y verificar que SIEMPRE retorna list[TextContent] con mensaje de error, nunca propaga exception
- [ ] Tests de invariante: MCP es stateless — hacer 5 calls secuenciales a `aws_translate` con inputs diferentes y verificar que cada call instancia nuevas dependencias (mock IntentParser/BedrockTranslator con side_effect que detecte reutilización)
- [ ] Tests parametrizados para los 4 tools — verificar input/output contract de cada uno: aws_translate (input válido → JSON con 8 campos), aws_execute (input válido → JSON con 6 campos), aws_cost_preview (input → JSON con 4 campos), aws_explain (input → string markdown)
- [ ] Tests para aws_translate — campos faltantes en input (sin intent, sin region), input vacío, input extremadamente largo (> 1000 chars)
- [ ] Tests para aws_execute — verificar que description del tool contiene texto de confirmación con usuario (AC-6.3 requisito)
- [ ] Tests para `list_tools()` — verificar que retorna exactamente 4 tools con names correctos, schemas JSON válidos, y descriptions no vacías
- [ ] Tests para routing en `call_tool` — tool name desconocido retorna "Unknown tool", tool name vacío, tool name con caracteres especiales
- [ ] Tests async para `serve_mcp()` — verificar que levanta sin error y responde a initialize (protocol compliance básico)
- [ ] Tests unitarios para LearningMode — TutorialRunner con topic válido muestra steps, topic inválido muestra error con available topics
- [ ] Tests para Explainer — mocked Bedrock: explain_sync retorna markdown, Bedrock error retorna mensaje de error sin crashear
- [ ] Tests para Explainer.explain_last — audit log vacío muestra warning, audit con entries explica el último
- [ ] **Checkpoint:** Kiro puede usar csgpt como MCP server + 100% de exceptions manejadas sin crash

---

### Sprint 5: Polish + Docs + Demo (Hours 62-70)

**Goal:** Documentación profesional + video + entrega

#### Tareas
- [ ] Completar eval set a 100+ casos (`tests/eval/translation_eval.yaml`) con distribución verificada:
  - ≥ 15 casos por idioma (ES, EN, PT, FR, DE, ZH) — total ≥ 90
  - ≥ 8 casos por servicio top (S3, EC2, Lambda, IAM, RDS, DynamoDB, VPC, SQS, SNS, CloudFront)
  - ≥ 25 low, ≥ 25 medium, ≥ 25 high, ≥ 15 critical
  - ≥ 10 edge cases (ambiguos, idioma mixto, vacíos, unicode, muy largos)
- [ ] Crear script `tests/eval/validate_distribution.py` que verifica que el eval set cumple los mínimos de distribución antes de correr el eval
- [ ] Implementar `tests/eval/test_eval.py` — runner que carga el YAML, ejecuta IntentParser sobre cada caso, y reporta precisión por dimensión (idioma, servicio, acción, riesgo)
- [ ] Verificar > 90% precisión global en eval set Y > 85% por cada idioma individual (no solo el promedio)
- [ ] Coverage global > 80%, safety > 90%, executor > 90% — generar reporte HTML con `pytest --cov-report=html`
- [ ] Correr `ruff check . && mypy src/` sin errores — zero warnings policy
- [ ] Tests de integración E2E (sandbox AWS): mínimo 3 flujos completos (list → show table, create → confirm → execute, delete → safety blocks)
- [ ] README profesional con badges, quick start, examples
- [ ] Documentación de IAM permissions
- [ ] Grabar video demo 5-7 minutos
- [ ] Demo script con casos impactantes (multi-idioma, safety prevention, cost alert)
- [ ] GitHub release v1.0.0
- [ ] Submit al hackathon
- [ ] **Final Checkpoint:** Eval set pasa con > 90% global + > 85%/idioma + coverage cumplido + CI verde

---

---

## Estrategia de Testing

### Principios

1. **Tests parametrizados** — todo lo que tiene una lista finita de casos (metacharacters, destructive patterns, idiomas, servicios) usa `@pytest.mark.parametrize`. Un solo test cubre N variaciones.
2. **Tests de invariantes** — propiedades que deben cumplirse SIEMPRE se validan con múltiples inputs diseñados para romper la regla (ej: "safety NUNCA downgrda").
3. **Eval set distribuido** — no solo "100 casos", sino con distribución mínima garantizada por idioma, servicio y riesgo.
4. **Cobertura por hipótesis** — cada sub-hipótesis del proyecto tiene tests específicos que la validan bajo variación, no con un solo ejemplo.

### Tipos de Tests

| Tipo | Ubicación | Propósito | AWS real |
|------|-----------|-----------|----------|
| Unit | `tests/unit/` | Validar lógica aislada de cada módulo | No (moto/mocks) |
| Integration | `tests/integration/` | Validar flujo completo entre módulos | Sandbox only |
| Eval | `tests/eval/` | Validar precisión de traducción a escala | No (mocked Bedrock) |
| Invariant | Dentro de unit | Validar propiedades que NUNCA deben violarse | No |

### Pytest Markers

```python
# tests/conftest.py
import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "unit: unit tests (fast, no AWS)")
    config.addinivalue_line("markers", "integration: integration tests (sandbox AWS)")
    config.addinivalue_line("markers", "eval: eval set precision tests")
    config.addinivalue_line("markers", "invariant: property-based invariant tests")
    config.addinivalue_line("markers", "slow: tests that take > 5s")
    config.addinivalue_line("markers", "persona1: owned by Persona 1 (Core + Tests)")
    config.addinivalue_line("markers", "persona2: owned by Persona 2 (Infra + CI)")
    config.addinivalue_line("markers", "persona3: owned by Persona 3 (UX + Safety)")
    config.addinivalue_line("markers", "persona4: owned by Persona 4 (Docs + Eval)")
```

### Eval Set — Distribución Requerida (mínimo 100 casos)

| Dimensión | Distribución mínima |
|-----------|---------------------|
| **Idiomas** | ≥ 15 casos por idioma (ES, EN, PT, FR, DE, ZH) = 90 mínimo |
| **Servicios** | ≥ 8 casos por servicio top (S3, EC2, Lambda, IAM, RDS, DynamoDB, VPC, SQS, SNS, CloudFront) |
| **Acciones** | ≥ 12 list, ≥ 12 create, ≥ 12 delete, ≥ 8 update, ≥ 8 describe, ≥ 5 invoke |
| **Riesgo** | ≥ 25 low, ≥ 25 medium, ≥ 25 high, ≥ 15 critical |
| **Edge cases** | ≥ 10 (ambiguos, mixtos idioma, vacíos, unicode raro, muy largos) |

Cada caso del eval set incluye:
```yaml
- id: "ES-S3-LIST-001"
  input: "lista los buckets de S3"
  language: "es"
  expected_service: "s3"
  expected_action: "list"
  expected_risk: "low"
  expected_command_contains: ["s3", "list"]
  expected_command_not_contains: ["delete", "rm"]
```

### Invariantes a Validar (tests que prueban que algo NUNCA pasa)

| Invariante | Módulo | Qué testear |
|------------|--------|-------------|
| Safety NUNCA downgrda | safety.py | Generar 50+ combinaciones (LLM risk + command) y verificar que output_risk ≥ input_risk siempre |
| Executor NUNCA ejecuta metacharacters | executor.py | Parametrizar los 18+ metacharacters de AC-2.1 y verificar rechazo en cada uno |
| Executor SOLO ejecuta comandos `aws` | executor.py | Probar con `curl`, `rm`, `ls`, `python`, comandos vacíos, solo espacios |
| MCP NUNCA crashea por exception | mcp_server.py | Inyectar 10+ tipos de excepciones y verificar que siempre retorna TextContent |
| MCP es stateless | mcp_server.py | Hacer N calls secuenciales y verificar que no hay side effects entre ellas |
| Audit NUNCA crashea el flujo | audit.py | Simular disco lleno, permisos denegados, path inválido — nunca debe propagar exception |

### Esfuerzo Estimado por Persona (70 horas totales)

| Persona | Tests a cargo | Horas estimadas en tests | Horas en implementación |
|---------|---------------|--------------------------|-------------------------|
| Persona 1 (Core + Tests) | test_intent, test_config, conftest, eval runner | ~20h tests, ~15h impl | 35h total |
| Persona 2 (Infra + CI) | CI pipeline, test infra (moto setup), test_audit | ~10h tests, ~25h impl | 35h total |
| Persona 3 (UX + Safety) | test_safety, test_executor, test_formatter, test_mcp | ~25h tests, ~20h impl | 45h total* |
| Persona 4 (Docs + Eval) | eval dataset (100 casos), test_eval runner, test_cost, test_learning | ~20h tests, ~15h impl | 35h total |

> *Persona 3 tiene más carga de tests porque safety + executor son los módulos más críticos. Se recomienda que Persona 1 apoye con test_executor si hay bottleneck.

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

| Persona | Archivos de implementación | Tests a cargo | Sprints principales |
|---------|---------------------------|---------------|---------------------|
| Persona 1 (Core + Tests) | `intent.py`, `config.py`, `tests/conftest.py` | `test_intent.py` (78+ casos parametrizados), `test_config.py`, eval runner (`test_eval.py`), `validate_distribution.py` | Sprint 0, 1, 5 |
| Persona 2 (Infra + CI) | `infrastructure/`, `.github/`, `audit.py` | `test_audit.py` (invariante never-crash), CI pipeline (pytest en PR), coverage report setup | Sprint 0, 2, 5 |
| Persona 3 (UX + Safety) | `executor.py`, `safety.py`, `formatter.py`, `mcp_server.py` | `test_safety.py` (28 patterns + 50 invariant), `test_executor.py` (19 metacharacters + invariants), `test_formatter.py` (5 formatos + edge cases), `test_mcp.py` (invariants + 4 tools) | Sprint 2, 3, 4 |
| Persona 4 (Docs + Eval) | `docs/`, `README.md`, `learning.py`, `cost.py` | `test_learning.py`, `test_cost.py`, eval dataset YAML (100+ casos con distribución), `test_bedrock.py` (mocked) | Sprint 1, 4, 5 |

### Detalle de carga de tests por persona

| Persona | # Tests estimados | Módulos críticos (>90% cov) | Prioridad |
|---------|-------------------|------------------------------|-----------|
| Persona 1 | ~90 (intent: 78 parametrizados + config: ~12) | No | Alta — es la base para eval |
| Persona 2 | ~15 (audit: invariantes + happy path) | No | Media — apoyo con CI |
| Persona 3 | ~130 (safety: 50+, executor: 40+, formatter: 20+, mcp: 20+) | Sí — safety + executor | Crítica — más carga, pedir apoyo si bottleneck |
| Persona 4 | ~40 (eval dataset: 100 casos, cost: 10, learning: 10, bedrock: 20) | No | Alta — eval set es entregable final |

### Reglas de coordinación

- Persona 3 tiene la mayor carga de tests. Si se atrasa, Persona 1 toma `test_executor.py`
- El eval dataset (Persona 4) depende de que IntentParser (Persona 1) esté estable → coordinar en Sprint 1
- `tests/conftest.py` (Persona 1) debe estar listo en Sprint 0 para que todos puedan escribir tests
- Si necesitas tocar un archivo de otra persona, avisa en el canal del equipo antes de commitear

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
