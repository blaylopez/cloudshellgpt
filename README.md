# ⚡ CloudShellGPT

> **AWS CLI que habla tu idioma.**
> Natural language → AWS operations · powered by Amazon Bedrock

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Powered by Bedrock](https://img.shields.io/badge/Powered_by-Amazon_Bedrock-orange.svg)](https://aws.amazon.com/bedrock/)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://modelcontextprotocol.io)
[![Kiro Compatible](https://img.shields.io/badge/Kiro-Ready-purple.svg)](https://kiro.dev)

CloudShellGPT convierte tus intenciones en lenguaje natural (en **cualquier idioma**) en comandos AWS CLI correctos, seguros y con predicción de costos. Construido con [Amazon Bedrock](https://aws.amazon.com/bedrock/) (Claude 3.5 Sonnet) y compatible con [Kiro](https://kiro.dev) como MCP server.

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
# Con pip
pip install cloudshellgpt

# O con uv (más rápido)
uv tool install cloudshellgpt

# O con pipx (aislado)
pipx install cloudshellgpt
```

### Configuración inicial (1 minuto)

```bash
# 1. Asegúrate de tener credenciales AWS
aws configure

# 2. Habilita el modelo Claude 3.5 en Bedrock (one-click)
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

## 🎬 Demo — 5 ejemplos que impresionan

### 1. En español, sin saber AWS CLI
```bash
$ csgpt ask "muéstrame las lambdas que fallaron ayer"
```

### 2. En portugués, con filtro de costo
```bash
$ csgpt ask "liste os buckets do S3 que ninguém usa há mais de 90 dias"
```

### 3. En inglés, comando complejo generado
```bash
$ csgpt ask "create a t3.micro ec2 with a security group allowing SSH from my IP, and tag it as 'hackathon-demo'"
```

### 4. Con predicción de costo
```bash
$ csgpt ask "spin up a rds postgres db.t3.medium for 30 days" --cost-only
# Output:
# Estimated monthly cost: $58.32
# Breakdown:
#   - RDS db.t3.medium (Single-AZ): $54.62/month
#   - Storage (100GB gp2):       $11.50/month
#   - Backup retention:          $2.00/month
# Total:                          $68.12/month
```

### 5. Modo aprendizaje
```bash
$ csgpt ask "create a lambda that responds with current time" --explain
# Output:
# ✓ Lambda created
#
# What just happened? (educational mode)
# - aws lambda create-function: Creates a new Lambda
# - --function-name: must be unique within your account/region
# - --runtime python3.12: latest stable Python runtime
# - --role: IAM role with lambda:InvokeFunction permission
# - --handler index.handler: file is index.py, function is handler()
# - --zip-file fileb://: reads code from a ZIP file
#
# 📚 Learn more: https://docs.aws.amazon.com/lambda/latest/dg/getting-started.html
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
                Claude 3.5      Cost Explorer
                Sonnet
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
| Bedrock Translator | Traduce Intent → AWS CLI command | Amazon Bedrock + Claude 3.5 Sonnet |
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
      "Resource": "arn:aws:bedrock:*::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0"
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
- ✅ **Timeout enforcement**: comandos colgados se matan a los 30s

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

¡Contribuciones bienvenidas! Ver [CONTRIBUTING.md](CONTRIBUTING.md).

### Setup de desarrollo

```bash
git clone https://github.com/cloudshellgpt/cloudshellgpt
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
- Anthropic por [Claude 3.5 Sonnet](https://www.anthropic.com)
- Los organizadores de **HACKATHONKIRO**
- La comunidad open source

---

<p align="center">
  <strong>Hecho con ⚡ para HACKATHONKIRO</strong>
  <br>
  <em>Demo en vivo: <a href="https://cloudshellgpt.dev/demo">cloudshellgpt.dev/demo</a></em>
</p>
