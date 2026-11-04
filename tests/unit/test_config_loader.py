
from pathlib import Path

import pytest
import yaml

from fraud_detection.utils import config_loader


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    """Create an isolated configuration directory."""
    directory = tmp_path / "configs"
    directory.mkdir()

    monkeypatch.setattr(config_loader, "CONFIG_DIR", directory.resolve())

    return directory


def test_load_valid_yaml(config_dir):
    config_path = config_dir / "training.yaml"
    config_path.write_text(
        "model:\n  name: catboost\n  threshold: 0.8\n",
        encoding="utf-8",
    )

    result = config_loader.load_config(config_path)

    assert result == {
        "model": {
            "name": "catboost",
            "threshold": 0.8,
        }
    }


def test_load_valid_yml(config_dir):
    config_path = config_dir / "training.yml"
    config_path.write_text(
        "model: catboost\n",
        encoding="utf-8",
    )

    result = config_loader.load_config(config_path)

    assert result == {"model": "catboost"}


def test_reject_path_traversal(config_dir):
    outside_file = config_dir.parent / "secret.yaml"
    outside_file.write_text(
        "password: secret\n",
        encoding="utf-8",
    )

    malicious_path = config_dir / ".." / "secret.yaml"

    with pytest.raises(
        ValueError,
        match="Configuration path must be inside",
    ):
        config_loader.load_config(malicious_path)


def test_reject_absolute_path_outside_config_dir(config_dir):
    outside_file = config_dir.parent / "outside.yaml"
    outside_file.write_text(
        "value: test\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        config_loader.validate_config_path(outside_file)


def test_reject_invalid_extension(config_dir):
    config_path = config_dir / "training.txt"
    config_path.write_text(
        "model: catboost\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="Configuration must be a YAML file",
    ):
        config_loader.load_config(config_path)


def test_reject_missing_file(config_dir):
    config_path = config_dir / "missing.yaml"

    with pytest.raises(FileNotFoundError):
        config_loader.load_config(config_path)


@pytest.mark.parametrize(
    "content",
    [
        "- item1\n- item2\n",
        "hello\n",
        "123\n",
        "",
    ],
)
def test_reject_non_mapping_yaml(config_dir, content):
    config_path = config_dir / "invalid.yaml"
    config_path.write_text(content, encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="YAML configuration must be a mapping",
    ):
        config_loader.load_config(config_path)


def test_reject_malformed_yaml(config_dir):
    config_path = config_dir / "malformed.yaml"
    config_path.write_text(
        "model: [catboost\n",
        encoding="utf-8",
    )

    with pytest.raises(yaml.YAMLError):
        config_loader.load_config(config_path)


def test_validate_config_path_returns_resolved_path(config_dir):
    config_path = config_dir / "training.yaml"
    config_path.write_text(
        "model: catboost\n",
        encoding="utf-8",
    )

    result = config_loader.validate_config_path(config_path)

    assert isinstance(result, Path)
    assert result == config_path.resolve()
