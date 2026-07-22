# CloudShellGPT — Implementation Plan & Timeline

## Sprint Breakdown (48 horas)

### 🚀 Sprint 0: Foundation (Hours 0-6)
**Goal:** Repositorio funcional + CI básico + skeleton CLI

#### Tareas
- [ ] Setup monorepo con `uv` workspace
- [ ] Configurar pyproject.toml con todas las deps
- [ ] Crear CLI skeleton con Typer
- [ ] Setup de GitHub Actions (lint + test)
- [ ] Configurar pre-commit hooks
- [ ] Setup de testing con pytest + moto (mock AWS)
- [ ] Crear estructura de módulos
- [ ] **Checkpoint 0.1:** `csgpt --help` muestra comandos

**Kiro assistance:** Generar pyproject.toml, estructura de carpetas, GitHub Actions workflow.

---

### 🧠 Sprint 1: Intent Parsing + Bedrock Integration (Hours 6-14)
**Goal:** Traducción natural language → AWS CLI funcionando

#### Tareas
- [ ] Implementar Intent model con Pydantic
- [ ] Cliente de Bedrock (Claude 3.5 Sonnet)
- [ ] System prompt engineering (few-shot examples)
- [ ] Multi-language detection
- [ ] Basic command executor (subprocess)
- [ ] Tests unitarios para intent parser
- [ ] Tests de integración con Bedrock (usar eval set)
- [ ] **Checkpoint 1.1:** `csgpt "lista los buckets de S3"` ejecuta correctamente

**Kiro assistance:** Generar el bedrock client, system prompts, eval set.

**Créditos Kiro estimados:** 400-500 por persona

---

### 🛡️ Sprint 2: Safety Layer (Hours 14-22)
**Goal:** Sistema de seguridad robusto con cost preview

#### Tareas
- [ ] Risk classifier (rule-based + LLM)
- [ ] Cost estimator con AWS Cost Explorer
- [ ] Dry-run mode con validación
- [ ] Confirmation prompts typed
- [ ] PII detection con Comprehend (opt-in)
- [ ] Audit logger (local + opcional CloudWatch)
- [ ] Tests de seguridad
- [ ] **Checkpoint 2.1:** Comando destructivo requiere confirmación + muestra costo

**Kiro assistance:** Generar risk classifier, prompts de safety, tests.

**Créditos Kiro estimados:** 300-400

---

### 🎨 Sprint 3: Formatter + UX Polish (Hours 22-30)
**Goal:** Output beautiful + interactive

#### Tareas
- [ ] Rich integration (tablas, progress, colors)
- [ ] Multi-format output (json, yaml, csv, table)
- [ ] Streaming de output
- [ ] Search/filter interactivo
- [ ] Error messages humanizados
- [ ] Loading spinners con contexto
- [ ] **Checkpoint 3.1:** `csgpt ls s3` muestra tabla bonita + colores

**Kiro assistance:** Generar componentes de formatter, temas de colores.

**Créditos Kiro estimados:** 200-300

---

### 🔌 Sprint 4: MCP Server (Hours 30-36)
**Goal:** Servidor MCP funcional para integración con Kiro/Claude

#### Tareas
- [ ] Setup MCP server con stdio transport
- [ ] Implementar 4 tools: translate, execute, cost_preview, explain
- [ ] Documentar schema de cada tool
- [ ] Tests del MCP server
- [ ] Integración de prueba con Kiro IDE
- [ ] **Checkpoint 4.1:** Kiro puede usar csgpt como MCP server

**Kiro assistance:** Generar MCP server boilerplate, schemas.

**Créditos Kiro estimados:** 200-300

---

### 📚 Sprint 5: Learning Mode + Docs (Hours 36-42)
**Goal:** Material educativo + docs profesionales

#### Tareas
- [ ] `csgpt learn` con tutoriales interactivos
- [ ] `csgpt explain` con detalles de flags
- [ ] README profesional con badges
- [ ] Tutorial en YouTube (short, 2 min)
- [ ] IAM permissions docs
- [ ] Contributing guide
- [ ] **Checkpoint 5.1:** Un nuevo usuario puede empezar en < 5 min

**Kiro assistance:** Generar tutoriales interactivos, docs detalladas.

**Créditos Kiro estimados:** 150-200

---

### 🎬 Sprint 6: Demo + Polish (Hours 42-48)
**Goal:** Video pitch + últimos detalles

#### Tareas
- [ ] Grabar video de 5-7 minutos
- [ ] Demo script con casos impactantes
- [ ] Landing page (opcional, Next.js)
- [ ] Publicar en PyPI
- [ ] GitHub release v1.0.0
- [ ] Submit al hackathon
- [ ] **Final Checkpoint:** Todo entregado

**Kiro assistance:** Generar script de video, landing page.

**Créditos Kiro estimados:** 100-150

---

## Estructura del Repositorio

```
cloudshellgpt/
├── .kiro/
│   ├── specs/                  # Este directorio
│   ├── steering/
│   │   ├── code-style.md
│   │   ├── commit-conventions.md
│   │   └── aws-conventions.md
│   └── hooks/
│       └── pre-commit.md
├── src/
│   └── cloudshellgpt/
│       ├── __init__.py
│       ├── cli.py              # Entry point (Typer)
│       ├── intent.py           # Intent parser
│       ├── bedrock_translator.py
│       ├── safety.py
│       ├── executor.py
│       ├── formatter.py
│       ├── cost.py
│       ├── audit.py
│       ├── learning.py
│       └── mcp_server.py
├── tests/
│   ├── unit/
│   │   ├── test_intent.py
│   │   ├── test_safety.py
│   │   ├── test_formatter.py
│   │   └── test_executor.py
│   ├── integration/
│   │   ├── test_bedrock.py
│   │   ├── test_aws.py
│   │   └── test_mcp.py
│   └── eval/
│       └── translation_eval.jsonl   # 100 casos de prueba
├── infrastructure/
│   ├── app.py                  # CDK app
│   ├── stacks/
│   │   ├── observability_stack.py
│   │   └── docs_stack.py
│   └── cdk.json
├── docs/
│   ├── architecture.md
│   ├── iam-permissions.md
│   ├── tutorials/
│   │   ├── 01-quickstart.md
│   │   ├── 02-s3-workflows.md
│   │   └── 03-cost-optimization.md
│   └── images/
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── release.yml
├── pyproject.toml
├── README.md
├── LICENSE
├── CONTRIBUTING.md
└── CHANGELOG.md
```

---

## IAM Permissions Required (Documentar para usuarios)

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

> **Note:** Los permisos de los servicios AWS que el usuario quiera operar (S3, EC2, etc.) NO se incluyen aquí — son los que ya tiene en su environment.
