from __future__ import annotations

import importlib.util
import os
from argparse import Namespace
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "publish_pypi.py"
SPEC = importlib.util.spec_from_file_location("publish_pypi", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
publish_pypi = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publish_pypi)


def test_load_env_file_accepts_utf16_dotenv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("PYPI_TOKEN=fake-token\n", encoding="utf-16")
    monkeypatch.delenv("PYPI_TOKEN", raising=False)

    publish_pypi.load_env_file(str(env_file))

    assert os.environ["PYPI_TOKEN"] == "fake-token"


def test_twine_environment_uses_testpypi_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYPI_TOKEN", raising=False)
    monkeypatch.delenv("TWINE_PASSWORD", raising=False)
    monkeypatch.setenv("TEST_PYPI_TOKEN", "test-token")
    args = Namespace(repository="testpypi", token_env=None)

    env = publish_pypi.twine_environment(args)

    assert env["TWINE_USERNAME"] == "__token__"
    assert env["TWINE_PASSWORD"] == "test-token"


def test_twine_environment_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYPI_TOKEN", raising=False)
    monkeypatch.delenv("TEST_PYPI_TOKEN", raising=False)
    monkeypatch.delenv("TWINE_PASSWORD", raising=False)
    args = Namespace(repository="pypi", token_env=None)

    with pytest.raises(SystemExit, match="Missing PyPI token"):
        publish_pypi.twine_environment(args)
