#!/usr/bin/env python3
"""
Converte arquivos Markdown para PDF com suporte a blocos Mermaid.

Exemplos:
  python3 md_to_pdf.py arquivo.md
  python3 md_to_pdf.py arquivo.md saida.pdf
  python3 md_to_pdf.py ./docs ./pdfs
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MERMAID_BLOCK_RE = re.compile(
    r"(?P<fence>`{3,}|~{3,})[ \t]*(?:mermaid|\{[^\n}]*\.mermaid[^\n}]*\})[ \t]*\n"
    r"(?P<body>.*?)\n(?P=fence)[ \t]*",
    re.IGNORECASE | re.DOTALL,
)


class MarkdownToPdfError(Exception):
    pass


def require_command(command: str, install_hint: str) -> None:
    if shutil.which(command) is None:
        raise MarkdownToPdfError(f"Comando não encontrado: {command}. Instale com: {install_hint}")


def convert_mermaid_to_png(mermaid_content: str, output_path: Path) -> None:
    require_command("mmdc", "npm install -g mermaid-cli")

    temp_mmd = output_path.with_suffix(".mmd")
    temp_mmd.write_text(mermaid_content, encoding="utf-8")
    try:
        result = subprocess.run(
            ["mmdc", "-i", str(temp_mmd), "-o", str(output_path), "-b", "white"],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode != 0:
            raise MarkdownToPdfError(result.stderr.strip() or result.stdout.strip() or "Falha ao converter Mermaid")
    finally:
        if temp_mmd.exists():
            temp_mmd.unlink()


def render_markdown_to_pdf(markdown_path: Path, output_pdf: Path) -> None:
    require_command("pandoc", "sudo apt-get install pandoc")
    require_command("weasyprint", "sudo apt-get install weasyprint")

    content = markdown_path.read_text(encoding="utf-8")

    temp_dir = Path(tempfile.mkdtemp(prefix="md_to_pdf_", dir=str(output_pdf.parent)))
    try:
        counter = 0

        def replace_mermaid(match: re.Match[str]) -> str:
            nonlocal counter
            counter += 1
            image_name = f"mermaid_{counter}.png"
            image_path = temp_dir / image_name
            convert_mermaid_to_png(match.group("body").strip(), image_path)
            return f"\n\n![Diagrama Mermaid]({image_path.as_uri()})\n\n"

        transformed_content = MERMAID_BLOCK_RE.sub(replace_mermaid, content)

        temp_markdown = temp_dir / f"{markdown_path.stem}.md"
        temp_markdown.write_text(transformed_content, encoding="utf-8")

        result = subprocess.run(
            [
                "pandoc",
                str(temp_markdown),
                "-o",
                str(output_pdf),
                "--pdf-engine=weasyprint",
                "--standalone",
                "--resource-path",
                str(temp_dir),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            raise MarkdownToPdfError(result.stderr.strip() or result.stdout.strip() or "Falha ao gerar PDF")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


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
    parser = argparse.ArgumentParser(description="Converte Markdown para PDF com suporte a Mermaid")
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
