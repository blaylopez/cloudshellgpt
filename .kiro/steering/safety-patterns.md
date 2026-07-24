---
inclusion: fileMatch
fileMatchPattern: "**/safety.py"
---

# Safety Patterns — CloudShellGPT

## Philosophy

CloudShellGPT must NEVER execute a destructive command without explicit user consent. The safety layer is the last line of defense between a natural language mistake and production data loss.

## Risk Classification

| Level | Criteria | Action Required |
|-------|----------|-----------------|
| `low` | Read-only operations (list, describe, get, head, wait) | Execute immediately |
| `medium` | Create/update operations with easy rollback (e.g., create-bucket, tag-resource, put-metric-alarm, enable-*, create-snapshot) | Show plan, then execute |
| `high` | Delete/terminate/revoke operations on single resources (e.g., delete-bucket, terminate-instances, revoke-security-group-ingress, detach-volume) | Require typed confirmation |
| `critical` | Recursive/batch delete, force operations, skip-safety-net flags (e.g., `--skip-final-snapshot`, `--force-delete`, `--no-preserve-root`, empty-bucket, delete-stack with retain=none) | Require "yes-i-understand" + dry-run first |

**Heurística para clasificar operaciones medium vs high:**
- Si la operación tiene un inverso directo y no destruye datos (create → delete, attach → detach), es `medium`
- Si la operación elimina datos o acceso y requiere recreación manual, es `high`
- Si hay duda, clasificar hacia arriba (prefer false positive over false negative)

## Destructive Patterns to Detect

These patterns in a command MUST trigger risk upgrade:

```python
DESTRUCTIVE_PATTERNS = [
    # Generic destructive verbs
    "delete",
    "terminate",
    "rm",
    "remove",
    "drop",
    "destroy",
    "force",
    "purge",
    "wipe",
    "nuke",
    # AWS-specific destructive actions
    "deregister",
    "revoke",
    "detach",
    "disable",
    "release",
    "empty",
    # Dangerous flags
    "--recursive",
    "--force",
    "-f",
    "--no-preserve",
    "--skip-final-snapshot",
    "--force-delete",
    "--permanently-delete",
    "--no-undo",
    "--force-destroy",
    "--delete-all-versions",
    "--bypass-governance-retention",
    "--no-preserve-root",
]
```

> **Nota:** Esta lista es la base mínima. El safety layer también debe detectar combinaciones peligrosas en contexto (ej: `update-stack` + `--use-previous-template` sin changeset previo).

## Confirmation Flow

```
low     → execute directly
medium  → show command + explanation, ask Y/N
high    → show command + affected resources + cost, ask typed confirmation
critical → show command + warning banner + affected resources + cost estimate
           → force dry-run first
           → then ask user to type "yes-i-understand"
```

## Cost Estimation Rules

La estimación de costos es responsabilidad compartida entre `safety.py` y `cost.py`:

- **`cost.py`** — implementa la lógica de cálculo: consulta Cost Explorer, estima costos por servicio, genera el breakdown por componente
- **`safety.py`** — consume el resultado de `cost.py` para decidir si alertar al usuario o bloquear la ejecución según el umbral configurado

Reglas:
- Si un comando crea recursos, `cost.py` debe estimar el costo mensual ANTES de ejecutar
- `safety.py` compara el resultado contra `max_cost_alert` (config). Si lo excede, muestra warning explícito
- El cost breakdown (de `cost.py`) debe listar cada componente por separado
- Si Cost Explorer API falla, `cost.py` retorna estado "unknown" y `safety.py` muestra "costo desconocido — proceder con precaución"

## Dry-Run Injection

Services that support `--dry-run`:
- `ec2 run-instances`
- `ec2 terminate-instances`
- `ec2 delete-volume`
- `ec2 create-vpc`
- `ec2 authorize-security-group-ingress`
- `ec2 revoke-security-group-ingress`
- `rds delete-db-instance`
- `rds create-db-instance`
- `s3api delete-bucket`
- `iam delete-user`
- `cloudformation create-stack` (via change sets)
- `cloudformation update-stack` (via change sets)
- `lambda invoke` (with `--qualifier` for alias testing)

> **Nota:** Esta lista no es exhaustiva. Si un comando no está aquí, no inyectar `--dry-run` — en su lugar, mostrar el comando sin ejecutar y pedir confirmación explícita.

For services without native dry-run support, prepend a comment marker and show the command WITHOUT executing.

## Shell Injection Prevention

The executor MUST reject commands containing shell metacharacters:
- Pipe (`|`)
- Command chaining (`&&`, `||`, `;`)
- Subshell execution (`` ` ` ``, `$(...)`)
- Redirects (`>`, `>>`, `<`, `2>`)
- Background execution (`&` at end of command)
- Glob expansion in dangerous context (`*` outside of quoted arguments)
- Newlines or null bytes (`\n`, `\0`)
- Environment variable injection (`$VAR`, `${VAR}`)
- Here-doc/here-string (`<<`, `<<<`)
- Process substitution (`<(...)`, `>(...)`)

Only pure `aws ...` commands are allowed.

> **Excepción:** El argumento literal `-` (stdin/stdout) es válido en algunos comandos AWS (ej: `aws s3 cp - s3://bucket/file`). No rechazar `-` como carácter aislado en posición de argumento, solo rechazar los operadores shell `<` y `>` como sintaxis de redirección.

## Audit Before Execute

The audit logger MUST write the entry BEFORE the command executes. This ensures we have a record even if the command crashes the process.

```python
# Correct order:
audit.log(intent, command, risk)  # 1. Log first
result = executor.run(command)  # 2. Execute second
```

## PII Detection (opt-in)

When `enable_pii_detection` is true in config:
1. After execution, scan stdout with Amazon Comprehend
2. If PII detected (emails, SSNs, credit cards), redact before displaying
3. Show warning: "PII detected and redacted. Use --show-pii to override."
4. Never log PII to audit file

## Never Trust LLM Output Blindly

The Bedrock translator may return a risk_level that's too low. The safety layer MUST independently verify:
- Check for destructive patterns regardless of LLM's risk assessment
- Upgrade risk if patterns detected
- Never downgrade risk below what the LLM suggested
