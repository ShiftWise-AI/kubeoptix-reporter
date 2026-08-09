#!/usr/bin/env python3

import argparse
import hashlib
import pandas as pd
from pathlib import Path
import re


def extract_markdown_tables(md_content):
    """
    Extrai tabelas Markdown do arquivo.
    """
    lines = md_content.splitlines()

    tables = []
    current_table = []

    for line in lines:
        if "|" in line:
            current_table.append(line)
        else:
            if current_table:
                tables.append(current_table)
                current_table = []

    if current_table:
        tables.append(current_table)

    return tables


def markdown_table_to_dataframe(table_lines):
    """
    Converte uma tabela Markdown em DataFrame.
    """

    table_lines = [line.strip() for line in table_lines]

    if len(table_lines) < 2:
        return None

    header = [col.strip() for col in table_lines[0].strip("|").split("|")]

    data = []

    for line in table_lines[2:]:
        row = [col.strip() for col in line.strip("|").split("|")]

        while len(row) < len(header):
            row.append("")

        data.append(row[:len(header)])

    return pd.DataFrame(data, columns=header)


def compute_md5(file_path):
    hasher = hashlib.md5()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_existing_tables(files_dir):
    pattern = re.compile(r"^tabela(\d+)\.xlsx$")
    hash_to_name = {}
    max_index = 0

    for existing_file in files_dir.glob("tabela*.xlsx"):
        match = pattern.match(existing_file.name)
        if not match:
            continue
        max_index = max(max_index, int(match.group(1)))
        file_hash = compute_md5(existing_file)
        hash_to_name[file_hash] = existing_file.name

    return hash_to_name, max_index + 1


def append_inventory_event(events_file, file_name, origin, file_hash):
    if not events_file:
        return
    with events_file.open("a", encoding="utf-8") as f:
        f.write(f"{file_name}\t{origin}\t{file_hash}\n")


def md_to_xlsx_tables(md_file, files_dir, inventory_events=None):
    md_content = Path(md_file).read_text(encoding="utf-8")

    tables = extract_markdown_tables(md_content)

    if not tables:
        print(f"Nenhuma tabela Markdown encontrada em: {md_file}")
        return 0

    md_path = Path(md_file)
    output_dir = Path(files_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    hash_to_name, next_index = load_existing_tables(output_dir)

    generated_count = 0

    for table in tables:
        df = markdown_table_to_dataframe(table)

        if df is not None:
            tmp_file = output_dir / f".tmp_tabela_{next_index}.xlsx"

            with pd.ExcelWriter(tmp_file, engine="openpyxl") as writer:
                df.to_excel(
                    writer,
                    sheet_name="Tabela",
                    index=False
                )

            file_hash = compute_md5(tmp_file)
            if file_hash in hash_to_name:
                final_name = hash_to_name[file_hash]
                tmp_file.unlink(missing_ok=True)
            else:
                final_name = f"tabela{next_index}.xlsx"
                final_path = output_dir / final_name
                tmp_file.rename(final_path)
                hash_to_name[file_hash] = final_name
                next_index += 1
                generated_count += 1
                print(f"Arquivo gerado: {final_path}")

            origin = str(md_path)
            append_inventory_event(inventory_events, final_name, origin, file_hash)

    if generated_count == 0:
        print(f"Nenhuma tabela nova gerada em: {md_file}")

    return generated_count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Converte tabelas de um arquivo Markdown em planilhas Excel separadas."
    )
    parser.add_argument(
        "--md-file",
        required=True,
        help="Caminho do arquivo Markdown de entrada (.md)."
    )
    parser.add_argument(
        "--files-dir",
        required=False,
        help="Diretório único para salvar tabelas (padrão: <pasta_do_md>/files)."
    )
    parser.add_argument(
        "--inventory-events",
        required=False,
        help="Arquivo TSV para registrar eventos de inventário."
    )

    args = parser.parse_args()
    md_file = Path(args.md_file)

    if not md_file.exists() or not md_file.is_file():
        print(f"Arquivo nao encontrado: {md_file}")
        raise SystemExit(1)

    if md_file.suffix.lower() != ".md":
        print(f"Arquivo invalido (esperado .md): {md_file}")
        raise SystemExit(1)

    files_dir = Path(args.files_dir) if args.files_dir else md_file.parent / "files"
    events_file = Path(args.inventory_events) if args.inventory_events else None

    total_generated = md_to_xlsx_tables(md_file, files_dir, events_file)
    print(f"Total de planilhas geradas: {total_generated}")