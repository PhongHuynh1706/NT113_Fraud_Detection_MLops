
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = (PROJECT_ROOT / "configs").resolve()


def validate_config_path(config_path: str | Path) -> Path:
    """Validate a YAML configuration path."""

    path = Path(config_path).resolve()

    if not path.is_relative_to(CONFIG_DIR):
        raise ValueError(
            f"Configuration path must be inside {CONFIG_DIR}"
        )

    if path.suffix.lower() not in {".yaml", ".yml"}:
        raise ValueError("Configuration must be a YAML file")

    if not path.is_file():
        raise FileNotFoundError(path)

    return path


def load_config(config_path: str | Path) -> dict[str, Any]:
    """Load a validated YAML configuration."""

    safe_path = validate_config_path(config_path)

    with safe_path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    if not isinstance(config, dict):
        raise ValueError("YAML configuration must be a mapping")

    return config
