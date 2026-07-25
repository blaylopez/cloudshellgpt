"""Tests unitarios para ConfigManager — auto-creación de config con defaults."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from cloudshellgpt.config import Config, ConfigManager


@pytest.mark.unit
class TestConfigManagerAutoCreate:
    """Verifica que ConfigManager crea el archivo con defaults al inicializarse."""

    def test_creates_config_file_when_not_exists(self, tmp_path: Path) -> None:
        """El archivo config.yaml debe crearse automáticamente con defaults."""
        config_path = tmp_path / "config.yaml"
        assert not config_path.exists()

        ConfigManager(config_path=config_path)

        assert config_path.exists()

    def test_auto_created_config_has_correct_defaults(self, tmp_path: Path) -> None:
        """El archivo creado debe tener todos los valores por defecto del spec."""
        config_path = tmp_path / "config.yaml"
        ConfigManager(config_path=config_path)

        with config_path.open() as f:
            data = yaml.safe_load(f)

        assert data["region"] == "us-east-1"
        assert data["language"] == "auto"
        assert data["default_output"] == "table"
        assert data["bedrock_model"] == "anthropic.claude-3-5-sonnet-20241022-v2:0"
        assert data["require_confirmation_for"] == ["high", "critical"]
        assert data["enable_cost_preview"] is True
        assert data["enable_learning_mode"] is True
        assert data["max_cost_alert"] == 100

    def test_does_not_overwrite_existing_config(self, tmp_path: Path) -> None:
        """Si el archivo ya existe, NO debe sobreescribirlo."""
        config_path = tmp_path / "config.yaml"
        custom_data = {"region": "eu-west-1", "language": "es"}
        with config_path.open("w") as f:
            yaml.dump(custom_data, f)

        cfg = ConfigManager(config_path=config_path)

        assert cfg.get("region") == "eu-west-1"
        assert cfg.get("language") == "es"

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        """Debe crear el directorio padre si no existe."""
        config_path = tmp_path / "subdir" / "nested" / "config.yaml"
        assert not config_path.parent.exists()

        ConfigManager(config_path=config_path)

        assert config_path.exists()


@pytest.mark.unit
class TestConfigManagerResetDefaults:
    """Verifica que reset_defaults() recrea el config con valores por defecto."""

    def test_reset_defaults_overwrites_custom_config(self, tmp_path: Path) -> None:
        """reset_defaults() debe sobreescribir configuración existente."""
        config_path = tmp_path / "config.yaml"
        custom_data = {"region": "ap-southeast-1", "max_cost_alert": 500}
        with config_path.open("w") as f:
            yaml.dump(custom_data, f)

        cfg = ConfigManager(config_path=config_path)
        assert cfg.get("region") == "ap-southeast-1"

        cfg.reset_defaults()

        assert cfg.get("region") == "us-east-1"
        assert cfg.get("max_cost_alert") == 100

        # Verificar que se guardó en disco
        with config_path.open() as f:
            data = yaml.safe_load(f)
        assert data["region"] == "us-east-1"

    def test_reset_defaults_persists_all_fields(self, tmp_path: Path) -> None:
        """reset_defaults() debe guardar todos los campos del modelo Config."""
        config_path = tmp_path / "config.yaml"
        cfg = ConfigManager(config_path=config_path)
        cfg.reset_defaults()

        with config_path.open() as f:
            data = yaml.safe_load(f)

        expected_fields = set(Config.model_fields.keys())
        assert set(data.keys()) == expected_fields
