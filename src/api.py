import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import anyio
from fastapi import FastAPI, HTTPException, Path as PathParameter, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from starlette.background import BackgroundTask

from wrapper.apply_pdf_template import TemplateError, render_pdf

REPORTS_DIR = Path(os.getenv("DATA_DIR", "/app/data/reports"))
TEMPLATE_DIR = Path(os.getenv("PDF_TEMPLATE_DIR", "/app/template"))
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
    customer: str = Query(PDF_CUSTOMER, description="Nome do cliente"),
    description: str = Query(PDF_DESCRIPTION, description="Descrição do documento"),
    version: str = Query(PDF_VERSION, description="Versão do documento"),
    status: str = Query(PDF_STATUS, description="Status do documento"),
    author: str = Query(PDF_AUTHOR, description="Autor do documento"),
    project_manager: str = Query(
        PDF_PROJECT_MANAGER,
        alias="project-manager",
        description="Gerente do projeto",
    ),
) -> FileResponse:
    reports_dir = REPORTS_DIR.resolve()

    if Path(filename).name != filename or not filename.lower().endswith(".md"):
        raise HTTPException(
            status_code=400,
            detail="Informe somente o nome de um arquivo com extensão .md",
        )

    report_path = (reports_dir / filename).resolve()
    if not report_path.is_relative_to(reports_dir) or not report_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Arquivo não encontrado: {filename}",
        )

    temporary_fd, temporary_name = tempfile.mkstemp(
        prefix=f"{report_path.stem}-",
        suffix=".pdf",
    )
    os.close(temporary_fd)
    temporary_pdf = Path(temporary_name)
    try:
        await anyio.to_thread.run_sync(
            render_pdf,
            report_path,
            temporary_pdf,
            TEMPLATE_DIR,
            customer,
            description,
            version,
            status,
            PDF_CONFIDENTIALITY,
            None,
            author,
            project_manager,
            current_document_date(),
        )
    except TemplateError as exc:
        temporary_pdf.unlink(missing_ok=True)
        logger.exception("Failed to render PDF: filename=%s", filename)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except BaseException:
        temporary_pdf.unlink(missing_ok=True)
        raise

    pdf_filename = f"{report_path.stem}.pdf"
    return FileResponse(
        temporary_pdf,
        media_type="application/pdf",
        filename=pdf_filename,
        background=BackgroundTask(temporary_pdf.unlink, missing_ok=True),
    )