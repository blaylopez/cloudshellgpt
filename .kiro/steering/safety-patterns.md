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
| `low` | Read-only operations (list, describe, get) | Execute immediately |
| `medium` | Create/update operations that are reversible | Show plan, then execute |
| `high` | Delete/terminate operations | Require typed confirmation |
| `critical` | Recursive delete, force operations, production-affecting | Require "yes-i-understand" + dry-run first |

## Destructive Patterns to Detect

These patterns in a command MUST trigger risk upgrade:

```python
DESTRUCTIVE_PATTERNS = [
    "delete", "terminate", "rm", "remove", "drop", "destroy", "force",
    "--recursive", "--force", "-f", "--no-preserve",
    "purge", "wipe", "nuke",
]
```

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

- If a command creates resources, estimate monthly cost BEFORE executing
- If estimated cost > `max_cost_alert` ($100 default), show explicit warning
- Cost breakdown should list each component separately
- If Cost Explorer API fails, show "cost unknown — proceed with caution"

## Dry-Run Injection

Services that support `--dry-run`:
- `ec2 run-instances`
- `ec2 terminate-instances`
- `ec2 delete-volume`
- `rds delete-db-instance`
- `s3api delete-bucket`
- `iam delete-user`

For services without native dry-run support, prepend a comment marker and show the command WITHOUT executing.

## Shell Injection Prevention

The executor MUST reject commands containing:
- Pipe (`|`)
- Command chaining (`&&`, `||`, `;`)
- Subshell execution (`` ` ` ``, `$(...)`)
- Redirects (`>`, `>>`, `<`)

Only pure `aws ...` commands are allowed.

## Audit Before Execute

The audit logger MUST write the entry BEFORE the command executes. This ensures we have a record even if the command crashes the process.

```python
# Correct order:
audit.log(intent, command, risk)  # 1. Log first
result = executor.run(command)     # 2. Execute second
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
