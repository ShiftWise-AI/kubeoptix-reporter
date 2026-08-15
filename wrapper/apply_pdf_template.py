#!/usr/bin/env python3
"""Aplica o template Red Hat Consulting a um Markdown e gera um PDF A4."""

import argparse
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path


MERMAID_BLOCK_RE = re.compile(
    r"(?P<fence>`{3,}|~{3,})[ \t]*(?:mermaid|\{[^\n}]*\.mermaid[^\n}]*\})[ \t]*\n"
    r"(?P<body>.*?)\n(?P=fence)[ \t]*",
    re.IGNORECASE | re.DOTALL,
)
MERMAID_MARKER_RE = re.compile(r"^MERMAIDDIAGRAM(?P<number>[0-9]+)TOKEN$", re.MULTILINE)
AUTOMATIC_REPORT_NOTE_RE = re.compile(
    r"^[ \t]*\*?Relatório gerado automaticamente a partir dos artefatos "
    r"exportados em .*?\.?\*?[ \t]*$\n?",
    re.IGNORECASE | re.MULTILINE,
)
DOCUMENT_DATE_RE = re.compile(
    r"^(?:Janeiro|Fevereiro|Março|Abril|Maio|Junho|Julho|Agosto|"
    r"Setembro|Outubro|Novembro|Dezembro) de [0-9]{4}$"
)


class TemplateError(Exception):
    pass


def require_command(command: str, install_hint: str) -> None:
    if shutil.which(command) is None:
        raise TemplateError(
            f"Comando nao encontrado: {command}. Instale com: {install_hint}"
        )


def resolve_asciidoctor_pdf() -> list[str]:
    executable = shutil.which("asciidoctor-pdf")
    if executable:
        return [executable]

    require_command("ruby", "sudo apt-get install ruby")
    result = subprocess.run(
        [
            "ruby",
            "-e",
            "puts Gem.bin_path('asciidoctor-pdf', 'asciidoctor-pdf')",
        ],
        capture_output=True,
        text=True,
    )
    gem_executable = result.stdout.strip()
    if result.returncode != 0 or not Path(gem_executable).is_file():
        raise TemplateError(
            "asciidoctor-pdf nao encontrado. Instale com: "
            "gem install --user-install asciidoctor-pdf rouge"
        )
    return ["ruby", gem_executable]


def run_command(command: list[str], timeout: int) -> None:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise TemplateError(message or f"Falha ao executar: {command[0]}")


def render_mermaid(source: str, output_path: Path) -> None:
    mermaid_path = output_path.with_suffix(".mmd")
    mermaid_path.write_text(source, encoding="utf-8")
    run_command(
        [
            "mmdc",
            "-i",
            str(mermaid_path),
            "-o",
            str(output_path),
            "-b",
            "white",
            "-s",
            "2",
        ],
        timeout=180,
    )


def prepare_markdown(markdown_path: Path, temp_dir: Path) -> Path:
    content = markdown_path.read_text(encoding="utf-8")
    content = AUTOMATIC_REPORT_NOTE_RE.sub("", content)
    diagram_number = 0

    def replace_mermaid(match: re.Match[str]) -> str:
        nonlocal diagram_number
        diagram_number += 1
        image_path = temp_dir / f"mermaid-{diagram_number}.png"
        render_mermaid(match.group("body").strip(), image_path)
        return f"\n\nMERMAIDDIAGRAM{diagram_number}TOKEN\n\n"

    transformed = MERMAID_BLOCK_RE.sub(replace_mermaid, content)
    prepared_path = temp_dir / markdown_path.name
    prepared_path.write_text(transformed, encoding="utf-8")
    return prepared_path


def quote_attribute(value: str) -> str:
    return value.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def mermaid_pdf_width(image_path: Path) -> int:
    width, height = read_png_dimensions(image_path)
    aspect_ratio = width / height
    if aspect_ratio >= 2.2:
        return 90
    if aspect_ratio >= 1.5:
        return 78
    return 68


def read_png_dimensions(image_path: Path) -> tuple[int, int]:
    with image_path.open("rb") as image_file:
        header = image_file.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise TemplateError(f"Arquivo PNG invalido: {image_path}")

    width, height = struct.unpack(">II", header[16:24])
    if width == 0 or height == 0:
        raise TemplateError(f"Dimensoes invalidas no PNG: {image_path}")
    return width, height


def company_logo_width(image_path: Path) -> int:
    width, height = read_png_dimensions(image_path)
    return max(1, round(min(520, 267 * width / height)))


def add_section_page_breaks(content: str) -> str:
    section_number = 0

    def add_page_break(match: re.Match[str]) -> str:
        nonlocal section_number
        section_number += 1
        if section_number == 1:
            return match.group(0)
        return f"\n<<<\n\n{match.group('heading')}"

    return re.sub(
        r"^\n?(?P<heading>== [^\n]+)$",
        add_page_break,
        content,
        flags=re.MULTILINE,
    )


def convert_preface_to_asciidoc(
    template_dir: Path,
    temp_dir: Path,
    customer: str,
) -> str:
    preface_path = template_dir / "prefacio.md"
    if not preface_path.is_file():
        raise TemplateError(f"Prefacio nao encontrado: {preface_path}")

    preface_content = preface_path.read_text(encoding="utf-8")
    preface_content = preface_content.replace("<customer>", customer)
    prepared_preface = temp_dir / "prefacio.md"
    prepared_preface.write_text(preface_content, encoding="utf-8")
    asciidoc_preface = temp_dir / "prefacio.adoc"
    run_command(
        [
            "pandoc",
            str(prepared_preface),
            "--from=gfm",
            "--to=asciidoc",
            "--wrap=none",
            "--output",
            str(asciidoc_preface),
        ],
        timeout=120,
    )

    content = asciidoc_preface.read_text(encoding="utf-8")
    content = re.sub(r"^\[\[[^\n]+\]\]\n", "", content, flags=re.MULTILINE)
    content = re.sub(
        r"^== (?P<title>[^\n]+)$",
        r"[preface]\n== \g<title>",
        content,
        count=1,
        flags=re.MULTILINE,
    )
    return content.strip()


def convert_to_asciidoc(
    prepared_markdown: Path,
    asciidoc_path: Path,
    template_dir: Path,
    customer: str,
    description: str,
    version: str,
    status: str,
    confidentiality: str,
    company_logo: Path | None,
    author: str | None,
    project_manager: str | None,
    document_date: str | None,
) -> None:
    preface = convert_preface_to_asciidoc(template_dir, asciidoc_path.parent, customer)
    run_command(
        [
            "pandoc",
            str(prepared_markdown),
            "--from=gfm",
            "--to=asciidoc",
            "--wrap=none",
            "--output",
            str(asciidoc_path),
        ],
        timeout=120,
    )

    content = asciidoc_path.read_text(encoding="utf-8")
    content = MERMAID_MARKER_RE.sub(
        lambda match: (
            f".Diagrama Mermaid\n"
            f"image::{asciidoc_path.parent / ('mermaid-' + match.group('number') + '.png')}"
            "[Diagrama Mermaid,align=center,pdfwidth="
            f"{mermaid_pdf_width(asciidoc_path.parent / ('mermaid-' + match.group('number') + '.png'))}%]"
        ),
        content,
    )
    content = re.sub(r"^\[\[[^\n]+\]\]\n", "", content, flags=re.MULTILINE)
    content = re.sub(r"^(={2,}) ", lambda match: f"{match.group(1)[1:]} ", content, flags=re.MULTILINE)
    content = re.sub(
        r"^(= [^\n]+\n)\n(?P<quote>____\n.*?\n____)\n\n(?:'{5}\n\n)?(?P<section>== [^\n]+\n)",
        r"\1\n\g<section>\n\g<quote>\n",
        content,
        count=1,
        flags=re.DOTALL,
    )
    content = add_section_page_breaks(content)

    title_match = re.match(r"^= (?P<title>[^\n]+)\n", content)
    if not title_match:
        raise TemplateError("Nao foi possivel identificar o titulo principal do Markdown")

    source_title = re.sub(r"`([^`]+)`", r"\1", title_match.group("title"))
    cover_title = description
    attribute_lines = [
            ":doctype: book",
            ":toc: macro",
            ":toclevels: 3",
            ":chapter-label:",
            ":icons: font",
            ":source-highlighter: rouge",
            ":pdf-page-size: A4",
            ":pdf-theme: redhat",
            f":pdf-themesdir: {template_dir / 'styles' / 'pdf'}",
            f":pdf-fontsdir: {template_dir / 'fonts'}",
            f":customer: {quote_attribute(customer)}",
            f":confidentiality: {quote_attribute(confidentiality)}",
            f":document-title: {quote_attribute(source_title)}",
            f":source-document-title: {quote_attribute(source_title)}",
            f":description: {quote_attribute(description)}",
            f":revnumber: {quote_attribute(version)}",
            f":docstatus: {quote_attribute(status)}",
    ]
    if company_logo:
        logo_width = company_logo_width(company_logo)
        attribute_lines.append(
            f":title-logo-image: image:{company_logo}"
            f"[Logomarca da empresa,width={logo_width},align=center]"
        )
    if project_manager:
        attribute_lines.append(
            f":project-manager: {quote_attribute(project_manager)}"
        )
    if document_date:
        attribute_lines.append(f":document-date: {quote_attribute(document_date)}")
    attributes = "\n".join(attribute_lines)
    title_end = title_match.end()
    author_line = f"{author}\n" if author else ""
    report_content = content[title_end:].lstrip()
    content = (
        f"= {cover_title}\n{author_line}{attributes}\n\n"
        f"{preface}\n\n<<<\n\ntoc::[]\n\n<<<\n\n{report_content}"
    )
    asciidoc_path.write_text(content, encoding="utf-8")


def render_pdf(
    markdown_path: Path,
    output_path: Path,
    template_dir: Path,
    customer: str,
    description: str,
    version: str,
    status: str,
    confidentiality: str,
    company_logo: Path | None,
    author: str | None,
    project_manager: str | None,
    document_date: str | None,
) -> None:
    theme = template_dir / "styles" / "pdf" / "redhat-theme.yml"
    fonts_dir = template_dir / "fonts"
    if not theme.is_file():
        raise TemplateError(f"Tema nao encontrado: {theme}")
    if not fonts_dir.is_dir():
        raise TemplateError(f"Pasta de fontes nao encontrada: {fonts_dir}")

    require_command("pandoc", "sudo apt-get install pandoc")
    asciidoctor_command = resolve_asciidoctor_pdf()

    if MERMAID_BLOCK_RE.search(markdown_path.read_text(encoding="utf-8")):
        require_command("mmdc", "npm install -g @mermaid-js/mermaid-cli")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="assessment_pdf_") as temp_name:
        temp_dir = Path(temp_name)
        prepared_path = prepare_markdown(markdown_path, temp_dir)
        asciidoc_path = temp_dir / f"{markdown_path.stem}.adoc"
        convert_to_asciidoc(
            prepared_path,
            asciidoc_path,
            template_dir,
            customer,
            description,
            version,
            status,
            confidentiality,
            company_logo,
            author,
            project_manager,
            document_date,
        )
        run_command(
            asciidoctor_command
            + [
                str(asciidoc_path),
                "--safe-mode=unsafe",
                "--base-dir",
                str(markdown_path.parent),
                "--destination-dir",
                str(output_path.parent),
                "--out-file",
                output_path.name,
            ],
            timeout=300,
        )


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description="Aplica um template visual a um Markdown e gera PDF"
    )
    parser.add_argument("input", type=Path, help="Arquivo Markdown de entrada")
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        help="PDF de saida (padrao: <entrada>-formatado.pdf)",
    )
    parser.add_argument(
        "--template-dir",
        type=Path,
        default=project_root / "template",
        help="Pasta que contem styles/pdf/redhat-theme.yml e fonts/",
    )
    parser.add_argument("--customer", default="Cliente", help="Nome do cliente")
    parser.add_argument(
        "--description",
        default="OpenShift Application Assessment",
        help="Descricao exibida no rodape",
    )
    parser.add_argument("--version", default="1.0", help="Versao do documento")
    parser.add_argument("--status", default="final", help="Status exibido no cabecalho")
    parser.add_argument(
        "--confidentiality",
        default="Confidencial",
        help="Classificacao exibida no rodape",
    )
    parser.add_argument(
        "--company-logo",
        type=Path,
        help="Logomarca PNG exibida na capa, redimensionada proporcionalmente",
    )
    parser.add_argument("--author", help="Autor exibido no canto inferior da capa")
    parser.add_argument(
        "--project-manager",
        help="Gerente do projeto exibido no canto inferior da capa",
    )
    parser.add_argument(
        "--document-date",
        help='Mes e ano exibidos na capa, por exemplo: "Janeiro de 2026"',
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    markdown_path = args.input.expanduser().resolve()
    template_dir = args.template_dir.expanduser().resolve()
    company_logo = args.company_logo.expanduser().resolve() if args.company_logo else None

    if not markdown_path.is_file():
        print(f"Erro: arquivo nao encontrado: {markdown_path}", file=sys.stderr)
        return 1
    if markdown_path.suffix.lower() != ".md":
        print("Erro: o arquivo de entrada deve ter extensao .md", file=sys.stderr)
        return 1
    if company_logo and not company_logo.is_file():
        print(f"Erro: logomarca nao encontrada: {company_logo}", file=sys.stderr)
        return 1
    if company_logo and company_logo.suffix.lower() != ".png":
        print("Erro: a logomarca deve ter extensao .png", file=sys.stderr)
        return 1
    if args.document_date and not DOCUMENT_DATE_RE.fullmatch(args.document_date):
        print(
            'Erro: --document-date deve usar o formato "Janeiro de 2026"',
            file=sys.stderr,
        )
        return 1

    output_path = (
        args.output.expanduser().resolve()
        if args.output
        else markdown_path.with_name(f"{markdown_path.stem}-formatado.pdf")
    )
    if output_path.suffix.lower() != ".pdf":
        print("Erro: o arquivo de saida deve ter extensao .pdf", file=sys.stderr)
        return 1

    try:
        render_pdf(
            markdown_path,
            output_path,
            template_dir,
            args.customer,
            args.description,
            args.version,
            args.status,
            args.confidentiality,
            company_logo,
            args.author,
            args.project_manager,
            args.document_date,
        )
    except (TemplateError, OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    print(f"PDF gerado: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())