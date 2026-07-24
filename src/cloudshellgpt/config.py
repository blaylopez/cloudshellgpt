"""Configuration manager — handles user settings and defaults."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class Config(BaseModel):
    """User configuration for CloudShellGPT."""

    region: str = "us-east-1"
    language: str = "auto"  # auto, en, es, pt, etc.
    default_output: str = "table"  # table, json, yaml, csv
    bedrock_model: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    require_confirmation_for: list[str] = Field(default_factory=lambda: ["high", "critical"])
    enable_pii_detection: bool = False
    enable_cost_preview: bool = True
    enable_learning_mode: bool = True
    max_cost_alert: float = 100.0  # USD


class ConfigManager:
    """Manages the user's CloudShellGPT configuration."""

    DEFAULT_PATH = Path.home() / ".csgpt" / "config.yaml"

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or self.DEFAULT_PATH
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config = self._load()

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value by key."""
        return getattr(self._config, key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a config value."""
        setattr(self._config, key, value)

    def to_yaml(self) -> str:
        """Return the config as YAML string."""
        result: str = yaml.dump(self._config.model_dump(), default_flow_style=False)
        return result

    def save(self) -> None:
        """Save the current config to disk."""
        with self.config_path.open("w") as f:
            yaml.dump(self._config.model_dump(), f, default_flow_style=False)

    def _load(self) -> Config:
        """Load config from disk or return defaults."""
        if not self.config_path.exists():
            return Config()
        with self.config_path.open() as f:
            data = yaml.safe_load(f) or {}
        return Config(**data)
