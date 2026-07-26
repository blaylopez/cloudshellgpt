"""Tests unitarios para ConfigManager — auto-creación de config con defaults."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from cloudshellgpt.config import Config, ConfigError, ConfigManager


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


@pytest.mark.unit
class TestConfigTimeout:
    """Verifica el campo timeout en Config."""

    def test_timeout_defaults_to_30(self) -> None:
        """El timeout por defecto debe ser 30 segundos."""
        cfg = Config()
        assert cfg.timeout == 30

    def test_timeout_accepts_positive_value(self) -> None:
        """El timeout debe aceptar valores positivos."""
        cfg = Config(timeout=60)
        assert cfg.timeout == 60

    def test_timeout_rejects_zero(self) -> None:
        """El timeout debe rechazar el valor 0."""
        with pytest.raises(Exception, match="timeout must be > 0"):
            Config(timeout=0)

    def test_timeout_rejects_negative(self) -> None:
        """El timeout debe rechazar valores negativos."""
        with pytest.raises(Exception, match="timeout must be > 0"):
            Config(timeout=-5)

    def test_timeout_from_yaml(self, tmp_path: Path) -> None:
        """El timeout debe cargarse desde config.yaml."""
        config_path = tmp_path / "config.yaml"
        with config_path.open("w") as f:
            yaml.dump({"timeout": 120}, f)

        cfg = ConfigManager(config_path=config_path)
        assert cfg.get("timeout") == 120

    def test_timeout_from_env_var(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """El timeout debe ser configurable via CSGPT_TIMEOUT."""
        monkeypatch.setenv("CSGPT_TIMEOUT", "45")
        config_path = tmp_path / "config.yaml"

        cfg = ConfigManager(config_path=config_path)
        assert cfg.get("timeout") == 45

    def test_timeout_in_auto_created_config(self, tmp_path: Path) -> None:
        """El archivo auto-creado debe incluir el campo timeout con valor 30."""
        config_path = tmp_path / "config.yaml"
        ConfigManager(config_path=config_path)

        with config_path.open() as f:
            data = yaml.safe_load(f)

        assert data["timeout"] == 30


# ---------------------------------------------------------------------------
# Tests: ConfigManager.set() — setting config values
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConfigManagerSet:
    """Verify ConfigManager.set() updates values correctly."""

    def test_set_valid_key(self, tmp_path: Path) -> None:
        """set() updates a valid key."""
        config_path = tmp_path / "config.yaml"
        cfg = ConfigManager(config_path=config_path)
        cfg.set("region", "eu-west-1")
        assert cfg.get("region") == "eu-west-1"

    def test_set_unknown_key_raises_config_error(self, tmp_path: Path) -> None:
        """set() raises ConfigError for an unknown key."""
        config_path = tmp_path / "config.yaml"
        cfg = ConfigManager(config_path=config_path)
        with pytest.raises(ConfigError, match="Unknown config key"):
            cfg.set("nonexistent_key", "value")

    def test_set_invalid_value_raises_config_error(self, tmp_path: Path) -> None:
        """set() raises ConfigError for invalid values (validation failure)."""
        config_path = tmp_path / "config.yaml"
        cfg = ConfigManager(config_path=config_path)
        with pytest.raises(ConfigError, match="Invalid value"):
            cfg.set("default_output", "invalid_format")

    def test_set_max_cost_alert_negative_raises(self, tmp_path: Path) -> None:
        """set() with negative max_cost_alert raises ConfigError."""
        config_path = tmp_path / "config.yaml"
        cfg = ConfigManager(config_path=config_path)
        with pytest.raises(ConfigError, match="Invalid value"):
            cfg.set("max_cost_alert", -10)


# ---------------------------------------------------------------------------
# Tests: ConfigManager.reload() and to_yaml()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConfigManagerReload:
    """Verify ConfigManager.reload() picks up external changes."""

    def test_reload_picks_up_disk_changes(self, tmp_path: Path) -> None:
        """reload() reflects changes made externally to the YAML file."""
        config_path = tmp_path / "config.yaml"
        cfg = ConfigManager(config_path=config_path)
        assert cfg.get("region") == "us-east-1"

        # External modification
        with config_path.open("w") as f:
            yaml.dump({"region": "ap-northeast-1"}, f)

        cfg.reload()
        assert cfg.get("region") == "ap-northeast-1"

    def test_to_yaml_returns_string(self, tmp_path: Path) -> None:
        """to_yaml() returns a YAML-formatted string."""
        config_path = tmp_path / "config.yaml"
        cfg = ConfigManager(config_path=config_path)
        result = cfg.to_yaml()
        assert isinstance(result, str)
        assert "region:" in result
        assert "us-east-1" in result

    def test_config_property(self, tmp_path: Path) -> None:
        """config property returns the Config instance."""
        config_path = tmp_path / "config.yaml"
        cfg = ConfigManager(config_path=config_path)
        assert isinstance(cfg.config, Config)

    def test_get_default_for_missing_key(self, tmp_path: Path) -> None:
        """get() returns default for non-existent attributes."""
        config_path = tmp_path / "config.yaml"
        cfg = ConfigManager(config_path=config_path)
        assert cfg.get("nonexistent_field", "fallback") == "fallback"


# ---------------------------------------------------------------------------
# Tests: Config validation edge cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConfigValidation:
    """Verify Config field validators."""

    def test_invalid_output_format_raises(self) -> None:
        """Invalid default_output raises ValueError."""
        with pytest.raises(Exception, match="default_output"):
            Config(default_output="xml")

    def test_valid_output_formats_accepted(self) -> None:
        """All supported output formats are accepted."""
        for fmt in ("table", "json", "yaml", "csv"):
            cfg = Config(default_output=fmt)
            assert cfg.default_output == fmt

    def test_max_cost_alert_zero_is_valid(self) -> None:
        """max_cost_alert=0 is valid (no cost alerts)."""
        cfg = Config(max_cost_alert=0)
        assert cfg.max_cost_alert == 0

    def test_max_cost_alert_negative_raises(self) -> None:
        """Negative max_cost_alert raises ValueError."""
        with pytest.raises(Exception, match="max_cost_alert"):
            Config(max_cost_alert=-1)


# ---------------------------------------------------------------------------
# Tests: ConfigManager with malformed YAML
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConfigManagerMalformedYaml:
    """Verify ConfigManager handles malformed config files."""

    def test_non_dict_yaml_raises(self, tmp_path: Path) -> None:
        """YAML file that isn't a mapping raises ConfigError."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("- item1\n- item2\n")
        with pytest.raises(ConfigError, match="must contain a YAML mapping"):
            ConfigManager(config_path=config_path)
