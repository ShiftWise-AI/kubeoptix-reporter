"""Regression tests for image-converter dependency discovery."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wrapper.md2images import MDToImagesConverter


@pytest.mark.parametrize(
    ("command", "expected"),
    [("convert", True), ("missing-command", False), ("convert; echo injected", False)],
)
def test_command_discovery_does_not_use_a_shell(tmp_path, monkeypatch, command, expected):
    executable = tmp_path / "convert"
    executable.touch(mode=0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr(
        "wrapper.md2images.subprocess.run",
        lambda *args, **kwargs: pytest.fail("Dependency discovery must not spawn a process"),
    )
    converter = MDToImagesConverter.__new__(MDToImagesConverter)
    assert converter._command_exists(command) is expected


def test_converter_initializes_with_available_dependency(tmp_path, monkeypatch):
    executable = tmp_path / "convert"
    executable.touch(mode=0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    converter = MDToImagesConverter(str(tmp_path), str(tmp_path / "output"))
    assert converter.output_dir.is_dir()
    assert converter.count_errors == 0


def test_converter_keeps_missing_dependency_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(SystemExit) as error:
        MDToImagesConverter(str(tmp_path), str(tmp_path / "output"))
    assert error.value.code == 1