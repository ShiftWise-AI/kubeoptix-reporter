import os
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Path as PathParameter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

REPORTS_DIR = Path(os.getenv("DATA_DIR", "/data/reports"))

app = FastAPI(
    title="Assessment API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok"}


@app.get("/report/{filename}")
async def get_report(
    filename: str = PathParameter(..., description="Nome do arquivo Markdown")
) -> StreamingResponse:
    if Path(filename).name != filename or not filename.lower().endswith(".md"):
        raise HTTPException(
            status_code=400,
            detail="Informe somente o nome de um arquivo com extensão .md"
        )

    reports_dir = REPORTS_DIR.resolve()
    report_path = (reports_dir / filename).resolve()

    if not report_path.is_relative_to(reports_dir) or not report_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Arquivo não encontrado: {filename}"
        )

    try:
        report = report_path.open("r", encoding="utf-8")
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao ler o arquivo: {exc}"
        ) from exc

    return StreamingResponse(
        report,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}"
        },
        background=BackgroundTask(report.close),
    )