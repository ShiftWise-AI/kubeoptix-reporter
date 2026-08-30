# KubeOptix Reporter

KubeOptix Reporter is a FastAPI-based document reporting service for generating PDF documents from Markdown content and serving them in OpenShift or Kubernetes environments.

## Overview

The project combines:

- a FastAPI API for uploading and retrieving Markdown reports
- a PDF rendering pipeline with Red Hat-themed report formatting
- utilities to convert Markdown into PDF, DOCX, Excel tables, and PNG images
- a Helm chart for deployment in OpenShift

## Repository structure

- `src/api.py`: API layer that stores Markdown files and renders PDFs
- `wrapper/`: conversion and formatting utilities
  - `md2pdf.py`: convert Markdown to PDF
  - `md2docx.py`: convert Markdown to DOCX
  - `md2excel.py`: convert Markdown tables to Excel worksheets
  - `md2images.py`: extract images from Markdown and convert them to PNG
  - `apply_pdf_template.py`: applies the report template and generates the final PDF
- `template/`: template assets, styles, fonts, and Markdown documents used for report generation
- `helm/kubeoptix-reporter/`: Helm chart for deployment

## Requirements

- Python 3.11+
- `pip` and a virtual environment
- system tools used by the wrappers, depending on the conversion flow:
  - `ImageMagick` (`convert` command)
  - `pandoc`
  - `weasyprint`
  - `asciidoctor-pdf` and Ruby gems for PDF generation

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

### Download a Markdown report

```bash
GET /report/{filename}
```

### Generate a PDF report

```bash
GET /report/{filename}/pdf?versionNumber=1.0
```

This endpoint fetches the matching document metadata and version content from the configured configuration service and renders the final PDF.

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

## Wrapper tools

### Convert Markdown to PDF

```bash
python wrapper/md2pdf.py input.md output.pdf
python wrapper/md2pdf.py ./docs ./pdf-output
```

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

The PDF renderer reads Markdown input, removes front matter if present, materializes embedded images, applies the Red Hat report template, and generates an A4 PDF using `pandoc` and `asciidoctor-pdf`.

## Helm deployment

The Helm chart is located in:

- `helm/kubeoptix-reporter/`

It is intended for OpenShift/Kubernetes deployment and includes the application manifest and supporting resources.

## Notes

- The project is designed for OpenShift-style environments and expects a configuration service to provide document metadata and version history.
- The conversion wrappers may require package installation on the host environment before use.
- The project uses English as the code-comment language, while the generated document metadata can be customized by environment variables and API responses.
