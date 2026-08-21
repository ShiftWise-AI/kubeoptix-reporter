#!/usr/bin/env python3
"""Aplica o template Red Hat Consulting a um Markdown e gera um PDF A4."""

import argparse
import base64
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import pypandoc
AUTOMATIC_REPORT_NOTE_RE = re.compile(
    r"^[ \t]*\*?Relatório gerado automaticamente a partir dos artefatos "
    r"exportados em .*?\.?\*?[ \t]*$\n?",
    re.IGNORECASE | re.MULTILINE,
)
DOCUMENT_DATE_RE = re.compile(
    r"^(?:Janeiro|Fevereiro|Março|Abril|Maio|Junho|Julho|Agosto|"
    r"Setembro|Outubro|Novembro|Dezembro) de [0-9]{4}$"
)
MARKDOWN_PNG_DATA_URI_RE = re.compile(
    r"!\[(?P<alt>[^\]]*)\]\((?P<uri>data:image/png;base64,[A-Za-z0-9+/=\r\n]+)\)",
    re.IGNORECASE,
)
HTML_PNG_DATA_URI_RE = re.compile(
    r"(?P<prefix><img\b[^>]*\bsrc=)(?P<quote>[\"'])"
    r"(?P<uri>data:image/png;base64,[A-Za-z0-9+/=\r\n]+)"
    r"(?P=quote)",
    re.IGNORECASE,
)


class TemplateError(Exception):
    pass


def decode_data_uri_png(data_uri: str) -> bytes:
    _, encoded_payload = data_uri.split(",", 1)
    normalized_payload = "".join(encoded_payload.split())
    try:
        return base64.b64decode(normalized_payload, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise TemplateError("Data URI PNG base64 invalido") from exc


def materialize_inline_png_images(content: str, temp_dir: Path) -> str:
    image_dir = temp_dir / "embedded-images"
    image_dir.mkdir(parents=True, exist_ok=True)
    image_counter = 0

    def write_png(data_uri: str) -> Path:
        nonlocal image_counter
        image_counter += 1
        image_path = image_dir / f"inline-image-{image_counter}.png"
        image_path.write_bytes(decode_data_uri_png(data_uri))
        return image_path.resolve()

    def replace_markdown_image(match: re.Match[str]) -> str:
        image_path = write_png(match.group("uri"))
        alt = match.group("alt")
        return f"![{alt}]({image_path})"

    def replace_html_image(match: re.Match[str]) -> str:
        image_path = write_png(match.group("uri"))
        return f"{match.group('prefix')}{match.group('quote')}{image_path}{match.group('quote')}"

    content = MARKDOWN_PNG_DATA_URI_RE.sub(replace_markdown_image, content)
    content = HTML_PNG_DATA_URI_RE.sub(replace_html_image, content)
    return content


def require_command(command: str, install_hint: str) -> None:
    if shutil.which(command) is None:
        raise TemplateError(
            f"Comando nao encontrado: {command}. Instale com: {install_hint}"
        )


def resolve_pandoc() -> list[str]:
    executable = shutil.which("pandoc")
    if executable:
        return [executable]

    try:
        bundled_executable = pypandoc.get_pandoc_path()
    except OSError as exc:
        raise TemplateError(
            "pandoc nao encontrado. Instale o pacote pypandoc_binary"
        ) from exc
    return [bundled_executable]


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


def prepare_markdown(markdown_path: Path, temp_dir: Path) -> Path:
    content = markdown_path.read_text(encoding="utf-8")
    content = AUTOMATIC_REPORT_NOTE_RE.sub("", content)
    content = materialize_inline_png_images(content, temp_dir)
    prepared_path = temp_dir / markdown_path.name
    prepared_path.write_text(content, encoding="utf-8")
    return prepared_path


def quote_attribute(value: str) -> str:
    return value.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


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


IMAGE_BLOCK_RE = re.compile(r"^image::(?P<target>\S+)\[(?P<attrs>[^\]]*)\]$", re.MULTILINE)
IMAGE_INLINE_RE = re.compile(r"(?<!:)image:(?!:)(?P<target>\S+?)\[(?P<attrs>[^\]]*)\]")
# Matches the "image paragraph" + "italic caption paragraph" pattern that
# pandoc produces from a Markdown image immediately followed by an italic
# caption line (e.g. "![alt](img.png)" then "*Figura 1: ...*").
IMAGE_WITH_CAPTION_PARAGRAPH_RE = re.compile(
    r"^image:(?P<target>\S+)\[(?P<attrs>[^\]]*)\]\n\n_(?P<caption>[^\n_]+)_[ \t]*$",
    re.MULTILINE,
)
# Asciidoctor PDF auto-numbers block titles used as image captions (e.g.
# "Figura 1. "), so a manually written "Figura 1:" prefix is stripped to
# avoid a duplicated figure number.
CAPTION_FIGURE_PREFIX_RE = re.compile(r"^figura\s+\d+\s*[:.]?\s*", re.IGNORECASE)

# A4 page (210mm) minus the theme's left/right margins (17mm each).
PAGE_CONTENT_WIDTH_MM = 176.0
# Leaves room on the page for the heading, caption and surrounding text.
MAX_IMAGE_HEIGHT_MM = 170.0
# Floor so a downscaled image never becomes illegible.
MIN_IMAGE_WIDTH_MM = 40.0
PNG_ASSUMED_DPI = 96.0


def attach_image_captions(content: str) -> str:
    """Turn a standalone italic paragraph right after an image into a native
    AsciiDoc block title, so the image and its caption always paginate as one
    unbreakable unit instead of risking a page break between them.
    """

    def replace(match: re.Match[str]) -> str:
        caption = CAPTION_FIGURE_PREFIX_RE.sub("", match.group("caption").strip())
        return f".{caption}\nimage::{match.group('target')}[{match.group('attrs')}]"

    return IMAGE_WITH_CAPTION_PARAGRAPH_RE.sub(replace, content)


def fit_png_width_mm(image_path: Path) -> float | None:
    """Largest width (mm) keeping a PNG inside the page content box, same aspect ratio.

    Returns None when the image already fits, so its natural size is left untouched.
    """
    try:
        width_px, height_px = read_png_dimensions(image_path)
    except TemplateError:
        return None

    width_mm = width_px / PNG_ASSUMED_DPI * 25.4
    height_mm = height_px / PNG_ASSUMED_DPI * 25.4
    scale = min(PAGE_CONTENT_WIDTH_MM / width_mm, MAX_IMAGE_HEIGHT_MM / height_mm)
    if scale >= 1.0:
        return None

    constrained_width_mm = width_mm * scale
    # Only raise a downscaled image to the legibility floor when that width
    # still respects the height ceiling; otherwise the height ceiling wins,
    # since staying on the same page as its caption/text matters more.
    width_at_floor_mm = MIN_IMAGE_WIDTH_MM
    height_at_floor_mm = width_at_floor_mm * (height_mm / width_mm)
    if constrained_width_mm < width_at_floor_mm and height_at_floor_mm <= MAX_IMAGE_HEIGHT_MM:
        constrained_width_mm = width_at_floor_mm
    return round(constrained_width_mm, 1)


def has_explicit_image_size(attrs: str) -> bool:
    if re.search(r"\b(width|pdfwidth|scaledwidth)\s*=", attrs):
        return True
    positional = [part.strip() for part in attrs.split(",")][1:]
    return any(positional)


def resolve_local_image_path(target: str, base_dir: Path) -> Path | None:
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", target):
        return None
    candidate = Path(target)
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    return candidate if candidate.is_file() else None


def apply_image_size_constraints(content: str, base_dir: Path) -> str:
    """Proportionally shrink oversized local PNGs so they stay on the page with
    their referencing text/caption, without ever distorting their aspect ratio.
    """

    def constrain(match: re.Match[str], macro: str) -> str:
        target = match.group("target")
        attrs = match.group("attrs")
        if has_explicit_image_size(attrs):
            return match.group(0)
        image_path = resolve_local_image_path(target, base_dir)
        if image_path is None or image_path.suffix.lower() != ".png":
            return match.group(0)
        width_mm = fit_png_width_mm(image_path)
        if width_mm is None:
            return match.group(0)
        new_attrs = f"{attrs},width={width_mm}mm" if attrs.strip() else f"width={width_mm}mm"
        return f"{macro}{target}[{new_attrs}]"

    content = IMAGE_BLOCK_RE.sub(lambda m: constrain(m, "image::"), content)
    content = IMAGE_INLINE_RE.sub(lambda m: constrain(m, "image:"), content)
    return content


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
        resolve_pandoc()
        + [
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
    source_dir: Path,
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
        resolve_pandoc()
        + [
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
    content = re.sub(r"^\[\[[^\n]+\]\]\n", "", content, flags=re.MULTILINE)
    content = re.sub(r"^(={2,}) ", lambda match: f"{match.group(1)[1:]} ", content, flags=re.MULTILINE)
    content = re.sub(
        r"^(= [^\n]+\n)\n(?P<quote>____\n.*?\n____)\n\n(?:'{5}\n\n)?(?P<section>== [^\n]+\n)",
        r"\1\n\g<section>\n\g<quote>\n",
        content,
        count=1,
        flags=re.DOTALL,
    )
    content = attach_image_captions(content)
    content = apply_image_size_constraints(content, source_dir)

    title_match = re.match(r"^= (?P<title>[^\n]+)\n", content)
    if not title_match:
        raise TemplateError("Nao foi possivel identificar o titulo principal do Markdown")

    source_title = re.sub(r"`([^`]+)`", r"\1", title_match.group("title"))
    cover_title = description
    attribute_lines = [
            ":doctype: book",
            ":toc: macro",
            ":toc-title: Sumário",
            ":toclevels: 3",
            ":chapter-label:",
            ":figure-caption: Figura",
            ":table-caption: Tabela",
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

    resolve_pandoc()
    asciidoctor_command = resolve_asciidoctor_pdf()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="assessment_pdf_") as temp_name:
        temp_dir = Path(temp_name)
        prepared_path = prepare_markdown(markdown_path, temp_dir)
        asciidoc_path = temp_dir / f"{markdown_path.stem}.adoc"
        convert_to_asciidoc(
            prepared_path,
            asciidoc_path,
            template_dir,
            markdown_path.parent,
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