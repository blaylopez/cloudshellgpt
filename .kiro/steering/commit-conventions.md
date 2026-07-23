# Commit & Git Conventions — CloudShellGPT

## Commit Message Format

Use Conventional Commits:

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

### Types

| Type | When to use |
|------|-------------|
| `feat` | New feature (adds user-facing functionality) |
| `fix` | Bug fix |
| `test` | Adding or updating tests |
| `docs` | Documentation only |
| `refactor` | Code change that doesn't fix a bug or add a feature |
| `ci` | CI/CD changes (GitHub Actions, pre-commit) |
| `infra` | Infrastructure changes (CDK stacks) |
| `chore` | Maintenance (deps, config, tooling) |
| `perf` | Performance improvement |

### Scopes

| Scope | Modules |
|-------|---------|
| `cli` | cli.py |
| `intent` | intent.py |
| `bedrock` | bedrock_translator.py |
| `safety` | safety.py |
| `executor` | executor.py |
| `formatter` | formatter.py |
| `audit` | audit.py |
| `cost` | cost.py |
| `learning` | learning.py |
| `mcp` | mcp_server.py |
| `config` | config.py |
| `cdk` | infrastructure/* |

### Examples

```
feat(intent): add support for CloudWatch Logs Insights queries
fix(executor): handle command with spaces in path arguments
test(safety): add unit tests for destructive pattern detection
docs: add IAM permissions guide for new users
infra(cdk): add CloudWatch alarm for Lambda errors > 5%
ci: add ruff + mypy check to GitHub Actions workflow
```

## Branch Strategy

- `main` — protected, always deployable (producción)
- `dev` — protected, rama de integración (QA/staging antes de main)
- `feature/<short-description>` — new features (se crean desde `dev`)
- `fix/<short-description>` — bug fixes (se crean desde `dev`)
- `infra/<short-description>` — infrastructure changes (se crean desde `dev`)
- `docs/<short-description>` — documentation (se crean desde `dev`)

### Flujo de merge

1. Las ramas de trabajo (`feature/*`, `fix/*`, `infra/*`, `docs/*`) se mergean a `dev` vía PR
2. Cuando `dev` está estable y pasa QA, se mergea a `main` vía PR

### Rules

- Never push directly to `main` or `dev`
- All changes via Pull Request with at least 1 review
- PRs a `dev` deben pasar CI (lint + tests) antes de merge
- PRs a `main` requieren que `dev` esté verde en CI y aprobación del equipo
- Squash merge preferred (clean history)
- Delete branch after merge

## PR Template

```markdown
## What does this PR do?

Brief description of the change.

## How to test

Steps to verify the change works.

## Checklist

- [ ] Tests pass locally (`pytest`)
- [ ] Linter passes (`ruff check .`)
- [ ] Type checker passes (`mypy src/`)
- [ ] No secrets committed
- [ ] Acceptance criteria covered (if applicable)
```

## File Ownership (para trabajo en paralelo)

Para evitar conflictos, cada persona del equipo tiene ownership:

- **Persona 1 (Core + Tests):** `tests/`, `intent.py`, `config.py`
- **Persona 2 (Infra + CI/CD):** `infrastructure/`, `.github/`, archivos raíz (LICENSE, CONTRIBUTING)
- **Persona 3 (UX + Safety):** `executor.py`, `safety.py`, `formatter.py`, `mcp_server.py`
- **Persona 4 (Docs + Demo):** `docs/`, `README.md`, `VIDEO_PITCH.md`, `eval/`

Si necesitas tocar un archivo de otra persona, avisa en el canal del equipo antes de commitear.
