# GitHub Copilot Instructions

## Context
- **Language/Framework:** Python 3.11+ / FastAPI
- **Base Image:** Red Hat UBI 10 (Universal Base Image)
- **Platform:** Red Hat OpenShift (Kubernetes)
- **Deployment:** Helm Charts
- **Token Efficiency:** Extreme. Code-only or diff-only outputs.

## Code Generation Rules
- **No Boilerplate:** Generate only requested endpoints or logic. No full boilerplate apps.
- **No Text Explanations:** Output pure code/manifests. Avoid preamble or summary text.
- **Diffs Only:** For modifications, provide only the changed code snippet.
- **Asynchronous Python:** Always use `async def` for FastAPI endpoints and operations.

## OpenShift & UBI 10 Standards
- **Container Image:** Strictly use `://redhat.com...` as the base image.
- **Non-Root Execution:** App must run with arbitrary UIDs (OpenShift standard). Never hardcode user `0` or rely on root-level directory permissions.
- **FastAPI Server:** Run using `uvicorn` or `gunicorn` binding to port `8000` (standard non-privileged port).
- **Probes:** Map Kubernetes liveness/readiness probes directly to FastAPI endpoints (e.g., `/health`).
