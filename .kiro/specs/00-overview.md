# CloudShellGPT — Overview Specification

## Project Identity

- **Name:** CloudShellGPT
- **Tagline:** *AWS CLI que habla tu idioma.*
- **Category:** HACKATHONKIRO — Agentes especializados / Productividad para developers
- **Version:** 1.0.0
- **License:** Apache 2.0

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
- **Entiende** intención en lenguaje natural (ES, EN, PT, ZH, FR, DE)
- **Traduce** a AWS CLI / Boto3 con contexto del ambiente
- **Ejecuta** con sandboxing y confirmaciones inteligentes
- **Explica** qué hace cada comando en modo "learning"
- **Predice costos** antes de ejecutar
- **Previene** acciones destructivas con dry-run obligatorio

## Success Metrics

| Métrica | Target | Medición |
|---|---|---|
| Latencia promedio de traducción | < 2.5s | Bedrock latency metrics |
| Precisión de traducción (intent → CLI) | > 90% | Eval set con 100 casos |
| Comandos destructivos prevenidos | 100% de los críticos | Audit log en DynamoDB |
| Idiomas soportados con misma calidad | 6 (ES, EN, PT, ZH, FR, DE) | Eval set multi-idioma |
| Costo por request promedio | < $0.02 | Bedrock + API costs |
| Time to first useful command | < 30s desde install | Onboarding analytics |

## Stakeholders

- **Primary users:** Developers LATAM, juniors en AWS, equipos no-angloparlantes
- **Secondary:** AWS Solutions Architects que necesitan prototipar rápido
- **Tertiary:** Educadores y estudiantes de cloud computing

## Non-Goals (v1.0)

- ❌ No es un reemplazo de AWS Console (es complementario)
- ❌ No es un IDE completo (es un CLI)
- ❌ No ejecuta comandos multi-cuenta cross-region en v1
- ❌ No soporta IaC (Terraform/CDK) — son proyectos complementarios
