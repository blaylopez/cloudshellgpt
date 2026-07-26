# 🔐 Permisos IAM — CloudShellGPT

## Tabla de Contenidos

- [Visión General](#visión-general)
- [Modelo Dual de Permisos](#modelo-dual-de-permisos)
- [Política Mínima Requerida](#política-mínima-requerida)
- [Política Recomendada](#política-recomendada)
- [Política Opcional (PII Detection)](#política-opcional-pii-detection)
- [Política Completa Combinada](#política-completa-combinada)
- [Restricción de Recursos](#restricción-de-recursos)
- [Instrucciones de Configuración](#instrucciones-de-configuración)
- [Resolución de Problemas](#resolución-de-problemas)
- [Mejores Prácticas de Seguridad](#mejores-prácticas-de-seguridad)

---

## Visión General

CloudShellGPT requiere permisos IAM específicos para funcionar. Estos permisos son **exclusivamente** para las llamadas API que realiza la herramienta internamente (traducción con Bedrock, estimación de costos). Son **independientes** de los permisos que el usuario necesita para ejecutar comandos AWS CLI.

### Principios clave

1. **CloudShellGPT NUNCA gestiona sus propias credenciales** — utiliza las credenciales AWS del entorno (variables de entorno, perfil configurado, rol de instancia, etc.)
2. **Los permisos de la herramienta son SEPARADOS** de los permisos del usuario para operar AWS
3. **Principio de mínimo privilegio** — solo se solicitan los permisos estrictamente necesarios

---

## Modelo Dual de Permisos

CloudShellGPT opera con un modelo de permisos dual:

```
┌─────────────────────────────────────────────────────────────┐
│                    CREDENCIALES AWS DEL USUARIO              │
├─────────────────────────┬───────────────────────────────────┤
│  Permisos CloudShellGPT │     Permisos del Usuario          │
│  (la herramienta)       │     (operaciones AWS)             │
├─────────────────────────┼───────────────────────────────────┤
│  • bedrock:InvokeModel  │  • s3:ListBuckets                 │
│  • ce:GetCostAndUsage   │  • ec2:DescribeInstances          │
│  • comprehend:Detect*   │  • lambda:CreateFunction          │
│  (solo lo de la tool)   │  • (lo que el usuario ya tenga)   │
└─────────────────────────┴───────────────────────────────────┘
```

| Capa | Propósito | Quién lo define |
|------|-----------|-----------------|
| **Permisos CloudShellGPT** | Traducción (Bedrock), estimación de costos (Cost Explorer), detección de PII (Comprehend) | Este documento |
| **Permisos del usuario** | Ejecutar comandos AWS CLI (S3, EC2, Lambda, etc.) | La organización/admin del usuario |

> **Importante:** Si el usuario ya tiene permisos para operar AWS CLI, solo necesita **agregar** los permisos de CloudShellGPT. No necesita reconfigurar nada de lo que ya tiene.

---

## Política Mínima Requerida

Esta política es el **mínimo absoluto** para que CloudShellGPT funcione. Permite la traducción de lenguaje natural a comandos AWS CLI mediante Amazon Bedrock.

**Sin estos permisos, CloudShellGPT no puede funcionar.**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CloudShellGPTBedrockMinimum",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0"
    }
  ]
}
```

### ¿Qué permite?

| Acción | Propósito |
|--------|-----------|
| `bedrock:InvokeModel` | Enviar prompts a Claude 3.5 Sonnet para traducir intenciones |
| `bedrock:InvokeModelWithResponseStream` | Respuestas en streaming (mejor UX con respuestas progresivas) |

### Limitaciones con solo esta política

- ❌ No hay estimación de costos antes de ejecutar comandos
- ❌ No hay detección de PII en outputs
- ✅ Traducción funciona completamente
- ✅ Safety layer funciona (usa pattern matching local, no requiere permisos extra)
- ✅ Ejecución de comandos funciona (usa los permisos propios del usuario)

---

## Política Recomendada

Esta política habilita **todas las funcionalidades principales** de CloudShellGPT: traducción + estimación de costos.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CloudShellGPTBedrock",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0"
    },
    {
      "Sid": "CloudShellGPTCostExplorer",
      "Effect": "Allow",
      "Action": [
        "ce:GetCostAndUsage",
        "ce:GetCostForecast"
      ],
      "Resource": "*"
    }
  ]
}
```

### ¿Qué agrega sobre la mínima?

| Acción | Propósito |
|--------|-----------|
| `ce:GetCostAndUsage` | Consultar costos históricos para estimar impacto de nuevos recursos |
| `ce:GetCostForecast` | Proyectar costos futuros basados en patrones actuales |

> **Nota:** Cost Explorer (`ce:*`) no soporta restricción por recurso ARN — el `Resource` debe ser `"*"`. Esto es una limitación de AWS, no un problema de seguridad: estas acciones son solo de lectura.

---

## Política Opcional (PII Detection)

Si se habilita la detección de PII (`enable_pii_detection: true` en `~/.csgpt/config.yaml`), se necesita acceso a Amazon Comprehend.

**Esta funcionalidad es opt-in y NO se requiere para el funcionamiento normal.**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CloudShellGPTComprehendPII",
      "Effect": "Allow",
      "Action": [
        "comprehend:DetectPiiEntities"
      ],
      "Resource": "*"
    }
  ]
}
```

### ¿Qué permite?

| Acción | Propósito |
|--------|-----------|
| `comprehend:DetectPiiEntities` | Escanear outputs de comandos para detectar y redactar PII (emails, SSN, tarjetas de crédito) |

---

## Política Completa Combinada

Esta política incluye **todos los permisos** que CloudShellGPT puede necesitar:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CloudShellGPTBedrock",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0"
    },
    {
      "Sid": "CloudShellGPTCostExplorer",
      "Effect": "Allow",
      "Action": [
        "ce:GetCostAndUsage",
        "ce:GetCostForecast"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudShellGPTComprehendPII",
      "Effect": "Allow",
      "Action": [
        "comprehend:DetectPiiEntities"
      ],
      "Resource": "*"
    }
  ]
}
```

---

## Restricción de Recursos

### Restringir por región

Si CloudShellGPT solo se usará en una región específica, se puede restringir el ARN de Bedrock:

```json
{
  "Sid": "CloudShellGPTBedrockRegionRestricted",
  "Effect": "Allow",
  "Action": [
    "bedrock:InvokeModel",
    "bedrock:InvokeModelWithResponseStream"
  ],
  "Resource": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0"
}
```

Para otra región (ej. `eu-west-1`):

```json
"Resource": "arn:aws:bedrock:eu-west-1::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0"
```

Para múltiples regiones:

```json
"Resource": [
  "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0",
  "arn:aws:bedrock:eu-west-1::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0"
]
```

### Restringir por modelo específico

El ARN ya está restringido al modelo `anthropic.claude-3-5-sonnet-20241022-v2:0`. Si en el futuro se quiere permitir otros modelos de Bedrock:

```json
"Resource": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.*"
```

> **No recomendado** para producción — es preferible ser explícito con el modelo.

### Condiciones adicionales

Se puede añadir una condición para restringir por IP de origen o por hora:

```json
{
  "Sid": "CloudShellGPTBedrockWithConditions",
  "Effect": "Allow",
  "Action": [
    "bedrock:InvokeModel",
    "bedrock:InvokeModelWithResponseStream"
  ],
  "Resource": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0",
  "Condition": {
    "IpAddress": {
      "aws:SourceIp": "203.0.113.0/24"
    }
  }
}
```

---

## Instrucciones de Configuración

### Opción 1: Adjuntar política a un usuario IAM

#### Vía AWS Console

1. Abre la [consola de IAM](https://console.aws.amazon.com/iam/)
2. Navega a **Users** → selecciona tu usuario
3. Pestaña **Permissions** → **Add permissions** → **Create inline policy**
4. Selecciona la pestaña **JSON**
5. Pega la [política recomendada](#política-recomendada)
6. Click **Review policy** → nombre: `CloudShellGPTAccess` → **Create policy**

#### Vía AWS CLI

```bash
# Crear el archivo de política
cat > /tmp/cloudshellgpt-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CloudShellGPTBedrock",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0"
    },
    {
      "Sid": "CloudShellGPTCostExplorer",
      "Effect": "Allow",
      "Action": [
        "ce:GetCostAndUsage",
        "ce:GetCostForecast"
      ],
      "Resource": "*"
    }
  ]
}
EOF

# Adjuntar como inline policy
aws iam put-user-policy \
  --user-name TU_USUARIO \
  --policy-name CloudShellGPTAccess \
  --policy-document file:///tmp/cloudshellgpt-policy.json
```

### Opción 2: Adjuntar política a un rol IAM

Útil si usas roles (EC2 instance profile, ECS task role, Lambda execution role).

#### Vía AWS CLI

```bash
# Crear política gestionada
aws iam create-policy \
  --policy-name CloudShellGPTAccess \
  --policy-document file:///tmp/cloudshellgpt-policy.json

# Adjuntar al rol
aws iam attach-role-policy \
  --role-name TU_ROL \
  --policy-arn arn:aws:iam::123456789012:policy/CloudShellGPTAccess
```

### Opción 3: Uso en AWS CloudShell

Si usas CloudShellGPT directamente desde AWS CloudShell:

1. El rol de CloudShell ya incluye los permisos del usuario
2. Solo necesitas agregar los permisos de Bedrock y Cost Explorer al usuario/rol que inicia la sesión de CloudShell
3. Sigue la [Opción 1](#opción-1-adjuntar-política-a-un-usuario-iam) para agregar los permisos a tu usuario

### Opción 4: Uso con AWS SSO / Identity Center

```bash
# Crea un permission set con la política
aws sso-admin create-permission-set \
  --instance-arn arn:aws:sso:::instance/ssoins-XXXXXXXX \
  --name "CloudShellGPTAccess" \
  --description "Permisos para CloudShellGPT"

# Adjunta la política inline al permission set
aws sso-admin put-inline-policy-to-permission-set \
  --instance-arn arn:aws:sso:::instance/ssoins-XXXXXXXX \
  --permission-set-arn arn:aws:sso:::permissionSet/ssoins-XXXXXXXX/ps-XXXXXXXX \
  --inline-policy file:///tmp/cloudshellgpt-policy.json
```

### Habilitar el modelo en Bedrock

Antes de usar CloudShellGPT, debes habilitar el acceso al modelo Claude 3.5 Sonnet en tu cuenta:

1. Abre la [consola de Bedrock](https://console.aws.amazon.com/bedrock/home?region=us-east-1#/modelaccess)
2. Click en **Manage model access**
3. Selecciona **Anthropic** → **Claude 3.5 Sonnet v2**
4. Click **Save changes**

> **Nota:** La habilitación del modelo es un paso único por cuenta/región. No tiene costo — solo pagas por las invocaciones.

---

## Resolución de Problemas

### Error: `AccessDeniedException` en Bedrock

```
botocore.exceptions.ClientError: An error occurred (AccessDeniedException)
when calling the InvokeModel operation: You don't have access to the model
```

**Causa:** El usuario/rol no tiene permisos `bedrock:InvokeModel`.

**Solución:**
1. Verifica que la [política mínima](#política-mínima-requerida) esté adjunta
2. Verifica que el modelo esté habilitado en la consola de Bedrock
3. Verifica que la región sea correcta (el modelo debe estar habilitado en la misma región que usas)

```bash
# Verificar permisos actuales
aws sts get-caller-identity
aws iam list-attached-user-policies --user-name TU_USUARIO
aws iam list-user-policies --user-name TU_USUARIO
```

### Error: `AccessDeniedException` en Cost Explorer

```
botocore.exceptions.ClientError: An error occurred (AccessDeniedException)
when calling the GetCostAndUsage operation
```

**Causa:** Faltan permisos de `ce:GetCostAndUsage`.

**Solución:**
1. Agrega la [política recomendada](#política-recomendada)
2. **Nota:** Cost Explorer debe estar activado en la cuenta. Si es una cuenta nueva, actívalo en **Billing** → **Cost Explorer** → **Enable**

> Si no puedes obtener permisos de Cost Explorer, CloudShellGPT seguirá funcionando pero mostrará "costo desconocido" en lugar de estimaciones.

### Error: `ModelNotReadyException`

```
botocore.exceptions.ClientError: An error occurred (ModelNotReadyException)
```

**Causa:** El modelo Claude 3.5 Sonnet no está habilitado en tu cuenta/región.

**Solución:**
1. Ve a la [consola de Bedrock Model Access](https://console.aws.amazon.com/bedrock/home?region=us-east-1#/modelaccess)
2. Habilita Claude 3.5 Sonnet v2 de Anthropic
3. Espera unos minutos a que se active

### Error: `ExpiredTokenException`

```
botocore.exceptions.ClientError: An error occurred (ExpiredTokenException)
```

**Causa:** Las credenciales AWS han expirado.

**Solución:**
```bash
# Si usas credenciales temporales (SSO, assume-role)
aws sso login --profile tu-perfil

# Si usas MFA
aws sts get-session-token --serial-number arn:aws:iam::123456789012:mfa/user --token-code 123456
```

### Error: `RegionDisabledException`

**Causa:** Estás intentando usar Bedrock en una región donde no está disponible o no está habilitado.

**Solución:**
1. Usa `us-east-1` (siempre disponible para Bedrock)
2. O habilita la región en tu cuenta: **Account** → **AWS Regions** → Enable

### Verificar que todo funciona

```bash
# Test rápido de permisos
aws bedrock-runtime invoke-model \
  --model-id anthropic.claude-3-5-sonnet-20241022-v2:0 \
  --region us-east-1 \
  --content-type application/json \
  --body '{"anthropic_version":"bedrock-2023-05-31","max_tokens":10,"messages":[{"role":"user","content":"hi"}]}' \
  /tmp/test-output.json

# Si retorna sin error, los permisos de Bedrock están correctos
cat /tmp/test-output.json

# Test de Cost Explorer
aws ce get-cost-and-usage \
  --time-period Start=2024-01-01,End=2024-01-02 \
  --granularity DAILY \
  --metrics BlendedCost

# Si retorna datos (o error de fechas), los permisos de CE están correctos
```

---

## Mejores Prácticas de Seguridad

### 1. Principio de mínimo privilegio

- Usa la [política mínima](#política-mínima-requerida) si no necesitas estimación de costos
- Solo agrega Comprehend si realmente usas detección de PII
- Restringe el ARN de Bedrock a la región que uses

### 2. Usa condiciones IAM

Agrega condiciones para limitar desde dónde se puede invocar:

```json
{
  "Condition": {
    "StringEquals": {
      "aws:RequestedRegion": "us-east-1"
    }
  }
}
```

### 3. Rotación y temporalidad

- Prefiere roles IAM sobre access keys estáticas
- Si usas access keys, configura rotación cada 90 días
- Usa AWS SSO/Identity Center para credenciales temporales automáticas

### 4. Monitoreo

- Habilita CloudTrail para auditar las llamadas a Bedrock
- Configura alertas en CloudWatch si el uso de Bedrock excede un umbral
- Revisa los logs de auditoría de CloudShellGPT en `~/.csgpt/audit.log`

### 5. Separación de permisos

- **No combines** los permisos de CloudShellGPT con permisos administrativos
- Crea una política separada llamada `CloudShellGPTAccess` para facilitar auditoría
- Si trabajas en equipo, usa políticas gestionadas (no inline) para reutilizar

### 6. Evita wildcards innecesarios

```json
// ❌ Mal — demasiado permisivo
"Resource": "*"

// ✅ Bien — específico al modelo
"Resource": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0"
```

> **Nota:** `ce:*` y `comprehend:DetectPiiEntities` requieren `Resource: "*"` por diseño de AWS — no es posible restringirlos a un ARN específico.

### 7. No expongas credenciales

CloudShellGPT usa las credenciales del entorno. Asegúrate de:

- **Nunca** hardcodear access keys en código o configuración
- **Nunca** compartir archivos `~/.aws/credentials` sin redactar
- Usar variables de entorno o perfiles nombrados
- El archivo `~/.csgpt/audit.log` **nunca** registra credenciales

---

## Resumen Rápido

| Funcionalidad | Permisos necesarios | ¿Obligatorio? |
|---|---|---|
| Traducción (lenguaje natural → AWS CLI) | `bedrock:InvokeModel`, `bedrock:InvokeModelWithResponseStream` | ✅ Sí |
| Estimación de costos | `ce:GetCostAndUsage`, `ce:GetCostForecast` | ⚡ Recomendado |
| Detección de PII | `comprehend:DetectPiiEntities` | ⚪ Opcional (opt-in) |
| Ejecución de comandos AWS | *Los permisos propios del usuario* | — (ya los tiene) |
| Safety layer / Risk classification | *Ninguno adicional* (lógica local) | — |
| Audit logging | *Ninguno* (escritura local a disco) | — |
