import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import anyio
import httpx
from fastapi import FastAPI, HTTPException, Path as PathParameter, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from starlette.background import BackgroundTask

from wrapper.apply_pdf_template import TemplateError, render_pdf

REPORTS_DIR = Path(os.getenv("DATA_DIR", "/app/data/reports"))
TEMPLATE_DIR = Path(os.getenv("PDF_TEMPLATE_DIR", "/app/template"))
CONFIGURATIONS_API_URL = os.getenv("CONFIGURATIONS_API_URL", "http://configurations-api:8000")
PDF_CUSTOMER = os.getenv("PDF_CUSTOMER", "Cliente")
PDF_DESCRIPTION = os.getenv("PDF_DESCRIPTION", "OpenShift Application Assessment")
PDF_VERSION = os.getenv("PDF_VERSION", "1.0")
PDF_STATUS = os.getenv("PDF_STATUS", "final")
PDF_AUTHOR = os.getenv("PDF_AUTHOR", "Autor")
PDF_PROJECT_MANAGER = os.getenv("PDF_PROJECT_MANAGER", "Gerente do projeto")
PDF_CONFIDENTIALITY = os.getenv("PDF_CONFIDENTIALITY", "Confidencial")
MONTH_NAMES_PT_BR = (
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
    "OFF": logging.CRITICAL + 1,
}

if LOG_LEVEL not in LOG_LEVELS:
    LOG_LEVEL = "INFO"

logger = logging.getLogger("uvicorn.error.kubeoptix")
logger.setLevel(LOG_LEVELS[LOG_LEVEL])

app = FastAPI(
    title="Assessment API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "PUT"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok"}


def current_document_date() -> str:
    current_date = datetime.now().astimezone()
    return f"{MONTH_NAMES_PT_BR[current_date.month - 1]} de {current_date.year}"


async def fetch_pdf_metadata(
    document_name: str, version_number: str
) -> tuple[dict[str, str], str | None, list[dict[str, str]], list[dict[str, str]]]:
    """De-para: customer/description/projectManager/author vêm de /documents e
    /authors; version e status usam o versionNumber informado por parâmetro.
    confidentiality permanece com o valor default. O conteúdo Markdown, antes
    lido do arquivo .md salvo, agora vem de VersionResponse.markdownContent
    para o versionNumber informado.
    """
    metadata = {
        "customer": PDF_CUSTOMER,
        "description": PDF_DESCRIPTION,
        "version": version_number,
        "status": version_number,
        "author": PDF_AUTHOR,
        "project_manager": PDF_PROJECT_MANAGER,
    }
    markdown_content: str | None = None
    authors: list[dict[str, str]] = []
    customers: list[dict[str, str]] = []

    try:
        async with httpx.AsyncClient(base_url=CONFIGURATIONS_API_URL, timeout=5.0) as client:
            versions_response = await client.get("/versions")
            resolved_document_name: str | None = None
            if versions_response.status_code == 200:
                for version in versions_response.json():
                    version_document_name = version.get("documentName")
                    if (
                        isinstance(version_document_name, str)
                        and (
                            version_document_name == document_name
                            or version_document_name.startswith(f"{document_name}::")
                        )
                        and str(version.get("versionNumber")) == version_number
                    ):
                        resolved_document_name = version_document_name
                        markdown_content = version.get("markdownContent")
                        metadata["version_created_at"] = (
                            version.get("createdAt")
                            or version.get("created_at")
                            or version.get("screated_at")
                            or ""
                        )
                        break

            if resolved_document_name is None:
                return metadata, None, authors, customers

            document_response = await client.get(f"/documents/{resolved_document_name}")
            if document_response.status_code == 200:
                document = document_response.json()
                metadata["customer"] = document.get("costumer") or metadata["customer"]
                metadata["description"] = document.get("title") or metadata["description"]
                metadata["project_manager"] = (
                    document.get("projectManager") or metadata["project_manager"]
                )

                author_id = document.get("authorId")
                if author_id:
                    author_response = await client.get(f"/authors/{author_id}")
                    if author_response.status_code == 200:
                        author = author_response.json()
                        author_name = author.get("name")
                        metadata["author"] = author_name or metadata["author"]
                        authors.append(author)

                document_id = document.get("id") or resolved_document_name
                authors_response = await client.get("/authors")
                if authors_response.status_code == 200:
                    authors = [
                        author
                        for author in authors_response.json()
                        if author.get("documentId") == document_id
                        or author.get("documentName") == resolved_document_name
                    ] or authors

                customers_response = await client.get("/costumers")
                if customers_response.status_code == 200:
                    customers = [
                        customer
                        for customer in customers_response.json()
                        if customer.get("documentId") == document_id
                        or customer.get("documentName") == resolved_document_name
                    ]
    except httpx.HTTPError:
        logger.exception(
            "Failed to fetch PDF metadata from configurations-api: "
            "document_name=%s version_number=%s",
            document_name,
            version_number,
        )

    return metadata, markdown_content, authors, customers


@app.api_route("/report/{filename}", methods=["PUT", "POST"])
async def save_report(
    request: Request,
    filename: str = PathParameter(..., description="Nome do arquivo Markdown"),
):
    reports_dir = REPORTS_DIR.resolve()

    if Path(filename).name != filename or not filename.lower().endswith(".md"):
        raise HTTPException(
            status_code=400,
            detail="Informe somente o nome de um arquivo com extensão .md",
        )

    report_path = (reports_dir / filename).resolve()
    if not report_path.is_relative_to(reports_dir):
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido")

    temporary_path = reports_dir / f".{filename}.{uuid4().hex}.tmp"

    try:
        async with await anyio.open_file(temporary_path, "wb") as report:
            async for chunk in request.stream():
                await report.write(chunk)
        os.replace(temporary_path, report_path)
    except OSError as exc:
        temporary_path.unlink(missing_ok=True)
        logger.exception("Failed to save report: filename=%s", filename)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao salvar o arquivo: {exc}",
        ) from exc
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise

    logger.info("Report saved: filename=%s report_path=%s", filename, report_path)
    return {"filename": filename, "status": "saved"}


@app.get("/report/{filename}")
async def get_report(
    filename: str = PathParameter(..., description="Nome do arquivo Markdown")
) -> StreamingResponse:
    reports_dir = REPORTS_DIR.resolve()

    logger.info(
        "Report requested: filename=%s reports_dir=%s",
        filename,
        reports_dir,
    )

    if Path(filename).name != filename or not filename.lower().endswith(".md"):
        logger.warning(
            "Invalid report filename: filename=%s reports_dir=%s",
            filename,
            reports_dir,
        )
        raise HTTPException(
            status_code=400,
            detail="Informe somente o nome de um arquivo com extensão .md"
        )

    report_path = (reports_dir / filename).resolve()

    if not report_path.is_relative_to(reports_dir) or not report_path.is_file():
        logger.warning(
            "Report not found: filename=%s report_path=%s reports_dir=%s",
            filename,
            report_path,
            reports_dir,
        )
        raise HTTPException(
            status_code=404,
            detail=f"Arquivo não encontrado: {filename}"
        )

    try:
        report = report_path.open("r", encoding="utf-8")
    except OSError as exc:
        logger.exception(
            "Failed to open report: filename=%s report_path=%s reports_dir=%s",
            filename,
            report_path,
            reports_dir,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao ler o arquivo: {exc}"
        ) from exc

    logger.info(
        "Report opened: filename=%s report_path=%s",
        filename,
        report_path,
    )

    return StreamingResponse(
        report,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}"
        },
        background=BackgroundTask(report.close),
    )


@app.get("/report/{filename}/pdf")
async def get_report_pdf(
    filename: str = PathParameter(..., description="Nome do arquivo Markdown"),
    version_number: str = Query(
        ..., alias="versionNumber", description="Número da versão do documento"
    ),
) -> FileResponse:
    if Path(filename).name != filename or not filename.lower().endswith(".md"):
        raise HTTPException(
            status_code=400,
            detail="Informe somente o nome de um arquivo com extensão .md",
        )

    document_name = Path(filename).stem
    metadata, markdown_content, authors, customers = await fetch_pdf_metadata(
        document_name, version_number
    )
    if markdown_content is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Versão {version_number} não encontrada para o documento "
                f"{document_name}"
            ),
        )

    temporary_md_fd, temporary_md_name = tempfile.mkstemp(
        prefix=f"{document_name}-", suffix=".md"
    )
    with os.fdopen(temporary_md_fd, "w", encoding="utf-8") as temporary_md_file:
        temporary_md_file.write(markdown_content)
    temporary_md = Path(temporary_md_name)

    temporary_fd, temporary_name = tempfile.mkstemp(
        prefix=f"{document_name}-",
        suffix=".pdf",
    )
    os.close(temporary_fd)
    temporary_pdf = Path(temporary_name)
    try:
        await anyio.to_thread.run_sync(
            render_pdf,
            temporary_md,
            temporary_pdf,
            TEMPLATE_DIR,
            metadata["customer"],
            metadata["description"],
            metadata["version"],
            metadata["status"],
            PDF_CONFIDENTIALITY,
            None,
            metadata["author"],
            metadata["project_manager"],
            current_document_date(),
            version_number,
            metadata.get("version_created_at", ""),
            authors,
            customers,
        )
    except TemplateError as exc:
        temporary_pdf.unlink(missing_ok=True)
        logger.exception("Failed to render PDF: filename=%s", filename)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except BaseException:
        temporary_pdf.unlink(missing_ok=True)
        raise
    finally:
        temporary_md.unlink(missing_ok=True)

    pdf_filename = f"{document_name}.pdf"
    return FileResponse(
        temporary_pdf,
        media_type="application/pdf",
        filename=pdf_filename,
        background=BackgroundTask(temporary_pdf.unlink, missing_ok=True),
    )