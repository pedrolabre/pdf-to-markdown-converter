# PDF to Markdown Converter

O **PDF to Markdown Converter** é uma ferramenta local-first desenvolvida em Python para converter documentos PDF em arquivos Markdown estruturados e semanticamente ricos, com compilação direta para HTML5.

A ferramenta implementa uma esteira híbrida com análise de qualidade: extrai texto vetorial diretamente quando a camada textual é íntegra e aplica fallback transparente para OCR em memória quando o documento é escaneado, protegido ou possui codificações corrompidas.

A ferramenta fornece uma esteira de processamento completa que opera de forma desacoplada via interface gráfica intuitiva (`pdf-to-markdown-gui` ou `pdf-to-markdown gui`), interface de linha de comando (`pdf-to-markdown`) ou importação programática em Python.

## Objetivo

Converter arquivos PDF em documentos Markdown (`.md`) canônicos e páginas HTML5 (`.html`), garantindo fidelidade estrutural (títulos, listas, blocos de código e parágrafos contínuos) sem dependência de serviços remotos, nuvem ou modelos externos.

## Premissas Técnicas

- **Local-First**: Execução 100% local, garantindo privacidade e segurança total dos documentos processados.
- **Zero I/O Temporário no OCR**: Processamento de imagens estritamente em memória RAM através de streams e buffers de bytes, sem criação de arquivos temporários em disco.
- **Normalização Determinística**: Limpeza reproduzível de caracteres de controle, desfazimento de quebras de linha e reconstituição de hifenizações espúrias de margem.
- **Desacoplamento Arquitetural**: Separação estrita entre o núcleo de extração/normalização, a interface gráfica (GUI) e a interface de linha de comando (CLI).

## Recursos Principais

- Interface gráfica nativa (GUI) com seleção de arquivo PDF, preenchimento automático de destino, barra de progresso em tempo real e abertura direta dos arquivos gerados.
- Acompanhamento contínuo e granular de progresso página a página, refletido dinamicamente na interface gráfica (GUI) e no terminal interativo (CLI).
- Abertura segura e validação de PDFs com tratamento de restrições de permissão e autenticação de senhas.
- Classificação automática de estratégia de extração (`NATIVE_TEXT` vs. `OCR_FALLBACK`) com opção de sobrescrita manual (`--force-ocr`).
- Extrator vetorial baseado em blocos espaciais e ordenação de coordenadas (PyMuPDF) com suporte nativo à extração de tabelas (`page.find_tables()`).
- Extrator óptico em memória RAM com suporte a DPI configurável e Tesseract OCR.
- Módulo de normalização textual (remoção de hifens de margem, caracteres de controle e unificação de parágrafos).
- Reconstrutor semântico para Markdown (cabeçalhos hierárquicos, listas padronizadas, blocos de código cercados e tabelas sintéticas canônicas).
- Exportador duplo atômico: Markdown canônico e HTML5 com CSS responsivo embutido e suporte a modo escuro.
- CLI com subcomandos de extração (`extract`), alias implícito direto, lançamento da interface gráfica (`gui`) e diagnóstico de ambiente local (`info`).
- Cobertura de testes automatizados com `pytest` em cada módulo e suíte integrada ponta a ponta (E2E).

## Stack Tecnológica

- Python 3.10 ou superior.
- PyMuPDF (`fitz`) para parsing de PDF e renderização de buffers de imagem em memória.
- Tesseract OCR + `pytesseract` para extração óptica de caracteres.
- Python-Markdown para compilação HTML.
- `pytest` para testes unitários e de integração.

## Instalação

### 1. Clonar o Repositório e Criar Ambiente Virtual

```bash
git clone https://github.com/pedrolabre/pdf-to-markdown-converter.git
cd pdf-to-markdown-converter

python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Linux / macOS
source .venv/bin/activate
```

### 2. Instalar Dependências do Pacote

```bash
# Instalação em modo editável com dependências de desenvolvimento e testes
pip install -e ".[dev]"
```

### 3. Motor Tesseract OCR (Opcional, para Fallback Óptico)

Caso deseje processar documentos digitalizados (scans ou imagens sem camada vetorial):

- **Windows**: `winget install UB-Mannheim.TesseractOCR`
- **Ubuntu/Debian**: `sudo apt-get install tesseract-ocr tesseract-ocr-por`
- **macOS**: `brew install tesseract tesseract-lang`

Para verificar se o Tesseract foi detectado corretamente pelo ambiente:

```bash
pdf-to-markdown info
```

## Uso da Interface Gráfica (GUI)

Para quem prefere uma experiência visual intuitiva, a ferramenta inclui uma interface gráfica nativa em Tkinter/TTK (leve e sem dependências adicionais).

### Inicialização da GUI

Você pode iniciar a interface gráfica por qualquer uma das opções abaixo:

```bash
# 1. Pelo executável de console dedicado:
pdf-to-markdown-gui

# 2. Pelo subcomando da CLI:
pdf-to-markdown gui

# 3. Como módulo Python direto:
python -m pdf_to_markdown_converter.gui
```

### Funcionalidades da Interface

- **Seleção de Arquivo e Destino**: Botão "Procurar..." para selecionar o arquivo PDF via explorador nativo. Ao selecionar o arquivo, a pasta de destino é automaticamente definida para a mesma pasta do PDF de origem.
- **Opções de Exportação**: Checkboxes para escolher gerar Markdown (`.md`), HTML5 (`.html`) ou ambos, além de controle de sobrescrita.
- **Configurações de OCR e Senha**: Opção para forçar OCR (em casos de documentos escaneados), idiomas do motor e campo de senha para PDFs protegidos.
- **Progresso em Tempo Real**: Barra de progresso e rótulos de status assíncronos atualizados a cada etapa da conversão sem travar a janela.
- **Ações Imediatas pós-conversão**: Botões para abrir a pasta de destino e visualizar diretamente os arquivos Markdown e HTML gerados.

## Uso da CLI

Após a instalação, o executável `pdf-to-markdown` estará disponível no ambiente virtual.

### 1. Diagnóstico do Ambiente (`info`)

Verifica a prontidão das bibliotecas e o status do motor Tesseract:

```bash
# Diagnóstico visual formatado no terminal
pdf-to-markdown info

# Diagnóstico em formato JSON estruturado (para scripts/automações)
pdf-to-markdown info --json
```

### 2. Conversão de Documentos (`extract`)

#### Conversão Básica (Markdown + HTML5)
Por padrão, a ferramenta gera simultaneamente o arquivo `.md` e o `.html` na mesma pasta do documento:

```bash
pdf-to-markdown extract documento.pdf

# Ou utilizando o alias simplificado direto:
pdf-to-markdown documento.pdf
```

#### Especificar Diretório ou Arquivo de Saída
```bash
# Destino em diretório específico
pdf-to-markdown extract documento.pdf -o ./dist

# Destino com caminho e nome de arquivo customizado
pdf-to-markdown extract documento.pdf --output-path ./relatorios/resultado.md
```

#### Seleção Específica de Formato
```bash
# Exportar exclusivamente Markdown
pdf-to-markdown extract documento.pdf --format md

# Exportar exclusivamente HTML5
pdf-to-markdown extract documento.pdf --format html
```

#### Forçar Extração Óptica via OCR
```bash
# Força o motor OCR com resolução e idiomas configurados
pdf-to-markdown extract documento.pdf --force-ocr --dpi 300 --lang por+eng
```

#### Documento Protegido por Senha
```bash
pdf-to-markdown extract documento.pdf --password "senha_de_acesso"
```

#### Proteção Contra Sobrescrita e Modo Silencioso
```bash
# Bloqueia sobrescrita caso os arquivos de destino já existam
pdf-to-markdown extract documento.pdf --no-overwrite

# Execução em modo silencioso (suprime barras de progresso e resumos)
pdf-to-markdown extract documento.pdf -q
```

## Execução de Testes

A suíte de testes abrange testes unitários, modulares e de ponta a ponta (E2E):

```bash
# Executa toda a suíte de testes automatizados
python -m pytest

# Executa com saída detalhada
python -m pytest -v
```

## Estrutura do Projeto

```text
pdf-to-markdown-converter/
├── pyproject.toml
├── README.md
├── src/
│   └── pdf_to_markdown_converter/
│       ├── __init__.py
│       ├── cli/
│       │   ├── __init__.py
│       │   ├── info.py
│       │   └── main.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── block_classifier.py
│       │   ├── detector.py
│       │   ├── line_normalizer.py
│       │   ├── link_extractor.py
│       │   ├── markdown_builder.py
│       │   ├── native_extractor.py
│       │   ├── ocr_extractor.py
│       │   ├── pdf_reader.py
│       │   ├── pipeline.py
│       │   ├── tesseract_env.py
│       │   └── text_cleaner.py
│       ├── domain/
│       │   ├── __init__.py
│       │   └── models.py
│       ├── exporters/
│       │   ├── __init__.py
│       │   ├── html_exporter.py
│       │   ├── markdown_exporter.py
│       │   └── styles.py
│       └── gui/
│           ├── __init__.py
│           ├── __main__.py
│           └── app.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_block_classifier.py
    ├── test_cli_info.py
    ├── test_cli_main.py
    ├── test_detector.py
    ├── test_e2e.py
    ├── test_gui.py
    ├── test_html_exporter.py
    ├── test_line_normalizer.py
    ├── test_link_extractor.py
    ├── test_markdown_builder.py
    ├── test_markdown_exporter.py
    ├── test_models.py
    ├── test_native_extractor.py
    ├── test_ocr_extractor.py
    ├── test_pdf_reader.py
    ├── test_pipeline.py
    ├── test_scaffold.py
    ├── test_styles.py
    ├── test_tesseract_env.py
    └── test_text_cleaner.py
```
