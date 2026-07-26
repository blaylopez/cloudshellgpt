# 🎬 Demo Script — CloudShellGPT

> **Duración objetivo:** 5–7 minutos
> **Formato:** Demo en vivo (terminal real) o video grabado
> **Audiencia:** Jueces de HACKATHONKIRO + developers

---

## 📋 Preparación

### Antes de grabar

```bash
# Verificar que csgpt está instalado
csgpt --version

# Verificar credenciales AWS
aws sts get-caller-identity

# Limpiar historial previo (para output limpio)
rm -f ~/.csgpt/audit.log
```

### Setup de terminal

- Terminal con fondo oscuro (tema recomendado: Dracula o Tokyo Night)
- Font size: 16–18pt para legibilidad en video
- Resolución: 1920×1080 mínimo
- Limpiar el prompt: `export PS1="$ "`

---

## 🎯 Escenario 1: Multi-idioma (90 segundos)

**Talking point:** *"CloudShellGPT entiende tu intención en cualquier idioma. No necesitas saber inglés para operar AWS."*

### 1.1 — Español 🇪🇸

```bash
$ csgpt ask "lista los buckets de S3 con su fecha de creación"
```

**Output esperado:**
```
⚡ CloudShellGPT v1.0.0 — AWS CLI that speaks your language

┌──────────────────────────┬─────────────────────┐
│ Name                     │ Created             │
├──────────────────────────┼─────────────────────┤
│ mi-bucket-produccion     │ 2024-03-15T10:23:01 │
│ backups-2023             │ 2023-11-08T08:45:12 │
└──────────────────────────┴─────────────────────┘
```

### 1.2 — Portugués 🇧🇷

```bash
$ csgpt ask "mostre as funções Lambda que falharam nas últimas 24 horas"
```

**Talking point:** *"Detecta portugués automáticamente y genera el comando correcto con filtros de CloudWatch."*

### 1.3 — Francés 🇫🇷

```bash
$ csgpt ask "combien d'instances EC2 sont en cours d'exécution?"
```

**Talking point:** *"Francés, alemán, chino… el mismo resultado preciso."*

### 1.4 — Alemán 🇩🇪

```bash
$ csgpt ask "zeige mir die IAM-Benutzer ohne MFA"
```

### 1.5 — Chino 🇨🇳

```bash
$ csgpt ask "列出所有没有标签的EC2实例"
```

**Talking point:** *"6 idiomas, mismo motor. Powered by Claude Sonnet 4.6 en Amazon Bedrock."*

### 1.6 — Inglés (comando complejo) 🇺🇸

```bash
$ csgpt ask "find all S3 buckets with public access enabled and show their policy"
```

**Talking point:** *"Incluso en inglés ahorra tiempo: una frase → un comando complejo de multi-step."*

---

## 🛡️ Escenario 2: Safety Prevention (120 segundos)

**Talking point:** *"AWS CLI es poderoso pero peligroso. CloudShellGPT agrega una capa de seguridad inteligente según el nivel de riesgo."*

### 2.1 — Riesgo BAJO (ejecución directa)

```bash
$ csgpt ask "describe the ec2 instance i-0abc123def"
```

**Output esperado:**
```
⚡ CloudShellGPT v1.0.0 — AWS CLI that speaks your language

┌─────────────────────────────────────────┐
│ Plan                                    │
├─────────────────────────────────────────┤
│ Command:                                │
│   aws ec2 describe-instances ...        │
│ Risk: low                               │
│ Cost: $0.00                             │
└─────────────────────────────────────────┘

(ejecuta directamente, sin confirmación)
```

**Talking point:** *"Comandos de lectura (list, describe, get) se ejecutan directo. Sin fricción."*

### 2.2 — Riesgo MEDIO (confirmación Y/N)

```bash
$ csgpt ask "create a new S3 bucket called hackathon-demo-2026"
```

**Output esperado:**
```
┌─────────────────────────────────────────┐
│ Plan                                    │
├─────────────────────────────────────────┤
│ Command:                                │
│   aws s3 mb s3://hackathon-demo-2026    │
│ Risk: medium                            │
│ Cost: ~$0.023/GB stored                 │
└─────────────────────────────────────────┘

Proceed? [y/N]: █
```

**Talking point:** *"Crear recursos requiere confirmación simple. Un typo no te cuesta dinero."*

### 2.3 — Riesgo ALTO (confirmación typed)

```bash
$ csgpt ask "delete the S3 bucket hackathon-demo-2026"
```

**Output esperado:**
```
┌─────────────────────────────────────────────────┐
│ ⚠️  HIGH RISK OPERATION                         │
├─────────────────────────────────────────────────┤
│ Command:                                        │
│   aws s3 rb s3://hackathon-demo-2026            │
│ Affected resources: hackathon-demo-2026        │
│ Estimated cost: $0.00 (deletion)                │
└─────────────────────────────────────────────────┘

Type the resource name ("hackathon-demo-2026") to confirm: █
```

**Talking point:** *"Para borrar, tienes que escribir el nombre del recurso. Imposible eliminar por accidente."*

### 2.4 — Riesgo CRÍTICO (dry-run + "yes-i-understand")

```bash
$ csgpt ask "elimina todos los objetos del bucket de producción recursivamente"
```

**Output esperado:**
```
┌──────────────────────────────────────────────────────────┐
│ 🚨 CRITICAL OPERATION — IRREVERSIBLE                     │
├──────────────────────────────────────────────────────────┤
│ Command:                                                 │
│   aws s3 rm s3://prod-bucket --recursive                 │
│ Affected resources:                                      │
│   • prod-bucket (all objects)                            │
│ Estimated cost: $0.00 (deletion)                         │
│                                                          │
│ A dry-run will be performed first to validate.           │
└──────────────────────────────────────────────────────────┘

Performing dry-run...

┌─────────────────────────────────────────┐
│ Dry-Run Result                          │
├─────────────────────────────────────────┤
│ ✓ Dry-run successful                    │
│ Would delete: 1,247 objects (3.2 GB)    │
└─────────────────────────────────────────┘

To proceed with this critical operation, type yes-i-understand:
Confirm: █
```

**Talking point:** *"Nivel crítico: primero se hace dry-run automático para que veas el impacto, y luego tienes que escribir 'yes-i-understand'. Triple protección."*

---

## 💰 Escenario 3: Cost Alert (60 segundos)

**Talking point:** *"Antes de gastar, sabes cuánto va a costar. Sin sorpresas en la factura."*

### 3.1 — Estimación con --cost-only

```bash
$ csgpt ask "create a RDS PostgreSQL db.r5.xlarge with multi-AZ" --cost-only
```

**Output esperado:**
```
⚡ CloudShellGPT v1.0.0 — AWS CLI that speaks your language

┌─────────────────────────────────────────────────┐
│ Cost Preview                                    │
├─────────────────────────────────────────────────┤
│ Estimated monthly cost: $487.20                 │
│                                                 │
│ Breakdown:                                      │
│   RDS db.r5.xlarge (Multi-AZ):    $365.00/mo   │
│   Storage (100GB gp3):            $23.00/mo     │
│   Multi-AZ standby:              $365.00/mo     │
│   Backup (7-day retention):        $11.50/mo    │
│                                                 │
│ ⚠️  ALERT: Exceeds $100/month threshold!        │
└─────────────────────────────────────────────────┘
```

**Talking point:** *"$487 al mes. Mejor saberlo ANTES de darle enter. El umbral de alerta es configurable."*

### 3.2 — Alerta integrada en el flujo normal

```bash
$ csgpt ask "launch 5 c5.2xlarge EC2 instances for load testing"
```

**Output esperado:**
```
┌─────────────────────────────────────────────────────┐
│ Plan                                                │
├─────────────────────────────────────────────────────┤
│ Command:                                            │
│   aws ec2 run-instances --instance-type c5.2xlarge  │
│       --count 5 ...                                 │
│ Risk: medium                                        │
│ Cost: ~$1.22/hr ($878/month if left running)        │
│                                                     │
│ ⚠️  COST ALERT: Estimated cost exceeds $100/month   │
└─────────────────────────────────────────────────────┘

Proceed? [y/N]: █
```

**Talking point:** *"La alerta de costo aparece integrada en el flujo, junto con el nivel de riesgo. Toda la info que necesitas para decidir."*

### 3.3 — Resumen de sesión

```bash
$ csgpt cost-summary
```

**Output esperado:**
```
┌─────────────────────────────────────────────────┐
│ Session Cost Summary                            │
├─────────────────────────────────────────────────┤
│ Commands executed: 8                            │
│ Resources created: 3                            │
│ Estimated monthly impact: $156.43               │
│                                                 │
│ Top costs:                                      │
│   1. RDS db.t3.medium:     $54.62/mo            │
│   2. EC2 t3.micro (×2):    $18.98/mo            │
│   3. S3 storage:           $2.30/mo             │
│                                                 │
│ Bedrock API usage: $0.18 (this session)         │
└─────────────────────────────────────────────────┘
```

**Talking point:** *"Al final de la sesión, un resumen de todo lo que gastaste. Transparencia total."*

---

## 📚 Escenario 4: Learning Mode (60 segundos)

**Talking point:** *"CloudShellGPT no solo ejecuta, enseña. Cada comando es una oportunidad de aprender."*

### 4.1 — Modo --explain

```bash
$ csgpt ask "create a lambda function that runs every hour" --explain
```

**Output esperado:**
```
(ejecuta el comando normalmente, luego muestra:)

┌─────────────────────────────────────────────────────────────┐
│ Learn: What just happened?                                  │
├─────────────────────────────────────────────────────────────┤
│ aws lambda create-function                                  │
│   --function-name: nombre único en tu cuenta/región         │
│   --runtime python3.12: última versión estable de Python    │
│   --role: IAM role con permisos de ejecución                │
│   --handler index.handler: archivo=index.py, función=handler│
│                                                             │
│ aws events put-rule                                         │
│   --schedule-expression "rate(1 hour)": cron simplificado   │
│   --name: nombre del trigger en EventBridge                 │
│                                                             │
│ 📚 Learn more:                                              │
│   https://docs.aws.amazon.com/lambda/latest/dg/             │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 — Explicar un comando existente

```bash
$ csgpt explain "aws iam list-users --query 'Users[?PasswordLastUsed<=`2024-01-01`]'"
```

**Output esperado:** Una explicación detallada de cada parte del comando, incluyendo la sintaxis JMESPath del `--query`.

### 4.3 — Comandos relacionados

```bash
$ csgpt ask "list all security groups"
```

**Output esperado (después de ejecutar):**
```
┌─────────────────────────────────────────────────────────┐
│ 🔗 Related commands                                     │
├─────────────────────────────────────────────────────────┤
│   aws ec2 describe-security-group-rules   Show rules    │
│   aws ec2 revoke-security-group-ingress   Remove rule   │
│   aws ec2 authorize-security-group-ingress  Add rule    │
└─────────────────────────────────────────────────────────┘
```

**Talking point:** *"Después de cada comando, sugiere los siguientes pasos lógicos. Como tener un mentor de AWS al lado."*

---

## 🔌 Escenario 5: MCP Integration con Kiro (60 segundos)

**Talking point:** *"CloudShellGPT también funciona como MCP server. Kiro puede usarlo directamente."*

### 5.1 — Mostrar configuración MCP

```json
// .kiro/settings/mcp.json
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

### 5.2 — Demo en Kiro (narrado)

**Talking point:** *"Desde Kiro puedo decir en lenguaje natural lo que quiero hacer en AWS, y CloudShellGPT lo ejecuta como herramienta MCP."*

**Flujo a mostrar en pantalla:**
1. Abrir Kiro con el proyecto configurado
2. Escribir: *"Ayúdame a encontrar las instancias EC2 que no tienen tags de equipo"*
3. Kiro invoca `aws_translate` → muestra el comando generado
4. Kiro invoca `aws_execute` → muestra resultados formateados
5. Kiro sugiere: *"¿Quieres que les agregue el tag 'team=hackathon'?"*

### 5.3 — Tools expuestos

```bash
$ csgpt mcp serve
# Starting MCP server on stdio...
# Tools: aws_translate, aws_execute, aws_cost_preview, aws_explain
```

**Talking point:** *"4 herramientas MCP: traducir, ejecutar, estimar costo, y explicar. Cualquier cliente MCP compatible puede usarlas."*

---

## ⏱️ Timing Sugerido

| Sección | Duración | Acumulado |
|---------|----------|-----------|
| Intro + Banner | 30s | 0:30 |
| Escenario 1: Multi-idioma | 90s | 2:00 |
| Escenario 2: Safety Prevention | 120s | 4:00 |
| Escenario 3: Cost Alert | 60s | 5:00 |
| Escenario 4: Learning Mode | 60s | 6:00 |
| Escenario 5: MCP Integration | 60s | 7:00 |
| Cierre + Resumen | 15s | 7:15 |

**Total: ~7 minutos** (recortar multi-idioma a 3 idiomas si necesitas llegar a 5 min)

---

## 🎤 Script de Apertura (Sugerido)

> "¿Cuántas veces has googleado un comando de AWS CLI? ¿Cuántas veces has borrado algo por accidente? ¿Cuántas veces te ha llegado una factura sorpresa?
>
> CloudShellGPT resuelve los tres problemas: habla tu idioma, protege contra errores destructivos, y te avisa antes de gastar.
>
> Les muestro cómo funciona."

---

## 🎤 Script de Cierre (Sugerido)

> "CloudShellGPT: 6 idiomas, 4 niveles de seguridad, predicción de costos, modo educativo, y compatible con Kiro como MCP server. Todo con Amazon Bedrock.
>
> AWS CLI que habla tu idioma. Gracias."

---

## 💡 Tips para la Grabación

1. **Velocidad de tipeo:** Usa un script con `sleep` entre comandos o tipea despacio para que se vea natural
2. **Terminal limpia:** Ejecuta `clear` entre escenarios
3. **Highlights:** Los paneles de Rich se ven espectaculares en video — asegúrate de que el tema del terminal tenga buen contraste
4. **Errores:** Si algo falla en vivo, es una oportunidad de mostrar el manejo de errores graceful
5. **Zoom:** Usa `Ctrl++` para ampliar el texto en secciones clave (cost alert, critical warning)

---

## 🔧 Script Automatizado (Opcional)

Para una demo grabada sin errores, puedes usar este script con delays:

```bash
#!/bin/bash
# demo-auto.sh — Script automatizado para grabación

DELAY=2

clear
echo "$ csgpt --version"
sleep $DELAY
csgpt --version
sleep $DELAY

clear
echo ""
echo "═══════════════════════════════════════════"
echo "  ESCENARIO 1: MULTI-IDIOMA"
echo "═══════════════════════════════════════════"
echo ""
sleep $DELAY

echo '$ csgpt ask "lista los buckets de S3 con su fecha de creación"'
sleep $DELAY
csgpt ask "lista los buckets de S3 con su fecha de creación"
sleep 3

echo ""
echo '$ csgpt ask "mostre as funções Lambda que falharam nas últimas 24 horas"'
sleep $DELAY
csgpt ask "mostre as funções Lambda que falharam nas últimas 24 horas"
sleep 3

echo ""
echo '$ csgpt ask "列出所有没有标签的EC2实例"'
sleep $DELAY
csgpt ask "列出所有没有标签的EC2实例"
sleep 3

clear
echo ""
echo "═══════════════════════════════════════════"
echo "  ESCENARIO 2: SAFETY PREVENTION"
echo "═══════════════════════════════════════════"
echo ""
sleep $DELAY

echo '$ csgpt ask "describe the ec2 instance i-0abc123def"'
sleep $DELAY
csgpt ask "describe the ec2 instance i-0abc123def"
sleep 3

echo ""
echo '$ csgpt ask "elimina todos los objetos del bucket de producción recursivamente"'
sleep $DELAY
csgpt ask "elimina todos los objetos del bucket de producción recursivamente"
# (aquí se detiene esperando input — demostrar el flujo manualmente)

clear
echo ""
echo "═══════════════════════════════════════════"
echo "  ESCENARIO 3: COST ALERT"
echo "═══════════════════════════════════════════"
echo ""
sleep $DELAY

echo '$ csgpt ask "create a RDS PostgreSQL db.r5.xlarge with multi-AZ" --cost-only'
sleep $DELAY
csgpt ask "create a RDS PostgreSQL db.r5.xlarge with multi-AZ" --cost-only
sleep 3

clear
echo ""
echo "═══════════════════════════════════════════"
echo "  ESCENARIO 4: LEARNING MODE"
echo "═══════════════════════════════════════════"
echo ""
sleep $DELAY

echo '$ csgpt explain "aws s3 ls --recursive s3://my-bucket"'
sleep $DELAY
csgpt explain "aws s3 ls --recursive s3://my-bucket"
sleep 3

echo ""
echo "═══════════════════════════════════════════"
echo "  FIN — CloudShellGPT ⚡"
echo "═══════════════════════════════════════════"
```

---

*Última actualización: Sprint 5 — Polish + Docs + Demo*
