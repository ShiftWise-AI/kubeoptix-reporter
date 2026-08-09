#!/usr/bin/env python3

import sys
import os
import pypandoc


def md_to_docx(md_file):
    if not os.path.isfile(md_file):
        print(f"Erro: arquivo não encontrado: {md_file}")
        sys.exit(1)

    if not md_file.lower().endswith(".md"):
        print("Erro: o arquivo deve possuir extensão .md")
        sys.exit(1)

    docx_file = os.path.splitext(md_file)[0] + ".docx"

    try:
        pypandoc.convert_file(
            md_file,
            "docx",
            outputfile=docx_file
        )

        print(f"Arquivo gerado com sucesso: {docx_file}")

    except Exception as e:
        print(f"Erro durante a conversão: {e}")
        sys.exit(1)


def main():
    if len(sys.argv) != 2:
        print(f"Uso: {sys.argv[0]} arquivo.md")
        sys.exit(1)

    md_to_docx(sys.argv[1])


if __name__ == "__main__":
    main()