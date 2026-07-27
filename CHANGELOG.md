# Changelog

Todos los cambios relevantes del proyecto están documentados aquí.

El formato se basa en [Keep a Changelog](https://keepachangelog.com/es/1.1.0/),
y el proyecto sigue [Semantic Versioning](https://semver.org/lang/es/).

## [1.0.2] - 2026-07-27

### Fixed
- `executor.py`: Agregado `stdin=subprocess.DEVNULL` para evitar que `aws.exe` herede el pipe stdio del MCP server (fix timeout en Windows)
- `mcp_server.py`: `_tool_execute` ahora lee el timeout desde la configuración del usuario
- `config.py`: Uso de `Config.model_fields` (clase) en vez de instancia (deprecado en Pydantic V2.11)
- `cost.py`: Reemplazo de `datetime.utcnow()` con `datetime.now(UTC)` (deprecado en Python 3.12+)

### Added
- `.github/workflows/publish.yml`: Publicación automatizada a PyPI via Trusted Publisher
- `LICENSE`: Archivo Apache 2.0

### Changed
- `README.md`: Overhaul completo con 7 ejemplos probados, badge de PyPI, instalación desde PyPI
- `pyproject.toml`: URLs corregidas a `github.com/blaylopez/cloudshellgpt`

## [1.0.1] - 2026-07-27

### Changed
- `README.md`: Actualización de ejemplos y badges para reflejar publicación en PyPI

## [1.0.0] - 2026-07-27

### Added
- CLI completo con comandos: `ask`, `explain`, `learn`, `cost-summary`, `mcp`, `config`
- Traducción de lenguaje natural a AWS CLI via Amazon Bedrock (Claude Sonnet 4.6)
- Soporte multi-idioma: ES, EN, PT, ZH, FR (detección automática + config)
- Safety Layer con clasificación de riesgo (low, medium, high, critical)
- Cost Preview integrado con AWS Cost Explorer
- MCP Server con 4 tools: `aws_translate`, `aws_execute`, `aws_cost_preview`, `aws_explain`
- Modo aprendizaje (`--explain`) con tips y comandos relacionados
- Audit logging local en `~/.csgpt/audit.log`
- Executor con shell injection prevention y timeout configurable
- Configuración via `~/.csgpt/config.yaml`
- CI pipeline con ruff lint + format + pytest

[1.0.2]: https://github.com/blaylopez/cloudshellgpt/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/blaylopez/cloudshellgpt/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/blaylopez/cloudshellgpt/releases/tag/v1.0.0
