# CI/CD Audit and Operations

## Findings (2026-10-09)

The existing workflow already triggered on `push` to `main`. GitHub run
37970595425 completed checkout, Quay login, and build/push successfully.
There is no evidence that the latest main publication was skipped. All seven
KubeOptix repositories had successful latest main push runs during this audit.
The confirmed gaps were missing test/security gates, mutable Action tags,
publication independent of GitFlow validation, and cancellable main runs.
Branch protection required only `check-flow`, no approvals, and no up-to-date
branch. Repository secrets were empty; organization secret visibility could
not be audited with the available GitHub token (403).

## Required Pipeline

PRs targeting `develop`, `stage`, or `main`, pushes to those branches, and
merge queues run GitFlow validation, Python tests, workflow syntax validation,
dependency/secret scans, image build, non-root inspection, and image scans.
`ci-required` fails if any dependency fails, is cancelled, or is skipped.
Trivy v0.69.3 blocks HIGH/CRITICAL findings, including unfixed vulnerabilities.
Image configuration and embedded secrets are checked before login. Actions
are pinned by SHA; actionlint v1.7.7 is checksum-verified. The GitHub token has
only `contents: read`; checkout does not persist credentials.

Only `push` to `main` or a valid `vMAJOR.MINOR.PATCH` tag can log in and publish.
The already-scanned local image is pushed without rebuilding. Main publishes
`latest` and `sha-<commit>`; releases retain version and SHA tags and must point
to main history. PRs, stage, develop, and merge queues never receive Quay secrets.
Main runs are not actively cancelled by later runs; GitHub concurrency can
coalesce pending runs when several commits arrive rapidly.

## GitHub Configuration and Activation

Protections were applied and re-read for `main`, `stage`, and `develop` in all
seven repositories: require `check-flow` and `ci-required` from GitHub Actions,
require an up-to-date branch, at least one approval, dismiss stale approvals,
require approval of the last push, enforce for admins, and disallow force pushes
and deletion. Existing checks were preserved. GitHub still allows a reviewer
to submit APPROVE on a failing PR; these protections prevent its integration.

Publish these workflow changes on the existing feature branch, open a PR to
`develop`, and require a green `ci-required` plus an independent review. Then
promote `develop -> stage -> main`. Until the changed workflows produce the
new check, existing PRs are intentionally blocked. Never bypass the gate.
Protect release tag creation in a tag ruleset for `v*`, restricting creation
to release maintainers and disallowing updates/deletion. Check repository or
organization Actions policies allow the pinned actions. Pushes performed by
another workflow's `GITHUB_TOKEN` do not trigger a new push workflow; use an
approved GitHub App if release automation needs to create tags.

## Quay Configuration

Keep destination `quay.io/parraes/kubeoptix-reporter`. Create a dedicated Quay
robot with Write access only to this repository, not organization Admin.
Configure Actions secrets `QUAY_USERNAME` (full `namespace+robot` name) and
`QUAY_PASSWORD` (robot token), at repository or restricted organization scope.
Organization secrets must explicitly include this GitHub repository. Rotate
tokens and enter them directly in the GitHub UI or secure CLI prompt, never
in source, command arguments, logs, or test fixtures. Do not enable shell tracing.
Enable Quay vulnerability notifications as a complementary post-push control.

## Validation and Remaining Acceptance

The 14 workflows passed actionlint; aggregate failure/skipped/cancelled handling
and 63 GitFlow scenarios passed. Reporter: 39 local tests passed on Python 3.14;
CI uses Python 3.12, whose clean-run installation still needs GitHub execution.
Source scans passed with no HIGH/CRITICAL findings or secrets; the misspelled
`requeriments.txt` is not fully covered by manifest autodetection, so scanning
installed packages in the final image is mandatory. The reporter image was not
rebuilt/scanned locally. No changed workflows were committed, pushed, or executed
remotely, and no new image was published during the audit. Final acceptance
requires a deliberately failing PR to remain blocked, a reviewed green promotion
to main, and a successful main run whose Quay digest matches the scanned image.

## PR Failure Remediation (2026-10-09)

PR #32 reached the image gate and correctly blocked vulnerable Pillow, Starlette,
WeasyPrint, CairoSVG, and css_parser. Runtime dependencies are now fixed to
patched versions. The stable Asciidoctor PDF 2.3.27 source is pinned to commit
39a97554fbd2c27cdd919bde3091dc048b174ce6. Its gem specification has an explicit
compatibility patch for prawn-svg 0.40.4, allowing css_parser 3.3.0 instead of
installing the vulnerable 1.x dependency. This is a maintained local packaging
patch, not an upstream release change; revisit it when upstream adopts the fix.

The corrected UBI image passed strict vulnerability/configuration/secret scans,
all 39 tests on its Python 3.12 runtime, dependency resolution/import checks,
and actual PDF generation containing SVG. No mandatory scan was disabled and
no application assertions were skipped. The updated PR still needs its new
GitHub run and independent review before promotion.