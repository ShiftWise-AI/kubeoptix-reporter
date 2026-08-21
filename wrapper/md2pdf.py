#!/usr/bin/env python3
"""
Converte arquivos Markdown para PDF.

Exemplos:
    python3 md_to_pdf.py arquivo.md
    python3 md_to_pdf.py arquivo.md saida.pdf
    python3 md_to_pdf.py ./docs ./pdfs
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import pypandoc


class MarkdownToPdfError(Exception):
    pass


def require_command(command: str, install_hint: str) -> None:
    if shutil.which(command) is None:
        raise MarkdownToPdfError(f"Comando não encontrado: {command}. Instale com: {install_hint}")


def render_markdown_to_pdf(markdown_path: Path, output_pdf: Path) -> None:
    require_command("weasyprint", "sudo apt-get install weasyprint")
    try:
        pypandoc.convert_file(
            str(markdown_path),
            "pdf",
            outputfile=str(output_pdf),
            extra_args=[
                "--pdf-engine=weasyprint",
                "--standalone",
                "--resource-path",
                str(markdown_path.parent),
            ],
        )
    except RuntimeError as exc:
        raise MarkdownToPdfError(str(exc)) from exc


def resolve_output_path(input_path: Path, output_path: Path | None) -> Path:
    if output_path is None:
        return input_path.with_suffix(".pdf")

    if output_path.exists() and output_path.is_dir():
        return output_path / f"{input_path.stem}.pdf"

    return output_path


def convert_file(input_file: Path, output_file: Path) -> None:
    if not input_file.exists():
        raise MarkdownToPdfError(f"Arquivo não encontrado: {input_file}")
    if input_file.suffix.lower() != ".md":
        raise MarkdownToPdfError(f"O arquivo precisa ter extensão .md: {input_file}")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    render_markdown_to_pdf(input_file, output_file)
    print(f"PDF gerado: {output_file}")


def convert_directory(input_dir: Path, output_dir: Path | None) -> None:
    md_files = sorted(input_dir.rglob("*.md"))
    if not md_files:
        print("Nenhum arquivo .md encontrado.")
        return

    if output_dir is None:
        for md_file in md_files:
            output_pdf = md_file.with_suffix(".pdf")
            convert_file(md_file, output_pdf)
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        for md_file in md_files:
            relative_path = md_file.relative_to(input_dir)
            output_pdf = output_dir / relative_path.with_suffix(".pdf")
            output_pdf.parent.mkdir(parents=True, exist_ok=True)
            convert_file(md_file, output_pdf)


def main() -> int:
    parser = argparse.ArgumentParser(description="Converte Markdown para PDF")
    parser.add_argument("input", help="Arquivo .md ou diretório")
    parser.add_argument("output", nargs="?", help="Caminho do PDF ou diretório de saída")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve() if args.output else None

    try:
        if input_path.is_dir():
            convert_directory(input_path, output_path)
        else:
            final_output = resolve_output_path(input_path, output_path)
            convert_file(input_path, final_output)
    except MarkdownToPdfError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired:
        print("Erro: tempo limite excedido durante a conversão.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    main()
