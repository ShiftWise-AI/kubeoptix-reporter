# KubeOptix Reporter

KubeOptix Reporter is a FastAPI service that stores Markdown reports and generates Red Hat Consulting-style PDF documents. It is designed to run as a non-root container on OpenShift and can be deployed with the Helm chart in this repository.

## Overview

The project combines:

- a FastAPI API for saving and retrieving Markdown reports
- a PDF endpoint that resolves document versions and metadata from a configurations API
- a PDF rendering pipeline with Red Hat report formatting, images, captions, and optional logo support
- command-line utilities to convert Markdown into PDF, DOCX, Excel tables, and PNG images
- an OpenShift-oriented Helm chart with a BuildConfig, ImageStream, StatefulSet, Service, probes, and persistent storage

## Repository structure

- `src/api.py`: API layer that stores Markdown files and renders PDFs
- `wrapper/`: conversion and formatting utilities
  - `md2pdf.py`: convert Markdown to PDF
  - `md2docx.py`: convert Markdown to DOCX
  - `md2excel.py`: convert Markdown tables to Excel worksheets
  - `md2images.py`: extract images from Markdown and convert them to PNG
  - `apply_pdf_template.py`: applies the report template and generates the final PDF
  - `i18n/`: locale catalogs and rendering helpers used to localize the generated report (`pt-BR`, `en-US`, `es-ES`, `it-IT`)
- `template/`: template assets, styles, fonts, and Markdown documents used for report generation
- `helm/kubeoptix-reporter/`: Helm chart for deployment
- `install.sh`: validates access to OpenShift, installs or upgrades the Helm release, starts the build, and waits for the rollout
- `requeriments.txt`: pinned Python runtime dependencies

## Requirements

- Python 3.11+
- `pip` and a virtual environment
- local PDF generation also requires the tools used by the selected wrapper:
   - `pandoc` (the API can use the bundled copy supplied by `pypandoc_binary`)
   - `weasyprint` for `wrapper/md2pdf.py`
   - Ruby and the `asciidoctor-pdf` and `rouge` gems for the Red Hat template renderer
   - `cairosvg`, Pillow, and the other Python packages in `requeriments.txt` for template image processing

The provided `Containerfile` installs Python, Ruby, the required native libraries, Python dependencies, and the `asciidoctor-pdf` and `rouge` gems. The local host still needs any commands required by the wrapper being run.

## Local setup

1. Create and activate a virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install Python dependencies:

   ```bash
   pip install -r requeriments.txt
   ```

3. Start the API locally:

   ```bash
   uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload
   ```

4. Validate the service:

   ```bash
   curl http://localhost:8000/health
   ```

The API listens on port `8000` by default. For local execution, create the configured report directory before saving a report if it does not already exist:

```bash
mkdir -p /app/data/reports
```

## API endpoints

### Health check

```bash
GET /health
```

Returns:

```json
{ "status": "ok" }
```

### Save a Markdown report

```bash
PUT /report/{filename}
POST /report/{filename}
```

The request body is the Markdown content. The filename must end in `.md`.

```bash
curl --data-binary @report.md \
   -X PUT http://localhost:8000/report/report.md
```

The endpoint accepts only a plain filename ending in `.md`; path traversal and subdirectories are rejected. The file is written atomically and returns:

```json
{ "filename": "report.md", "status": "saved" }
```

### Download a Markdown report

```bash
GET /report/{filename}
```

The response has media type `text/markdown` and returns `404` when the file does not exist.

### Generate a PDF report

```bash
GET /report/{filename}/pdf?versionNumber=1.0
```

This endpoint does not render the Markdown file stored by the upload endpoint. It uses the filename stem as `documentName`, then queries the configured configurations API:

1. `GET /system-settings` to resolve the report locale from the `language` field (BCP 47). Supported locales are `pt-BR`, `en-US`, `es-ES`, and `it-IT`; any other value, an empty/missing `language`, or an unreachable `/system-settings` fails the request instead of silently falling back to another locale.
2. `GET /versions` to find the requested `versionNumber` and its `markdownContent`.
3. `GET /documents/{documentName}` to resolve the title, customer, and project manager.
4. `GET /documents` to find related document records.
5. `GET /authors/{authorId}` and `GET /costumers-list/{customerListId}` for report participants.
6. `GET /system-settings/logo` for an optional PNG, JPEG, WebP, or SVG logo.

The Markdown content returned by `/versions` is rendered with the template under `PDF_TEMPLATE_DIR`. All fixed report text (preface, participants and version-history sections, table of contents/figure/table captions, and the cover date) is generated from the locale resolved above via [`wrapper/i18n`](wrapper/i18n). A missing document version returns `404`; an unsupported/missing locale returns `400`; an unreachable `/system-settings` or rendering failures return `503`.

```bash
curl -f -o report.pdf \
   "http://localhost:8000/report/report.md/pdf?versionNumber=1.0"
```

The configurations API must be reachable from the reporter container. Its default base URL is `http://configurations-api:8000`.

### Report localization (i18n)

The generated report is fully localized based on the `language` field returned by the configurations API's `/system-settings` endpoint, treated as a BCP 47 locale. Only four locales are supported, with no fallback for any other value:

- `pt-BR`
- `en-US`
- `es-ES`
- `it-IT`

Translations are centralized in [`wrapper/i18n/`](wrapper/i18n), with one message-catalog module per locale (`pt_br.py`, `en_us.py`, `es_es.py`, `it_it.py`) and shared rendering/validation helpers in `wrapper/i18n/__init__.py`. This is the single place to add or adjust translated report text; the Markdown/AsciiDoc generation code in `wrapper/apply_pdf_template.py` never hardcodes locale-specific strings.

## Environment variables

The service uses the following variables:

- `DATA_DIR`: directory where Markdown reports are stored
- `PDF_TEMPLATE_DIR`: folder containing the PDF template assets
- `CONFIGURATIONS_API_URL`: base URL for the configuration API
- `LOG_LEVEL`: application log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, etc.)
- `PDF_CUSTOMER`: default customer name on the report
- `PDF_DESCRIPTION`: default description shown in the report metadata
- `PDF_VERSION`: default version value
- `PDF_STATUS`: default document status
- `PDF_AUTHOR`: default author value
- `PDF_PROJECT_MANAGER`: default project manager value
- `PDF_CONFIDENTIALITY`: default confidentiality value

The PDF metadata defaults are used when the configurations API does not provide a corresponding value. `PDF_CONFIDENTIALITY` is currently always passed to the renderer as the confidentiality value.

## Wrapper tools

### Convert Markdown to PDF

```bash
python wrapper/md2pdf.py input.md output.pdf
python wrapper/md2pdf.py ./docs ./pdf-output
```

This standalone wrapper uses Pandoc with WeasyPrint and is separate from the API's Red Hat template flow.

### Convert Markdown to DOCX

```bash
python wrapper/md2docx.py report.md
```

### Extract Markdown images and convert them to PNG

```bash
python wrapper/md2images.py ./docs ./files --verbose
```

### Convert Markdown tables to Excel files

```bash
python wrapper/md2excel.py --md-file report.md --files-dir ./files --inventory-events ./events.tsv
```

## PDF generation details

The PDF renderer reads Markdown input, removes front matter if present, materializes embedded images, applies the Red Hat report template, and generates an A4 PDF using `pandoc` and `asciidoctor-pdf`. All fixed report text is localized through [`wrapper/i18n`](wrapper/i18n) based on the locale resolved from `/system-settings` (see [Report localization (i18n)](#report-localization-i18n)).

## Running tests

Install the test dependencies and run `pytest`:

```bash
pip install -r requeriments.txt -r requirements-dev.txt
pytest
```

The suite covers the `wrapper/i18n` catalogs for all four supported locales and the `/system-settings` locale-resolution logic in `src/api.py`, including unsupported/missing/empty `language` values and an unavailable configurations API.

## Helm deployment

The Helm chart is located in:

- `helm/kubeoptix-reporter/`

It is intended primarily for OpenShift and includes:

- a `BuildConfig` that builds `Containerfile` from the configured Git repository;
- an `ImageStream` and a `StatefulSet` running one replica by default;
- a `ClusterIP` service on port `8000`;
- startup, readiness, and liveness probes using `/health`;
- an optional existing PVC mounted at `/app/data`, with reports stored at `/app/data/reports`;
- a single-replica policy enabled by default.

The example values expect an existing Git authentication Secret named `github-auth` and an existing PVC named `harvester-app-data`. Change these values for another cluster or disable the build/persistence features when appropriate.

### Install with `install.sh`

The script requires `oc`, `helm`, an authenticated OpenShift session, the Git Secret, and the values file:

```bash
oc login <cluster-url>
./install.sh --values helm/kubeoptix-reporter/values.example.yaml
```

The script creates the `shiftwise-ai` namespace when needed, runs `helm lint`, installs or upgrades the release, starts or follows the OpenShift build, waits for the rollout, and prints the service name. Override defaults with `NAMESPACE`, `RELEASE_NAME`, `TIMEOUT`, and the cleanup flags documented in the script's `--help` output.

For a plain Helm installation without the build helper:

```bash
helm lint helm/kubeoptix-reporter -f values.yaml
helm upgrade --install kubeoptix-reporter helm/kubeoptix-reporter \
   --namespace shiftwise-ai --create-namespace -f values.yaml
```

## Notes

- The project is designed for OpenShift-style environments and expects a configurations API to provide document metadata, version history, participant data, and optionally a logo.
- The conversion wrappers may require package installation on the host environment before use.
- The container runs as UID `1001` after the image build and keeps `/app` group-writable for OpenShift-compatible arbitrary UID behavior.
- The project uses English as the code-comment language, while generated document content and metadata can be customized by environment variables and API responses.
