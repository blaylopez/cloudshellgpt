# Code Style — CloudShellGPT

## Python Version & Typing

- Python 3.12+ required. Use modern syntax: `str | None`, `list[str]`, `dict[str, Any]`
- All functions must have type annotations (enforced by mypy strict mode)
- Use `from __future__ import annotations` at the top of every module for forward references

## Formatting & Linting

- Line length: 100 characters max (configured in ruff)
- Linter: ruff with rules `E, F, I, N, W, UP, Y, B, A, C4, PT`
- Type checker: mypy in strict mode
- Run before committing: `ruff check . --fix && ruff format . && mypy src/`

## Module Structure

Every module follows this order:
1. Module docstring (one line describing purpose)
2. `from __future__ import annotations`
3. Standard library imports
4. Third-party imports
5. Local imports (from cloudshellgpt.*)
6. Constants
7. Pydantic models
8. Classes
9. Public functions (module-level API, e.g. `parse_intent`, `run_command`)
10. Private helper functions (prefixed with `_`, e.g. `_detect_service`, `_build_prompt`)

## Naming Conventions

- Classes: PascalCase (`IntentParser`, `SafetyCheck`)
- Functions/methods: snake_case (`parse_intent`, `_detect_service`)
- Constants: UPPER_SNAKE_CASE (`DEFAULT_TIMEOUT`, `MODEL_ID`)
- Private methods: prefix with `_` (`_build_user_message`)
- Modules: snake_case (`bedrock_translator.py`)

## Pydantic Models

- All data structures that cross module boundaries must be Pydantic BaseModel
- Use `Field(...)` with descriptions for non-obvious fields
- Use `default_factory` for mutable defaults
- Keep models immutable where possible

## Error Handling

- Custom exceptions per module (e.g., `BedrockError`, `ExecutorError`)
- Never swallow exceptions silently — log or re-raise
- Use structured error messages: include what failed, why, and what to do
- The audit logger is the one exception: it must never crash the user-facing flow

## Docstrings

- Google style docstrings for all public classes and methods
- Include Args, Returns, and Raises sections when applicable
- One-line docstrings for simple helpers

```python
def translate(self, intent: Intent) -> Translation:
    """Translate an Intent into an AWS CLI command.

    Args:
        intent: The parsed user intent

    Returns:
        Translation object with the command and metadata

    Raises:
        BedrockError: If translation fails
    """
```

## Testing Conventions

- Test files mirror source: `src/cloudshellgpt/intent.py` → `tests/unit/test_intent.py`
- Use pytest fixtures for shared setup
- Mock AWS calls with moto (never hit real AWS in unit tests)
- Integration tests in `tests/integration/` can use real AWS (sandbox account only)
- Name tests descriptively: `test_parse_spanish_list_intent_returns_high_confidence`
