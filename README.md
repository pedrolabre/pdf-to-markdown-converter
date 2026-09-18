# PDF to Markdown Converter

O **PDF to Markdown Converter** é uma ferramenta local-first desenvolvida em Python para converter documentos PDF em arquivos Markdown estruturados e semanticamente ricos, com compilação direta para HTML5.

A ferramenta implementa uma esteira híbrida com análise de qualidade: extrai texto vetorial diretamente quando a camada textual é íntegra e aplica fallback transparente para OCR em memória quando o documento é escaneado, protegido ou possui codificações corrompidas.

O repositório está em estágio preparatório e ainda não contém implementação funcional ou dependências instaladas. O desenvolvimento seguirá uma abordagem incremental orientada a testes (TDD), com separação estrita entre regras de domínio, adaptadores de extração, normalização e interfaces.

## Objetivo

Converter arquivos PDF em documentos Markdown (`.md`) canônicos e páginas HTML5 (`.html`), garantindo fidelidade estrutural (títulos, listas, blocos de código e parágrafos contínuos) sem dependência de serviços remotos, nuvem ou modelos externos.

## Premissas Técnicas

- **Local-First**: Execução 100% local, garantindo privacidade e segurança total dos documentos processados.
- **Zero I/O Temporário no OCR**: Processamento de imagens estritamente em memória RAM através de streams e buffers de bytes, sem criação de arquivos temporários em disco.
- **Normalização Determinística**: Limpeza reproduzível de caracteres de controle, desfazimento de quebras de linha e reconstituição de hifenizações espúrias de margem.
- **Desacoplamento Arquitetural**: Separação estrita entre o núcleo de extração/normalização e a interface de apresentação (CLI).

## Escopo Previsto do MVP

- Abertura segura e validação de PDFs com tratamento de restrições de permissão.
- Classificação automática de estratégia de extração (`NATIVE_TEXT` vs. `OCR_FALLBACK`) com opção de sobrescrita manual (`--force-ocr`).
- Extrator vetorial baseado em blocos espaciais e ordenação de coordenadas (PyMuPDF).
- Extrator óptico em memória com suporte a DPI configurável e Tesseract OCR.
- Módulo de normalização textual (remoção de hifens de margem, caracteres de controle e unificação de parágrafos).
- Reconstrutor semântico para Markdown (cabeçalhos hierárquicos, listas padronizadas e blocos de código cercados).
- Exportador duplo: Markdown canônico e HTML5 com CSS responsivo embutido.
- CLI com comandos de extração (`extract`) e diagnóstico de ambiente local (`info`).
- Cobertura de testes automatizados com `pytest` em cada módulo.

## Stack Prevista

- Python 3.10 ou superior.
- PyMuPDF (`fitz`) para parsing de PDF e renderização de buffers de imagem em memória.
- Tesseract OCR + `pytesseract` para extração óptica de caracteres.
- Python-Markdown para compilação HTML.
- `pytest` para testes unitários e de integração.

## Estrutura do Projeto

```text
pdf-to-markdown-converter/
├── pyproject.toml
├── README.md
├── src/
│   └── pdf_to_markdown_converter/
│       ├── __init__.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── line_normalizer.py
│       │   ├── pdf_reader.py
│       │   └── text_cleaner.py
│       └── domain/
│           ├── __init__.py
│           └── models.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_line_normalizer.py
    ├── test_models.py
    ├── test_pdf_reader.py
    ├── test_scaffold.py
    └── test_text_cleaner.py
```
