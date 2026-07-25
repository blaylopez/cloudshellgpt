"""Configuration manager — handles user settings and defaults."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONFIG_DIR = Path.home() / ".csgpt"
CONFIG_FILE = CONFIG_DIR / "config.yaml"


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class ConfigError(Exception):
    """Raised when configuration loading, saving, or validation fails."""


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class OutputFormat(StrEnum):
    """Supported output formats."""

    TABLE = "table"
    JSON = "json"
    YAML = "yaml"
    CSV = "csv"


# ---------------------------------------------------------------------------
# YAML settings source
# ---------------------------------------------------------------------------


class YamlSettingsSource(PydanticBaseSettingsSource):
    """Load settings from a YAML file on disk."""

    def __init__(self, settings_cls: type[BaseSettings], yaml_path: Path) -> None:
        super().__init__(settings_cls)
        self._yaml_path = yaml_path

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        """Return the value for a given field from the YAML data."""
        data = self._load_yaml()
        value = data.get(field_name)
        return value, field_name, False

    def __call__(self) -> dict[str, Any]:
        """Return all values from the YAML file."""
        return self._load_yaml()

    def _load_yaml(self) -> dict[str, Any]:
        """Read and parse the YAML config file."""
        if not self._yaml_path.exists():
            return {}
        try:
            with self._yaml_path.open() as f:
                data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
        except (yaml.YAMLError, OSError) as exc:
            raise ConfigError(f"Failed to read config file {self._yaml_path}: {exc}") from exc


# ---------------------------------------------------------------------------
# Pydantic Settings model
# ---------------------------------------------------------------------------


class Config(BaseSettings):
    """User configuration for CloudShellGPT.

    Settings are resolved in order of priority (highest first):
    1. Environment variables (prefix CSGPT_)
    2. YAML config file (~/.csgpt/config.yaml)
    3. Field defaults
    """

    region: str = Field(default="us-east-1", description="AWS region for Bedrock calls")
    language: str = Field(default="auto", description="UI language (auto, en, es, pt, etc.)")
    default_output: str = Field(
        default="table", description="Output format: table, json, yaml, csv"
    )
    bedrock_model: str = Field(
        default="anthropic.claude-3-5-sonnet-20241022-v2:0",
        description="Bedrock model ID for translations",
    )
    require_confirmation_for: list[str] = Field(
        default_factory=lambda: ["high", "critical"],
        description="Risk levels that require user confirmation",
    )
    enable_pii_detection: bool = Field(
        default=False, description="Enable PII detection via Comprehend"
    )
    enable_cost_preview: bool = Field(
        default=True, description="Show cost estimate before execution"
    )
    enable_learning_mode: bool = Field(
        default=True, description="Show educational tips after execution"
    )
    max_cost_alert: int = Field(default=100, description="USD threshold for cost alert warnings")

    model_config = {
        "env_prefix": "CSGPT_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @field_validator("default_output")
    @classmethod
    def validate_output_format(cls, v: str) -> str:
        """Ensure default_output is one of the supported formats."""
        allowed = {fmt.value for fmt in OutputFormat}
        if v not in allowed:
            msg = f"default_output must be one of {sorted(allowed)}, got '{v}'"
            raise ValueError(msg)
        return v

    @field_validator("max_cost_alert")
    @classmethod
    def validate_max_cost_alert(cls, v: int) -> int:
        """Ensure max_cost_alert is a positive value."""
        if v < 0:
            msg = f"max_cost_alert must be >= 0, got {v}"
            raise ValueError(msg)
        return v

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Customise settings sources to include YAML file.

        Priority order (highest first):
        1. init_settings (programmatic overrides)
        2. env_settings (CSGPT_* env vars)
        3. dotenv_settings (.env file)
        4. yaml_settings (~/.csgpt/config.yaml)
        5. file_secret_settings
        """
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlSettingsSource(settings_cls, CONFIG_FILE),
            file_secret_settings,
        )


# ---------------------------------------------------------------------------
# ConfigManager
# ---------------------------------------------------------------------------


class ConfigManager:
    """Manages the user's CloudShellGPT configuration.

    Provides load, save, get, set, and reload operations over the
    Config model backed by ~/.csgpt/config.yaml.
    """

    def __init__(self, config_path: Path | None = None) -> None:
        """Initialize the ConfigManager.

        Creates the config file with defaults if it doesn't exist.

        Args:
            config_path: Path to the YAML config file. Defaults to ~/.csgpt/config.yaml.
        """
        self.config_path = config_path or CONFIG_FILE
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        file_existed = self.config_path.exists()
        self._config = self._load()
        if not file_existed:
            self.save()

    @property
    def config(self) -> Config:
        """Return the current Config instance."""
        return self._config

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value by key.

        Args:
            key: The configuration field name.
            default: Fallback value if the key doesn't exist.

        Returns:
            The configuration value or the default.
        """
        return getattr(self._config, key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a config value.

        Args:
            key: The configuration field name.
            value: The new value to assign.

        Raises:
            ConfigError: If the key is not a valid config field or validation fails.
        """
        if key not in self._config.model_fields:
            raise ConfigError(f"Unknown config key: '{key}'")
        try:
            data = self._config.model_dump()
            data[key] = value
            self._config = Config(**data)
        except Exception as exc:
            raise ConfigError(f"Invalid value for '{key}': {exc}") from exc

    def save(self) -> None:
        """Save the current config to disk.

        Raises:
            ConfigError: If writing to disk fails.
        """
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with self.config_path.open("w") as f:
                yaml.dump(self._config.model_dump(), f, default_flow_style=False)
        except OSError as exc:
            raise ConfigError(f"Failed to save config to {self.config_path}: {exc}") from exc

    def reset_defaults(self) -> None:
        """Reset configuration to defaults and save to disk.

        Overwrites the current config file with all default values.
        """
        self._config = Config()
        self.save()

    def reload(self) -> None:
        """Reload config from disk, picking up any external changes."""
        self._config = self._load()

    def to_yaml(self) -> str:
        """Return the config as a YAML string.

        Returns:
            YAML-formatted string of the current configuration.
        """
        result: str = yaml.dump(self._config.model_dump(), default_flow_style=False)
        return result

    def _load(self) -> Config:
        """Load config from YAML file merged with env vars and defaults.

        Returns:
            A validated Config instance.

        Raises:
            ConfigError: If the config file is malformed.
        """
        if not self.config_path.exists():
            return Config()
        try:
            with self.config_path.open() as f:
                data = yaml.safe_load(f) or {}
            if not isinstance(data, dict):
                raise ConfigError(f"Config file {self.config_path} must contain a YAML mapping")
            return Config(**data)
        except ConfigError:
            raise
        except Exception as exc:
            raise ConfigError(f"Failed to load config from {self.config_path}: {exc}") from exc
