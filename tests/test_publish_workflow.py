"""Regression tests for the image publishing workflow."""

import re
from pathlib import Path


def test_buildx_uses_builtin_driver_without_pulling_buildkit():
    workflow = (
        Path(__file__).resolve().parents[1] / ".github/workflows/publish-quay.yml"
    ).read_text()
    steps = re.split(r"^      - ", workflow, flags=re.MULTILINE)
    buildx_steps = [step for step in steps if "uses: docker/setup-buildx-action@" in step]

    assert len(buildx_steps) == 1
    assert re.search(r"^        with:\n          driver: docker$", buildx_steps[0], re.MULTILINE)
