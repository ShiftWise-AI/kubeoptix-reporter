# Contributing

This repository is one component of the KubeOptix platform.

## Branches

- Use `develop` for integration and `main` for production releases.
- Start `feature/*` or `fix/*` branches from `develop` and open a PR to `develop`.
- Promote `develop` to `main` through a PR. A `fix/*` branch can also target `main`.
- PRs must originate in this repository; forks and other branch flows are rejected by the separate branch-governance workflow.
- Describe the change, impact, and validation when proposing a merge from `develop` to `main`.

## Validation and releases

The release workflow follows the Core AI pipeline: `validate` -> `ci-required` -> `release`.

- PRs to `develop` or `main` run workflow lint, Python tests, source/secret scans, a validation image build, a non-root check, and an image scan. PRs never publish images.
- Pushes to `main` run the same validation, then release only after `ci-required` succeeds. The source must be a merged, allowed same-repository PR to `main`.
- Releases are serialized without cancellation using `queue: max`. Configure the `quay-release` environment with `QUAY_USERNAME`, `QUAY_PASSWORD`, and `OPERATOR_TOKEN` secrets, plus any required approval rules.
- Each new source reserves an annotated `vX.Y.Z` tag pointing directly to that source commit, incrementing the highest released patch version (starting at `1.0.0` if no SemVer tags exist). Unlike Core AI, Reporter has no package version file to update.
- The exact tagged source is tested, built, checked for non-root execution, scanned, and published to `quay.io/parraes/kubeoptix-reporter:X.Y.Z` and `sha-<source>`. An existing versioned image is reused only when its version and source labels match.
- `latest` is updated only if the source is still the tip of `main` and the version is the highest reserved release. Only then does CI validate and open or resume an Operator PR changing `ReporterImage` to the versioned image pinned by digest.
- To resume a failed release, run the workflow manually on `main` with the original full merge SHA in `source`. Leaving it empty uses current `main`. The same source reuses its reserved version.

Run the local checks documented in the README before opening a PR. Deployment to OpenShift remains separate from GitHub Actions.

## Commands

```bash
git fetch origin
git switch develop
git pull --ff-only origin develop
```