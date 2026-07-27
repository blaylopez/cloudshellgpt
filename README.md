# ⚡ CloudShellGPT

> **AWS CLI que habla tu idioma.**
> Natural language → AWS operations · powered by Amazon Bedrock

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Powered by Bedrock](https://img.shields.io/badge/Powered_by-Amazon_Bedrock-orange.svg)](https://aws.amazon.com/bedrock/)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://modelcontextprotocol.io)
[![Kiro Compatible](https://img.shields.io/badge/Kiro-Ready-purple.svg)](https://kiro.dev)

CloudShellGPT convierte tus intenciones en lenguaje natural (en **cualquier idioma**) en comandos AWS CLI correctos, seguros y con predicción de costos. Construido con [Amazon Bedrock](https://aws.amazon.com/bedrock/) (Claude Sonnet 4.6) y compatible con [Kiro](https://kiro.dev) como MCP server.

> 🏆 Built for **HACKATHONKIRO** — Category: *Agentes especializados & Productividad para developers*

---

## 🎯 ¿Qué problema resuelve?

| Problema | Cómo CloudShellGPT lo resuelve |
|---|---|
| AWS CLI tiene 2,500+ comandos imposibles de memorizar | Describe lo que quieres en tu idioma, nosotros lo traducimos |
| La documentación de AWS está en inglés y es densa | Soporte nativo para ES, EN, PT, FR, DE, ZH |
| Los comandos destructivos son peligrosos | Confirmación typed + dry-run automático + cost preview |
| Los developers junior no saben qué comando usar | Modo `--explain` te enseña qué hace cada flag |
| Las facturas de AWS sorprenden al final del mes | Predicción de costo antes de ejecutar |

---

## ⚡ Quick Start

### Instalación (30 segundos)

```bash
# Desde GitHub (recomendado)
pip install git+https://github.com/blaylopez/cloudshellgpt.git

# O con uv (más rápido)
uv pip install git+https://github.com/blaylopez/cloudshellgpt.git

# Desde PyPI (próximamente)
# pip install cloudshellgpt
```

### Configuración inicial (1 minuto)

```bash
# 1. Asegúrate de tener credenciales AWS
aws configure

# 2. Habilita el modelo Claude Sonnet 4.6 en Bedrock (one-click)
# https://console.aws.amazon.com/bedrock/home?region=us-east-1#/modelaccess

# 3. (Opcional) Configura defaults
csgpt config --set-region us-west-2
csgpt config --set-language es
```

### Primer uso (10 segundos)

```bash
# Antes: tenías que saber el comando exacto
$ aws s3api list-buckets --query 'Buckets[].{Name:Name,Created:CreationDate}' --output table

# Ahora: solo describe lo que quieres
$ csgpt ask "lista los buckets de S3 con su fecha de creación"

# Output:
# ⚡ CloudShellGPT v1.0.0 — AWS CLI that speaks your language
#
# ┌──────────────────────────┬─────────────────────┐
# │ Name                     │ Created             │
# ├──────────────────────────┼─────────────────────┤
# │ mi-bucket-produccion     │ 2024-03-15T10:23:01 │
# │ mi-bucket-staging        │ 2024-09-22T14:18:33 │
# │ backups-2023             │ 2023-11-08T08:45:12 │
# └──────────────────────────┴─────────────────────┘
```

---

## 🎬 Demo — 7 ejemplos que impresionan

### 1. En español, sin saber AWS CLI
```bash
$ csgpt ask "muéstrame las funciones lambda de mi cuenta"
```

### 2. En portugués, detección automática de idioma
```bash
$ csgpt ask "liste os buckets do S3 com data de criação"
```

### 3. Crear un recurso (DynamoDB)
```bash
$ csgpt ask "crea una tabla en DynamoDB llamada hackathon-users con partition key user_id"
# Output:
# ╭──────────── Plan ─────────────╮
# │ Comando: aws dynamodb create-table --table-name hackathon-users
# │   --attribute-definitions AttributeName=user_id,AttributeType=S
# │   --key-schema AttributeName=user_id,KeyType=HASH
# │   --billing-mode PAY_PER_REQUEST
# │
# │ Riesgo: medium
# │ Costo: $1.25 por millón de escrituras / $0.25 por millón de lecturas
# ╰──────────────────────────────╯
# Proceed? [Y/n]: y
# ✓ Tabla creada: arn:aws:dynamodb:us-east-1:***:table/hackathon-users
```

### 4. Eliminar un recurso (con confirmación de seguridad)
```bash
$ csgpt ask "elimina la tabla DynamoDB hackathon-users"
# Output:
# ╭──────────── Plan ─────────────╮
# │ Comando: aws dynamodb delete-table --table-name hackathon-users
# │ Riesgo: high
# │ Recursos afectados: dynamodb:table/hackathon-users, todos los ítems, índices GSI/LSI
# ╰──────────────────────────────╯
# ⚠️  OPERACIÓN DE ALTO RIESGO
# Escribe el nombre del recurso ("dynamodb:table/hackathon-users") para confirmar: _
#
# 💡 Consejo: Antes de eliminar, considera hacer un backup con
#    'aws dynamodb create-backup' o exportar a S3.
```

### 5. Con predicción de costo
```bash
$ csgpt ask "spin up a rds postgres db.t3.medium for 30 days" --cost-only
# Output:
# ╭──────────────── Cost Preview ────────────────╮
# │ Estimated cost: ~$60–$75 per month           │
# │ (db.t3.medium On-Demand ~$0.082/hr           │
# │  + gp3 storage ~$0.115/GB-month)             │
# ╰──────────────────────────────────────────────╯
```

### 6. Modo aprendizaje
```bash
$ csgpt ask "lista las funciones lambda con su runtime" --explain
# Output:
# ✓ Ejecutado
#
# What just happened? (educational mode)
# - aws lambda list-functions: Obtiene todas las funciones Lambda de la cuenta
# - --query: Filtra y selecciona campos relevantes (nombre, runtime, memoria, timeout)
# - --output table: Presenta la información en formato tabular legible
# - --no-paginate: Devuelve todos los resultados en una sola llamada
#
# 💡 Consejo: Los runtimes deprecated dejan de recibir actualizaciones de seguridad.
#    Filtra por runtime específico añadiendo '?Runtime==`python3.8`' al query.
#
# 🔗 Relacionados:
#   aws lambda get-function --function-name NOMBRE
#   aws lambda list-functions --query 'Functions[?Runtime==`nodejs18.x`]...'
```

### 7. Explicar un comando existente (sin ejecutar)
```bash
$ csgpt explain "aws s3 rm s3://my-bucket --recursive"
# Output:
# ╭─────────────── Explanation ───────────────╮
# │ Service: Amazon S3 (high-level commands)
# │ Operation: rm — permanently deletes objects
# │
# │ Flags:
# │   s3://my-bucket     → Targets the entire bucket root
# │   --recursive        → Traverse all keys under the prefix
# │
# │ ⚠️  Common Pitfalls:
# │   - Does NOT delete the bucket itself
# │   - Versioned buckets: only adds Delete Markers
# │   - No confirmation prompt — executes immediately
# │   - Use --dryrun first to preview deletions
# │
# │ 💡 Dry-run:
# │   aws s3 rm s3://my-bucket --recursive --dryrun
# ╰──────────────────────────────────────────╯
```

---

## 🏗️ Arquitectura

```
┌──────────────────────────────────────────────────────────────┐
│                      USER TERMINAL                            │
│         $ csgpt ask "lista los buckets de S3"                 │
└────────────────────┬─────────────────────────────────────────┘
                     │
                     ▼
            ┌────────────────┐
            │   csgpt CLI    │
            │   (Python 3.12)│
            └────────┬───────┘
                     │
       ┌─────────────┼─────────────┐
       │             │             │
       ▼             ▼             ▼
┌──────────┐  ┌──────────┐  ┌──────────┐
│  Intent  │  │ Bedrock  │  │  Safety  │
│  Parser  │→ │Translator│→ │  Layer   │
└──────────┘  └──────────┘  └──────────┘
                Claude Sonnet   Cost Explorer
                4.6
                     │
                     ▼
            ┌────────────────┐
            │ AWS Executor   │
            │ (subprocess +  │
            │  boto3)        │
            └────────┬───────┘
                     │
                     ▼
            ┌────────────────┐
            │  Formatter     │
            │  (Rich TUI)    │
            └────────────────┘
```

### Componentes principales

| Componente | Responsabilidad | Tecnología |
|---|---|---|
| Intent Parser | Convierte lenguaje natural en Intent estructurado | Python + Pydantic + langdetect |
| Bedrock Translator | Traduce Intent → AWS CLI command | Amazon Bedrock + Claude Sonnet 4.6 |
| Safety Layer | Evalúa riesgo + predice costo | AWS Cost Explorer + reglas |
| Executor | Ejecuta comandos con sandboxing | subprocess + boto3 |
| Formatter | Renderiza output (table, json, yaml, csv) | Rich |
| Audit Logger | Registra todo para compliance | JSON Lines en disco |
| MCP Server | Expone como herramientas MCP | mcp library |

---

## 🌐 Integración con Kiro como MCP Server

CloudShellGPT se puede usar desde Kiro, Claude Desktop, Cursor, o cualquier cliente MCP.

### Configuración en Kiro

Agrega esto a `.kiro/settings/mcp.json`:

```json
{
  "mcpServers": {
    "cloudshellgpt": {
      "command": "csgpt",
      "args": ["mcp", "serve"],
      "env": {
        "AWS_REGION": "us-east-1"
      }
    }
  }
}
```

### Tools MCP expuestos

| Tool | Descripción |
|---|---|
| `aws_translate` | Traduce intención en lenguaje natural a comando AWS CLI |
| `aws_execute` | Ejecuta un comando AWS (con dry-run opcional) |
| `aws_cost_preview` | Predice el costo de un comando |
| `aws_explain` | Explica en detalle qué hace un comando |

### Ejemplo de uso desde Kiro

```
> Kiro, ayúdame a encontrar recursos sin tags en mi cuenta AWS

[Kiro invoca aws_translate con la intención]
[Kiro muestra el comando generado al usuario]
[Usuario confirma]
[Kiro invoca aws_execute]
[Kiro formatea el output]
```

---

## 🛡️ Seguridad

### IAM Permissions mínimas recomendadas

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
      "Resource": "arn:aws:bedrock:*::foundation-model/us.anthropic.claude-sonnet-4-6"
    },
    {
      "Sid": "CostExplorer",
      "Effect": "Allow",
      "Action": ["ce:GetCostAndUsage", "ce:GetCostForecast"],
      "Resource": "*"
    }
  ]
}
```

> **Importante:** CloudShellGPT NO necesita permisos adicionales sobre los servicios AWS que operas. Usa los que ya tienes en tu environment.

Para documentación completa de permisos IAM, ver [docs/IAM_PERMISSIONS.md](docs/IAM_PERMISSIONS.md).

### Características de seguridad

- ✅ **No exfiltra datos**: las llamadas a Bedrock usan solo el intent en lenguaje natural
- ✅ **Audit log local**: todos los comandos ejecutados quedan registrados
- ✅ **Risk classification**: cada comando es evaluado antes de ejecutar
- ✅ **Confirmation typed**: comandos críticos requieren escribir "yes-i-understand"
- ✅ **Dry-run obligatorio**: para comandos `critical` se fuerza `--dry-run`
- ✅ **Timeout enforcement**: comandos colgados se matan según configuración (default 60s)

---

## 🌍 Idiomas soportados

| Idioma | Calidad | Ejemplo |
|---|---|---|
| 🇪🇸 Español | ⭐⭐⭐⭐⭐ Nativo | `csgpt ask "lista los buckets de S3"` |
| 🇺🇸 English | ⭐⭐⭐⭐⭐ Nativo | `csgpt ask "list the S3 buckets"` |
| 🇧🇷 Português | ⭐⭐⭐⭐⭐ Nativo | `csgpt ask "liste os buckets do S3"` |
| 🇫🇷 Français | ⭐⭐⭐⭐ Excelente | `csgpt ask "liste les buckets S3"` |
| 🇩🇪 Deutsch | ⭐⭐⭐⭐ Excelente | `csgpt ask "liste die S3-Buckets"` |
| 🇨🇳 中文 | ⭐⭐⭐⭐ Excelente | `csgpt ask "列出S3存储桶"` |

---

## 🤝 Contribución

¡Contribuciones bienvenidas!

### Setup de desarrollo

```bash
git clone https://github.com/blaylopez/cloudshellgpt
cd cloudshellgpt
uv sync --all-extras
pre-commit install
pytest
```

### Roadmap

- [ ] Soporte para más modelos Bedrock (Llama 3, Mistral)
- [ ] TUI interactivo con Textual
- [ ] Plugin system para commands custom
- [ ] Integración con CloudWatch Logs Insights
- [ ] Modo "infrastructure as code" (genera Terraform)
- [ ] Multi-account con AWS SSO

---

## 📄 Licencia

Apache 2.0 — ver [LICENSE](LICENSE).

---

## 🙏 Agradecimientos

- Amazon Web Services por [Bedrock](https://aws.amazon.com/bedrock/)
- Anthropic por [Claude Sonnet 4.6](https://www.anthropic.com)
- Los organizadores de **HACKATHONKIRO**
- La comunidad open source

---

<p align="center">
  <strong>Hecho con ⚡ para HACKATHONKIRO</strong>
  <br>
  <em>Repositorio: <a href="https://github.com/blaylopez/cloudshellgpt">github.com/blaylopez/cloudshellgpt</a></em>
</p>
