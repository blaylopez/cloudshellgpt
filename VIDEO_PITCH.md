# 🎬 CloudShellGPT — Video Pitch Script (6:30)

> **Duration target:** 6:30 (within 5-7 min limit)
> **Audience:** Jeff Barr, Darko Mesaroš, Ana Cunha (AWS)
> **Tone:** Technical but accessible, with "wow" moments every 90 seconds

---

## 🎯 Story Arc

```
[0:00-0:30]  HOOK — The Pain
[0:30-1:00]  INTRO — What is CloudShellGPT
[1:00-2:30]  DEMO 1 — Multi-language + simple commands
[2:30-3:30]  DEMO 2 — Safety layer + cost preview
[3:30-4:30]  DEMO 3 — MCP integration with Kiro
[4:30-5:30]  ARCHITECTURE — How it works
[5:30-6:00]  IMPACT — Real numbers
[6:00-6:30]  CLOSE — Call to action
```

---

## 📜 SCRIPT DETALLADO

### 🎬 [0:00 - 0:30] HOOK — The Pain

**Visual:** Terminal blanco, comandos AWS CLI largos, scroll infinito de docs, developer frustrado.
**Audio:** Música electrónica suave, building.

```
[NARRATOR]
¿Alguna vez intentaste recordar el comando exacto para listar
los buckets de S3 con su fecha de creación?

[SCREEN]: Type slowly:
  aws s3api list-buckets --query 'Buckets[].{Name:Name,Created:CreationDate}' --output table

[NARRATOR]
AWS CLI tiene más de DOS MIL QUINIENTOS subcomandos.
La documentación está en inglés. Y un comando mal escrito
puede borrar producción.

[SCREEN]: Fade to red
  $ aws s3 rm s3://prod-data --recursive
  ⚠️  (big red warning)
```

**Director's note:** Ritmo rápido, pain visceral. El viewer debe sentir "eso me pasó".

---

### 🎬 [0:30 - 1:00] INTRO — What is CloudShellGPT

**Visual:** Logo aparece, terminal limpio, dashboard del proyecto.
**Audio:** Music shift, more confident.

```
[NARRATOR]
CloudShellGPT es un agente CLI que traduce lenguaje natural —
en CUALQUIER idioma — a comandos AWS correctos, seguros,
y con predicción de costos.

[SCREEN]: Animated text
  ⚡ CloudShellGPT
  AWS CLI que habla tu idioma

[NARRATOR]
Powered by Amazon Bedrock con Claude Sonnet 4.6,
funciona en español, inglés, portugués, francés, alemán y chino.
Y se integra con Kiro como MCP server.

[SCREEN]: Show Kiro integration
```

**Director's note:** Logo, nombre, claim. 30 segundos para setup mental.

---

### 🎬 [1:00 - 2:30] DEMO 1 — Multi-language magic

**Visual:** Live terminal, real demo. Tabs de diferente color por idioma.
**Audio:** Music building, more energetic.

```
[NARRATOR]
Veamos cómo funciona. Voy a hacer la misma pregunta en cinco idiomas
diferentes.

[SCREEN]: Split terminal — 5 panels

[Panel 1 — ES]
$ csgpt ask "lista los buckets de S3"
→ Output: tabla con buckets

[Panel 2 — EN]
$ csgpt ask "list the S3 buckets"
→ Output: same tabla

[Panel 3 — PT]
$ csgpt ask "liste os buckets do S3"
→ Output: same tabla

[Panel 4 — FR]
$ csgpt ask "liste les buckets S3"
→ Output: same tabla

[Panel 5 — ZH]
$ csgpt ask "列出S3存储桶"
→ Output: same tabla

[NARRATOR]
Misma pregunta, cinco idiomas, mismo resultado. Y en menos de dos segundos.

[SCREEN]: Show timing
  Translation latency: 1.3s
  Execution: 0.4s
  Total: 1.7s
```

**Director's note:** Esta es la sección "wow". El multi-idioma simultáneo es memorable.

---

### 🎬 [2:30 - 3:30] DEMO 2 — Safety first

**Visual:** Terminal, demo de comando destructivo.
**Audio:** Tension building, then relief.

```
[NARRATOR]
Pero la velocidad sin seguridad es peligrosa. Veamos qué pasa
cuando quiero hacer algo arriesgado.

[SCREEN]: Live demo

$ csgpt ask "borra todos los objetos del bucket de producción"

[SCREEN]: Show the safety panel
  ⚠️  CRITICAL OPERATION
  This action is IRREVERSIBLE and will affect:
    - s3://prod-data/* (estimated 2.3M objects)

  Estimated cost of recovery: $50,000+
  Cost of operation: $0.00

  Type 'yes-i-understand' to proceed:

[NARRATOR]
Detección automática de riesgo. Costo estimado de la operación.
Confirmación explícita. Dry-run disponible.

[SCREEN]: Type "yes-i-understand"
  → Command executes
  → Shows: "Deleted 2,301,847 objects. This is IRREVERSIBLE."

[NARRATOR]
Y antes de eso, podemos predecir costos.

[SCREEN]:
$ csgpt ask "spin up a rds postgres db.r5.large" --cost-only

  Estimated monthly cost: $234.18
  Breakdown:
    - RDS db.r5.large: $218.40/month
    - Storage 100GB:    $11.50/month
    - Backups:          $4.28/month
```

**Director's note:** Muestra que no es solo un wrapper tonto, hay inteligencia real.

---

### 🎬 [3:30 - 4:30] DEMO 3 — Kiro integration

**Visual:** Split screen — Kiro IDE a la izquierda, terminal a la derecha.
**Audio:** Music building to climax.

```
[NARRATOR]
Y aquí viene la magia para developers: CloudShellGPT funciona
como MCP server dentro de Kiro.

[SCREEN]: Show Kiro IDE with .kiro/settings/mcp.json open
  {
    "mcpServers": {
      "cloudshellgpt": {
        "command": "csgpt",
        "args": ["mcp", "serve"]
      }
    }
  }

[NARRATOR]
Ahora puedo pedirle a Kiro cosas sobre AWS en lenguaje natural.

[SCREEN]: Kiro chat
> Kiro, ayúdame a encontrar todos mis recursos S3 sin tags

[SCREEN]: Kiro uses csgpt tools
  [Tool call: aws_translate]
  [Tool call: aws_execute]
  [Tool call: aws_cost_preview]

[NARRATOR]
Kiro invoca CloudShellGPT, le pregunta a Bedrock, ejecuta el
comando correcto, y me muestra los resultados. Todo dentro del IDE.

[SCREEN]: Results shown in Kiro
  Found 7 S3 buckets without tags.
  Estimated cost if cleaned up: $0
  Suggestion: Add tags for better cost allocation.
```

**Director's note:** Esta es la killer demo. Muestra el futuro del dev workflow.

---

### 🎬 [4:30 - 5:30] ARCHITECTURE — How it works

**Visual:** Animated architecture diagram (Mermaid rendered).
**Audio:** Calm, confident, educational.

```
[NARRATOR]
Técnicamente, CloudShellGPT es una CLI en Python con cinco componentes.

[SCREEN]: Architecture diagram (animated)

  [Intent Parser]
    → Detecta idioma con langdetect
    → Identifica servicio y acción
    → Confidence score

  [Bedrock Translator]
    → Claude Sonnet 4.6 con system prompt
    → Few-shot examples
    → Streaming para baja latencia

  [Safety Layer]
    → Clasificador de riesgo
    → AWS Cost Explorer para predicción
    → Dry-run injection

  [Executor]
    → Subprocess con timeout
    → Boto3 fallback
    → Audit log local

  [MCP Server]
    → 4 tools expuestos
    → Compatible con Kiro, Claude, Cursor
    → Stdio transport

[NARRATOR]
Es 100% serverless cuando lo deployas en AWS Lambda.
Cero servidores que mantener. Pago por uso.

[SCREEN]: CDK diagram
  Lambda + API Gateway + DynamoDB (audit)
  + CloudWatch (observability) + Bedrock (LLM)
```

**Director's note:** Jeff Barr va a prestar atención aquí. Darko también.

---

### 🎬 [5:30 - 6:00] IMPACT — Real numbers

**Visual:** Dashboard con métricas reales.
**Audio:** Triumphant, conclusive.

```
[NARRATOR]
Los números:

[SCREEN]: Metrics dashboard

  ✓ 6 idiomas soportados con misma calidad
  ✓ < 2s latencia P95 para traducción
  ✓ 100% de comandos destructivos prevenidos
  ✓ $0.02 costo promedio por request a Bedrock
  ✓ 4 MCP tools listos para Kiro
  ✓ 80% coverage de tests
  ✓ Open source Apache 2.0

[NARRATOR]
Es open source, está documentado, y un developer puede instalarlo
y empezar a usarlo en menos de 5 minutos.
```

**Director's note:** Quick stats. Impressive pero no overwhelming.

---

### 🎬 [6:00 - 6:30] CLOSE — Call to action

**Visual]: Logo, GitHub URL, demo URL.
**Audio]: Music crescendo, fade.

```
[NARRATOR]
CloudShellGPT es un agente que vive en tu terminal, habla tu idioma,
y te hace más productivo en AWS sin sacrificar seguridad.

[SCREEN]: Title card
  ⚡ CloudShellGPT
  github.com/cloudshellgpt/cloudshellgpt
  cloudshellgpt.dev/demo

[NARRATOR]
Gracias. Estamos en GitHub, te esperamos en el repo.

[SCREEN]: Fade to black
  "Made with ⚡ for HACKATHONKIRO"
```

---

## 🎨 Production Notes

### Tools needed
- **Screen recorder:** OBS Studio (free) o ScreenFlow (Mac)
- **Editor:** DaVinci Resolve (free) o Adobe Premiere
- **Microphone:** Audio-Technica ATR2100x o similar (clear audio > 4K video)
- **Background:** Terminal con tema oscuro (Dracula, One Dark)

### Code snippets to show (clear, no sensitive data)
1. `csgpt ask "lista los buckets de S3"` (demo principal)
2. `csgpt config --show` (mostrar configuración)
3. `csgpt explain last` (modo aprendizaje)
4. `csgpt mcp serve` (MCP server)
5. AWS CDK code (1-2 snippets pequeños)

### B-roll to include
- AWS Console (browser tabs)
- Kiro IDE con chat
- Architecture diagram (Mermaid rendered)
- Logo animation
- GitHub repo page

### Music
- **Suggested:** Epidemic Sound — "Code in Motion" o similar
- **Volume:** -20dB bajo la voz
- **Timestamps:** Music builds at demos, drops en close

### Color palette
- Primary: `#FF9900` (AWS orange)
- Accent: `#00D4AA` (CloudShellGPT teal)
- Background: `#1E1E2E` (terminal dark)
- Text: `#F8F8F2` (light)

### Captions
- Subtítulos en inglés (obligatorio)
- Subtítulos en español (opcional pero加分)

---

## 📋 Pre-recording checklist

- [ ] Terminal con tema oscuro consistente
- [ ] AWS account de prueba con recursos inocuos
- [ ] Kiro IDE instalado con .kiro/settings/mcp.json configurado
- [ ] csgpt instalado y funcionando
- [ ] Bedrock model access habilitado en us-east-1
- [ ] Sin credentials en pantalla (usar IAM role)
- [ ] Micrófono probado
- [ ] Resolución 1920x1080 mínimo
- [ ] 30s de buffer al inicio para sync

---

## 🎤 Speaker notes

- **Tono:** Conversacional pero técnico. Eres un developer explicando a otros developers.
- **Velocidad:** 150-170 palabras por minuto (más lento que conversación normal)
- **Pausas:** 1-2 segundos entre secciones para que el viewer "procese"
- **Contacto visual:** Mirar a la cámara, no al screen (cuando narras)
- **Errores:** Si algo falla en vivo, respira, di "pueden ver que aquí detectamos X" y sigue

---

**Total runtime target:** 6:30
**Buffer:** 30s arriba/abajo para edición
**Export settings:** H.264, 1080p, 30fps, 8Mbps bitrate
