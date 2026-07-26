# CloudShellGPT — Overview Specification

## Project Identity

- **Name:** CloudShellGPT
- **CLI command:** `csgpt`
- **Tagline:** *AWS CLI que habla tu idioma.*
- **Category:** HACKATHONKIRO — Agentes especializados / Productividad para developers
- **Version:** 1.0.0
- **License:** Apache 2.0
- **Python:** 3.12+
- **Build system:** hatchling
- **Package manager:** uv

## Mission Statement

Convertir lenguaje natural (en cualquier idioma) en operaciones de AWS correctas, seguras y económicas, democratizando el acceso a la nube para developers de habla no inglesa y reduciendo drásticamente la curva de aprendizaje de la AWS CLI.

## The Problem We Solve

1. **Cognitive overload:** AWS CLI tiene +2,500 subcomandos. Ningún developer los memoriza.
2. **Documentation friction:** AWS Docs son exhaustivas pero requieren buscar, leer, adaptar. Toma 5-15 min por tarea.
3. **Language barrier:** El 80% del material está en inglés. Developers en LATAM, España, Asia tienen fricción adicional.
4. **Risk of destructive commands:** `aws s3 rm` mal escrito puede borrar producción. No hay guardrails nativos.
5. **Cost blindness:** Developers ejecutan comandos sin saber cuánto cuestan hasta que llega la factura.

## The Solution

Un agente CLI (compatible con bash/zsh/fish) que:

- **Entiende** intención en lenguaje natural (ES, EN, PT, ZH, FR, DE) usando `langdetect`
- **Traduce** a AWS CLI via Amazon Bedrock (`us.anthropic.claude-sonnet-4-6`, Converse API)
- **Ejecuta** con sandboxing estricto: solo comandos `aws`, sin shell metacharacters, con timeout configurable
- **Clasifica riesgo** en 4 niveles (low/medium/high/critical) con confirmaciones inteligentes
- **Predice costos** antes de ejecutar via AWS Cost Explorer
- **Previene** acciones destructivas con detección de patrones + dry-run obligatorio para critical
- **Explica** qué hace cada comando en modo "learning" post-ejecución
- **Se integra** como MCP server (stdio transport) con Kiro, Claude Desktop y Cursor

## Dual Interface

CloudShellGPT opera en dos modos:

1. **CLI directo:** `csgpt "lista los buckets de S3"` en terminal
2. **MCP Server:** `csgpt mcp serve` — expone tools via stdio:
   - `aws_translate` — natural language → AWS CLI
   - `aws_execute` — ejecutar con optional dry-run
   - `aws_cost_preview` — estimar costo
   - `aws_explain` — explicación detallada de comando

## Success Metrics

| Métrica | Target | Medición |
|---|---|---|
| Latencia promedio de traducción | < 2.5s | Bedrock latency metrics |
| Precisión de traducción (intent → CLI) | > 90% | Eval set con 100 casos |
| Comandos destructivos prevenidos | 100% de high/critical | Audit log local |
| Idiomas soportados con misma calidad | 6 (ES, EN, PT, ZH, FR, DE) | Eval set multi-idioma |
| Costo por request promedio | < $0.02 | ~$0.003/1K input, ~$0.015/1K output |
| Time to first useful command | < 30s desde install | Onboarding flow |
| Coverage tests unitarios | > 80% global, > 90% safety/executor | pytest --cov |
| Startup time | < 500ms | CLI cold start |
| Memory footprint | < 150MB | Runtime profiling |

## Stakeholders

- **Primary users:** Developers LATAM, juniors en AWS, equipos no-angloparlantes
- **Secondary:** AWS Solutions Architects que necesitan prototipar rápido
- **Tertiary:** Educadores y estudiantes de cloud computing

## Git & Collaboration Model

- **Branches:** `main` (producción) ← `dev` (integración/QA) ← `feature/*`, `fix/*`, `infra/*`, `docs/*`
- **Commits:** Conventional Commits con scopes por módulo (`feat(intent):`, `fix(executor):`, etc.)
- **CI/CD:** GitHub Actions — lint + test obligatorio antes de merge a `dev`, aprobación de equipo para merge a `main`
- **PRs:** Squash merge preferred, template con checklist, mínimo 1 review
- **Ownership por módulo:** Cada persona del equipo tiene ownership de archivos específicos para evitar conflictos

## Configuration

User config en `~/.csgpt/config.yaml`:

```yaml
region: us-east-1
language: auto
default_output: table
bedrock_model: us.anthropic.claude-sonnet-4-6
require_confirmation_for: [high, critical]
enable_cost_preview: true
enable_learning_mode: true
max_cost_alert: 100  # USD
```

## Non-Goals (v1.0)

- No es un reemplazo de AWS Console (es complementario)
- No es un IDE completo (es un CLI)
- No ejecuta comandos multi-cuenta cross-region
- No soporta IaC generation (Terraform/CDK)
- No gestiona sus propias credenciales — usa las del environment
- No ejecuta comandos con shell metacharacters (pipe, &&, ;, backticks, $())
- No GUI/TUI interactivo
- No deploy automation
- No custom LLM fine-tuning
