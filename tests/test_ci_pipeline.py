from pathlib import Path

import pytest
import yaml

from scripts import ci_pipeline
from scripts.ci_pipeline import allowed_pr, next_version, operator_image, version_tuple


def test_workflow_dependency_and_queue_contract():
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / ".github/workflows/ci-release.yml").read_text())
    events = workflow.get("on", workflow.get(True))
    assert events["pull_request"]["branches"] == ["main", "develop"]
    assert events["push"]["branches"] == ["main"]
    assert events["workflow_dispatch"]["inputs"]["source"]["required"] is False
    assert workflow["permissions"] == {"contents": "read"}
    jobs = workflow["jobs"]
    assert set(jobs) == {"validate", "ci-required", "release"}
    assert jobs["ci-required"]["needs"] == ["validate"]
    assert jobs["ci-required"]["if"] == "always()"
    gate = jobs["ci-required"]["steps"][0]
    assert gate["env"]["RESULT"] == "${{ needs.validate.result }}"
    assert gate["run"] == 'test "$RESULT" = success'
    assert jobs["release"]["needs"] == ["ci-required"]
    assert jobs["release"]["if"] == "github.event_name != 'pull_request' && github.ref == 'refs/heads/main'"
    assert jobs["release"]["environment"] == "quay-release"
    assert jobs["release"]["concurrency"] == {
        "group": "reporter-production-release", "cancel-in-progress": False, "queue": "max",
    }
    governance = yaml.safe_load((root / ".github/workflows/branch-limits.yml").read_text())
    assert "pull_request" in governance.get("on", governance.get(True))


def test_release_configures_identity_before_reserving_version():
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / ".github/workflows/ci-release.yml").read_text())
    release = workflow["jobs"]["release"]
    assert release["env"]["IMAGE"] == ci_pipeline.IMAGE
    steps = release["steps"]
    names = [step.get("name") for step in steps]
    identity = names.index("Configure release identity")
    reservation = names.index("Reserve or resume version")
    assert names.index("Check credentials before reserving a release") < identity < reservation
    assert "git config --global user.name" in steps[identity]["run"]
    assert "git config --global user.email" in steps[identity]["run"]
    assert steps[reservation]["env"]["SOURCE"] == "${{ inputs.source || github.sha }}"
    assert steps[-1]["run"] == 'python scripts/ci_pipeline.py operator --version "$VERSION" --digest "$DIGEST"'
    for step in steps[-3:]:
        assert step["if"] == "steps.published.outputs.current == 'true'"


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


def test_release_reservation_survives_a_fresh_checkout(tmp_path, monkeypatch):
    remote = tmp_path / "remote.git"
    first = tmp_path / "first"
    second = tmp_path / "second"
    monkeypatch.setenv("GIT_AUTHOR_NAME", "CI Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "ci@example.invalid")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "CI Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "ci@example.invalid")
    ci_pipeline.run("git", "init", "--bare", str(remote))
    ci_pipeline.run("git", "init", "-b", "main", str(first))
    monkeypatch.chdir(first)
    ci_pipeline.run("git", "remote", "add", "origin", str(remote))
    ci_pipeline.run("git", "commit", "--allow-empty", "-m", "Initial source")
    ci_pipeline.run("git", "tag", "v1.0.5")
    ci_pipeline.run("git", "commit", "--allow-empty", "-m", "Merge allowed PR")
    source = ci_pipeline.run("git", "rev-parse", "HEAD")
    ci_pipeline.run("git", "push", "origin", "main", "--tags")
    pr = {
        "merged_at": "2026-10-22T00:00:00Z",
        "merge_commit_sha": source,
        "base": {"ref": "main", "repo": {"full_name": ci_pipeline.REPOSITORY}},
        "head": {"ref": "develop", "repo": {"full_name": ci_pipeline.REPOSITORY}},
    }
    monkeypatch.setattr(ci_pipeline, "api", lambda *args: [pr])
    outputs = []
    monkeypatch.setattr(ci_pipeline, "output", lambda **values: outputs.append(values))

    ci_pipeline.reserve(source)
    ci_pipeline.run("git", "clone", "--branch", "main", str(remote), str(second))
    monkeypatch.chdir(second)
    ci_pipeline.reserve(source)

    assert outputs[0] == outputs[1]
    assert outputs[0] == {
        "version": "1.0.6", "tag": "v1.0.6", "source": source, "commit": source,
    }
    assert ci_pipeline.run("git", "tag", "--list") == "v1.0.5\nv1.0.6"