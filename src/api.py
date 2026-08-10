import logging
import os
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import anyio
from fastapi import FastAPI, HTTPException, Path as PathParameter, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

REPORTS_DIR = Path(os.getenv("DATA_DIR", "/app/data/reports"))
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