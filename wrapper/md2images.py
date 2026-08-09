#!/usr/bin/env python3
"""
Script: md_to_images.py
Descrição: Percorre arquivos .md, extrai imagens e gráficos Mermaid e 
           converte para PNG com suporte a múltiplos formatos.
Uso: python3 md_to_images.py [diretório_entrada] [diretório_saída] [--verbose]
Exemplo: python3 md_to_images.py . ./output_images --verbose
"""

import os
import sys
import re
import subprocess
import hashlib
from pathlib import Path
from typing import List, Tuple
from datetime import datetime

class MDToImagesConverter:
    def __init__(self, input_dir: str, output_dir: str, verbose: bool = False, inventory_events: str = None):
        self.input_dir = Path(input_dir).resolve()
        self.output_dir = Path(output_dir).resolve() if output_dir else None
        self.verbose = verbose
        self.inventory_events = Path(inventory_events).resolve() if inventory_events else None
        self.input_is_file = self.input_dir.is_file()
        self.scan_root = self.input_dir.parent if self.input_is_file else self.input_dir
        
        # Contadores
        self.count_images = 0
        self.count_mermaid = 0
        self.count_errors = 0
        
        # Criar diretório de saída para modo diretório.
        if not self.input_is_file:
            if self.output_dir is None:
                self.output_dir = self.input_dir / 'files'
            self.output_dir.mkdir(parents=True, exist_ok=True)

        if self.input_is_file and self.output_dir is None:
            self.output_dir = self.input_dir.parent / 'files'

        if self.output_dir is not None:
            self.output_dir.mkdir(parents=True, exist_ok=True)

        self.image_hash_to_name, self.next_image_index = self._load_existing_images()
        
        # Validar dependências
        self._check_dependencies()
    
    def log(self, level: str, msg: str):
        """Log com colorização"""
        colors = {
            'INFO': '\033[0;32m',
            'WARN': '\033[1;33m',
            'ERROR': '\033[0;31m',
            'DEBUG': '\033[0;36m',
        }
        reset = '\033[0m'
        
        if level == 'DEBUG' and not self.verbose:
            return
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        color = colors.get(level, '')
        print(f"{color}[{timestamp}] {level:6} | {msg}{reset}")
    
    def _check_dependencies(self):
        """Verifica se as dependências estão instaladas"""
        self.log('INFO', '🔍 Verificando dependências...')
        
        dependencies = {
            'mmdc': 'npm install -g mermaid-cli',
            'convert': 'sudo apt-get install imagemagick',
        }
        
        for cmd, install_cmd in dependencies.items():
            if not self._command_exists(cmd):
                self.log('ERROR', f'Dependência não encontrada: {cmd}')
                self.log('ERROR', f'Instale com: {install_cmd}')
                sys.exit(1)
        
        self.log('INFO', '✓ Todas as dependências OK')
    
    def _command_exists(self, cmd: str) -> bool:
        """Verifica se um comando existe"""
        result = subprocess.run(
            f'which {cmd}',
            shell=True,
            capture_output=True
        )
        return result.returncode == 0
    
    def _extract_mermaid_blocks(self, md_file: Path) -> List[Tuple[int, str]]:
        """Extrai blocos mermaid do arquivo markdown"""
        blocks = []
        content = md_file.read_text(encoding='utf-8')
        
        # Regex para encontrar blocos ```mermaid ... ```
        pattern = r'```mermaid\n(.*?)\n```'
        matches = re.finditer(pattern, content, re.DOTALL)
        
        for idx, match in enumerate(matches, 1):
            blocks.append((idx, match.group(1)))
        
        return blocks
    
    def _extract_image_references(self, md_file: Path) -> List[str]:
        """Extrai referências de imagem ![alt](path) do markdown"""
        images = []
        content = md_file.read_text(encoding='utf-8')
        
        # Regex para ![alt](path)
        pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
        matches = re.finditer(pattern, content)
        
        for match in matches:
            img_path = match.group(2)
            images.append(img_path)
        
        return images
    
    def _convert_mermaid_to_png(self, mermaid_content: str, output_path: Path) -> bool:
        """Converte diagrama Mermaid para arquivo de imagem (preferencialmente PNG)."""
        try:
            # Salvar conteúdo Mermaid temporário
            temp_mmd = output_path.with_name(f'{output_path.stem}__tmp.mmd')
            temp_png = output_path.with_name(f'{output_path.stem}__tmp.png')
            
            temp_mmd.write_text(mermaid_content)
            
            cmd_mmdc_png = [
                'mmdc',
                '-i', str(temp_mmd),
                '-o', str(temp_png),
                '-s', '2',
                '-w', '16000',
                '-H', '16000',
                '-b', 'white'
            ]

            result_png = subprocess.run(
                cmd_mmdc_png,
                capture_output=True,
                timeout=180
            )

            if result_png.returncode != 0:
                self.log('DEBUG', f'mmdc png stderr: {result_png.stderr.decode()}')
                return False
            
            # Normalizar PNG removendo canvas excedente e preservando legibilidade.
            cmd_convert = [
                'convert',
                str(temp_png),
                '-background', 'white',
                '-alpha', 'remove',
                '-alpha', 'off',
                '-trim',
                '+repage',
                '-bordercolor', 'white',
                '-border', '20',
                str(output_path)
            ]
            
            result = subprocess.run(
                cmd_convert,
                capture_output=True,
                timeout=30
            )
            
            if result.returncode != 0:
                self.log('DEBUG', f'convert stderr: {result.stderr.decode()}')
                return False
            
            # Limpeza
            temp_mmd.unlink(missing_ok=True)
            temp_png.unlink(missing_ok=True)
            
            return True
        
        except subprocess.TimeoutExpired:
            self.log('ERROR', f'Timeout ao converter Mermaid: {output_path.name}')
            return False
        except Exception as e:
            self.log('ERROR', f'Erro ao converter Mermaid: {str(e)}')
            return False
    
    def _convert_image_to_png(self, src_path: Path, dst_path: Path) -> bool:
        """Converte imagem para PNG"""
        try:
            cmd = [
                'convert',
                str(src_path),
                '-background', 'white',
                '-alpha', 'remove',
                '-alpha', 'off',
                str(dst_path)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=30
            )
            
            return result.returncode == 0
        
        except subprocess.TimeoutExpired:
            self.log('ERROR', f'Timeout ao converter imagem: {src_path.name}')
            return False
        except Exception as e:
            self.log('ERROR', f'Erro ao converter imagem: {str(e)}')
            return False

    def _compute_md5(self, file_path: Path) -> str:
        hasher = hashlib.md5()
        with file_path.open('rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _load_existing_images(self):
        pattern = re.compile(r'^imagem(\d+)\.png$')
        hash_to_name = {}
        max_index = 0

        if self.output_dir is None:
            return hash_to_name, 1

        for existing_file in self.output_dir.glob('imagem*.png'):
            match = pattern.match(existing_file.name)
            if not match:
                continue
            max_index = max(max_index, int(match.group(1)))
            file_hash = self._compute_md5(existing_file)
            hash_to_name[file_hash] = existing_file.name

        return hash_to_name, max_index + 1

    def _append_inventory_event(self, file_name: str, origin: str, file_hash: str):
        if self.inventory_events is None:
            return
        with self.inventory_events.open('a', encoding='utf-8') as f:
            f.write(f'{file_name}\t{origin}\t{file_hash}\n')

    def _register_image(self, tmp_file: Path, origin: str) -> str:
        file_hash = self._compute_md5(tmp_file)
        if file_hash in self.image_hash_to_name:
            final_name = self.image_hash_to_name[file_hash]
            tmp_file.unlink(missing_ok=True)
        else:
            final_name = f'imagem{self.next_image_index}.png'
            final_path = self.output_dir / final_name
            tmp_file.rename(final_path)
            self.image_hash_to_name[file_hash] = final_name
            self.next_image_index += 1

        self._append_inventory_event(final_name, origin, file_hash)
        return final_name
    
    def process_markdown_file(self, md_file: Path):
        """Processa um arquivo markdown"""
        if self.input_is_file:
            display_name = md_file.name
        else:
            display_name = md_file.relative_to(self.input_dir)

        self.log('INFO', f'Processando: {display_name}')
        
        output_subdir = self.output_dir
        output_subdir.mkdir(parents=True, exist_ok=True)
        
        # Extrair e converter Mermaid
        mermaid_blocks = self._extract_mermaid_blocks(md_file)
        for block_idx, content in mermaid_blocks:
            tmp_path = output_subdir / f'.tmp_mermaid_{self.next_image_index}_{block_idx}.png'
            self.log('DEBUG', 'Convertendo Mermaid para PNG')
            
            if self._convert_mermaid_to_png(content, tmp_path):
                origin = f'{md_file}#mermaid{block_idx}'
                final_name = self._register_image(tmp_path, origin)
                self.log('INFO', f'  ✓ Mermaid -> {output_subdir / final_name}')
                self.count_mermaid += 1
            else:
                self.log('ERROR', f'  ❌ Erro ao converter Mermaid #{block_idx}')
                self.count_errors += 1
        
        # Extrair e converter imagens referenciadas
        image_refs = self._extract_image_references(md_file)
        for img_ref in image_refs:
            # Resolver caminho relativo
            if img_ref.startswith('/'):
                full_path = Path(img_ref)
            else:
                full_path = (md_file.parent / img_ref).resolve()
            
            if full_path.exists():
                tmp_path = output_subdir / f'.tmp_image_{self.next_image_index}.png'
                self.log('DEBUG', f'Convertendo imagem: {full_path.name}')
                
                if self._convert_image_to_png(full_path, tmp_path):
                    origin = f'{md_file}#image:{img_ref}'
                    final_name = self._register_image(tmp_path, origin)
                    self.log('INFO', f'  ✓ Imagem -> {output_subdir / final_name}')
                    self.count_images += 1
                else:
                    self.log('ERROR', f'  ❌ Erro ao converter: {full_path.name}')
                    self.count_errors += 1
            else:
                self.log('WARN', f'  ⚠ Imagem não encontrada: {img_ref}')
    
    def run(self):
        """Executa o processamento"""
        self.log('INFO', f'Diretório de entrada: {self.input_dir}')
        self.log('INFO', f'Diretório de saída: {self.output_dir}')
        
        # Aceita um arquivo .md único ou um diretório com múltiplos .md.
        if self.input_is_file:
            if self.input_dir.suffix.lower() != '.md':
                self.log('ERROR', 'Arquivo de entrada precisa ter extensão .md')
                return False
            md_files = [self.input_dir]
        else:
            md_files = []
            for md_file in self.input_dir.rglob('*.md'):
                if self.output_dir is not None and self.output_dir in md_file.parents:
                    continue
                md_files.append(md_file)
        
        if not md_files:
            self.log('WARN', 'Nenhum arquivo .md encontrado')
            return
        
        self.log('INFO', f'Encontrados {len(md_files)} arquivo(s) markdown')
        self.log('INFO', '─' * 60)
        
        for md_file in md_files:
            self.process_markdown_file(md_file)
        
        # Resumo final
        self.log('INFO', '─' * 60)
        self.log('INFO', '📊 RESUMO DA CONVERSÃO')
        self.log('INFO', '─' * 60)
        self.log('INFO', f'Imagens convertidas: {self.count_images}')
        self.log('INFO', f'Diagramas Mermaid convertidos: {self.count_mermaid}')
        self.log('INFO', f'Erros encontrados: {self.count_errors}')
        self.log('INFO', f'Total de arquivos: {self.count_images + self.count_mermaid}')
        self.log('INFO', '─' * 60)
        
        return self.count_errors == 0


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Extrai imagens e gráficos Mermaid de arquivos markdown e converte para PNG'
    )
    parser.add_argument(
        'input_dir',
        nargs='?',
        default='.',
        help='Diretório de entrada (padrão: .)'
    )
    parser.add_argument(
        'output_dir',
        nargs='?',
        default=None,
        help='Diretório único de saída (padrão: <input>/files)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Ativar modo verbose'
    )
    parser.add_argument(
        '--inventory-events',
        default=None,
        help='Arquivo TSV para registrar eventos de inventário'
    )
    
    args = parser.parse_args()
    
    converter = MDToImagesConverter(
        args.input_dir,
        args.output_dir,
        args.verbose,
        args.inventory_events
    )
    
    success = converter.run()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
