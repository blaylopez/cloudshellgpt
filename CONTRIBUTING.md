# Contribución — CloudShellGPT

¡Gracias por tu interés en contribuir a CloudShellGPT! 🎉

## Requisitos previos

- Python 3.12+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (gestor de paquetes)
- Credenciales AWS configuradas (`aws configure`)
- Modelo Claude Sonnet 4.6 habilitado en Bedrock (region us-east-1)

## Setup de desarrollo

```bash
# 1. Clonar el repositorio
git clone https://github.com/blaylopez/cloudshellgpt
cd cloudshellgpt

# 2. Instalar dependencias (incluyendo dev)
uv sync --all-extras

# 3. Instalar pre-commit hooks
pre-commit install

# 4. Verificar que todo funciona
uv run pytest tests/unit/ -q
uv run ruff check .
uv run ruff format --check .
```

## Flujo de trabajo

1. Crea una rama desde `dev`:
   ```bash
   git checkout dev
   git pull origin dev
   git checkout -b feature/mi-feature
   ```

2. Haz tus cambios siguiendo las convenciones del proyecto

3. Verifica antes de commitear:
   ```bash
   uv run ruff check . --fix
   uv run ruff format .
   uv run pytest tests/unit/ -q
   ```

4. Commit con [Conventional Commits](https://www.conventionalcommits.org/):
   ```bash
   git commit -m "feat(intent): add support for CloudWatch queries"
   ```

5. Push y crea un PR hacia `dev`:
   ```bash
   git push -u origin feature/mi-feature
   gh pr create --base dev
   ```

## Convenciones de código

- **Line length:** 100 caracteres máximo
- **Linter:** ruff (E, F, I, N, W, UP, B, A, C4, PT)
- **Type checker:** mypy en modo estricto
- **Docstrings:** Google style
- **Naming:** PascalCase para clases, snake_case para funciones, UPPER_SNAKE para constantes

## Estructura de tests

Los tests están en `tests/unit/` y siguen la estructura del source:

```
src/cloudshellgpt/intent.py  →  tests/unit/test_intent.py
src/cloudshellgpt/safety.py  →  tests/unit/test_safety.py
```

- Usa `pytest` fixtures para setup compartido
- Mockea AWS con `moto` (nunca llames a AWS real en unit tests)
- Nombra tests descriptivamente: `test_parse_spanish_intent_returns_high_confidence`

## Tipos de commit

| Type | Cuándo |
|------|--------|
| `feat` | Nueva funcionalidad |
| `fix` | Corrección de bug |
| `test` | Tests nuevos o actualizados |
| `docs` | Solo documentación |
| `refactor` | Cambio sin fix ni feature |
| `ci` | CI/CD (GitHub Actions) |
| `chore` | Mantenimiento (deps, config) |

## Ramas

- `main` — producción (protegida)
- `dev` — integración (protegida)
- `feature/*` — nuevas funcionalidades
- `fix/*` — correcciones
- `docs/*` — documentación

## ¿Preguntas?

Abre un [issue](https://github.com/blaylopez/cloudshellgpt/issues) o consulta el README.
