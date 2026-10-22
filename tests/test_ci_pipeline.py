import pytest

from scripts.ci_pipeline import allowed_pr, next_version, operator_image, version_tuple


def test_next_version_increments_highest_semver_tag():
    assert next_version(["1.0.5", "1.0.3"]) == "1.0.6"


def test_next_version_starts_at_one_zero_zero():
    assert next_version([]) == "1.0.0"


def test_allowed_pr_requires_local_repository_and_valid_branch_flow():
    pr = {
        "base": {"ref": "main", "repo": {"full_name": "ShiftWise-AI/kubeoptix-reporter"}},
        "head": {"ref": "fix/patch", "repo": {"full_name": "ShiftWise-AI/kubeoptix-reporter"}},
    }
    assert allowed_pr(pr)
    pr["head"]["repo"]["full_name"] = "contributor/kubeoptix-reporter"
    assert not allowed_pr(pr)


def test_operator_image_replaces_only_reporter_default():
    source = 'ReporterImage: registryImage(constants.ReporterName),\nCoreAIImage: registryImage(constants.CoreAIName),'
    updated = operator_image(source, "quay.io/parraes/kubeoptix-reporter:1.0.6@sha256:" + "a" * 64)
    assert 'ReporterImage: "quay.io/parraes/kubeoptix-reporter:1.0.6@sha256:' in updated
    assert "CoreAIImage: registryImage(constants.CoreAIName)," in updated


def test_semver_rejects_leading_zeroes():
    with pytest.raises(ValueError):
        version_tuple("01.0.0")