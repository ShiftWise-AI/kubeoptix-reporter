import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

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
def health_check():
    return {"status": "ok"}


@app.get("/assessment/report")
def get_assessment_report(
    file: str = Query(..., description="Caminho do arquivo Markdown")
):
    if not file.lower().endswith(".md"):
        raise HTTPException(
            status_code=400,
            detail="O arquivo deve possuir extensão .md"
        )

    if not os.path.isfile(file):
        raise HTTPException(
            status_code=404,
            detail=f"Arquivo não encontrado: {file}"
        )

    try:
        with open(file, "r", encoding="utf-8") as f:
            content = f.read()

        return {
            "filename": os.path.basename(file),
            "path": file,
            "content": content
        }

    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao ler o arquivo: {exc}"
        )