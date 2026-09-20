from pdf_to_markdown_converter.core.block_classifier import (
    BlockClassifier,
    classify_block,
    classify_blocks,
    classify_document_structure,
    classify_text,
    detect_heading,
    infer_heading_level,
    is_code_block,
    is_heading,
    is_list_item,
)
from pdf_to_markdown_converter.domain.models import (
    BlockType,
    DocumentStructure,
    ExtractionStrategy,
    TextBlock,
)


def test_classify_empty_and_whitespace_text() -> None:
    block_type, level = classify_text("")
    assert block_type == BlockType.PARAGRAPH
    assert level == 0

    block_type, level = classify_text("   \n\t  ")
    assert block_type == BlockType.PARAGRAPH
    assert level == 0


def test_classify_explicit_markdown_headings() -> None:
    cases = [
        ("# Título Nível 1", 1),
        ("## Subtítulo Nível 2", 2),
        ("### Seção Nível 3", 3),
        ("#### Subseção Nível 4", 4),
        ("##### Detalhe Nível 5", 5),
        ("###### Mínimo Nível 6", 6),
        ("####### Título Além do Limite", 6),
    ]
    for text, expected_level in cases:
        assert is_heading(text) is True
        assert infer_heading_level(text) == expected_level
        b_type, level = classify_text(text)
        assert b_type == BlockType.HEADING
        assert level == expected_level


def test_classify_hierarchical_numbered_headings() -> None:
    cases = [
        ("1. Introdução Geral", 1),
        ("1.1 Contexto e Motivação", 2),
        ("1.1.1 Arquitetura do Sistema", 3),
        ("2.3.4.1 Especificação de Componentes", 4),
        ("2.3.4.1.2 Parâmetros Avançados", 5),
        ("2.3.4.1.2.3 Nível Máximo Suportado", 6),
        ("2.3.4.1.2.3.4 Nível Excedente Limitado", 6),
    ]
    for text, expected_level in cases:
        assert is_heading(text) is True
        b_type, level = classify_text(text)
        assert b_type == BlockType.HEADING
        assert level == expected_level


def test_classify_chapter_and_section_keywords() -> None:
    chapter_cases = [
        "Capítulo 1: Fundamentos",
        "Capitulo 2 - Metodologia",
        "Chapter 3: Architecture",
        "Parte 1: Visão Geral",
        "Part II: Detailed Design",
    ]
    for text in chapter_cases:
        assert is_heading(text) is True
        b_type, level = classify_text(text)
        assert b_type == BlockType.HEADING
        assert level == 1

    section_cases = [
        "Seção 2.1: Modelos de Domínio",
        "Secao 3: Utilitários Puros",
        "Section 4: Verification Plan",
        "Anexo A: Diagrama do Pipeline",
        "Apêndice B: Configuração do Tesseract",
        "Appendix C: Error Codes",
    ]
    for text in section_cases:
        assert is_heading(text) is True
        b_type, level = classify_text(text)
        assert b_type == BlockType.HEADING
        assert level == 2


def test_classify_all_caps_brevity_headings() -> None:
    uppercase_titles = [
        "SUMÁRIO",
        "INTRODUÇÃO",
        "ESTRUTURA DO PROJETO",
        "CONSIDERAÇÕES FINAIS",
        "REFERÊNCIAS BIBLIOGRÁFICAS",
        "REQUISITOS NÃO FUNCIONAIS",
    ]
    for text in uppercase_titles:
        assert is_heading(text) is True
        assert infer_heading_level(text) == 1
        b_type, level = classify_text(text)
        assert b_type == BlockType.HEADING
        assert level == 1


def test_all_caps_non_headings() -> None:
    non_headings = [
        "OK",
        "PDF",
        "ESTA É UMA FRASE COMPLETA EM CAIXA ALTA TERMINANDO COM PONTO.",
        "- ITEM EM CAIXA ALTA NA LISTA",
        "QUAL É O RESULTADO DA OPERAÇÃO?",
    ]
    for text in non_headings:
        is_hd, level = detect_heading(text)
        assert is_hd is False
        assert level == 0


def test_classify_fenced_code_blocks() -> None:
    backtick_block = "```python\ndef soma(a, b):\n    return a + b\n```"
    tilde_block = "~~~\nconst value = 42;\nconsole.log(value);\n~~~"

    assert is_code_block(backtick_block) is True
    assert is_code_block(tilde_block) is True

    b_type, level = classify_text(backtick_block)
    assert b_type == BlockType.CODE_BLOCK
    assert level == 0


def test_classify_indented_code_blocks() -> None:
    indented_spaces = "    x = 10\n    y = 20\n    print(x + y)"
    indented_tabs = "\tconst x = 1;\n\treturn x;"

    assert is_code_block(indented_spaces) is True
    assert is_code_block(indented_tabs) is True

    b_type, level = classify_text(indented_spaces)
    assert b_type == BlockType.CODE_BLOCK
    assert level == 0


def test_classify_programming_syntax_code_blocks() -> None:
    python_snippet = "import os\nfrom pathlib import Path\n\ndef run():\n    return 0"
    js_snippet = "function calculateTotal(items) {\n    return items.length;\n}"
    java_snippet = "public class Converter {\n    public static void main(String[] args) {}\n}"
    sql_snippet = "SELECT id, name, email FROM users"

    for snippet in [python_snippet, js_snippet, java_snippet, sql_snippet]:
        assert is_code_block(snippet) is True
        b_type, level = classify_text(snippet)
        assert b_type == BlockType.CODE_BLOCK
        assert level == 0


def test_classify_unordered_list_items() -> None:
    bullets = [
        "- Primeiro elemento da lista com hífen",
        "* Elemento com asterisco",
        "+ Elemento com sinal de mais",
        "• Marcador de ponto clássico",
        "◦ Marcador circular vazado",
        "▪ Marcador de quadrado preenchido",
        "▫ Marcador de quadrado vazado",
        "– Marcador traço curto",
        "— Marcador traço longo",
    ]
    for text in bullets:
        assert is_list_item(text) is True
        b_type, level = classify_text(text)
        assert b_type == BlockType.LIST_ITEM
        assert level == 0


def test_classify_ordered_list_items() -> None:
    ordered_items = [
        "1) Primeiro passo do procedimento",
        "(1) Alternativa numerada",
        "a) Primeira alínea alfabética",
        "b. Segunda alínea com ponto",
        "i) Numeral romano minúsculo",
        "IV) Numeral romano maiúsculo",
        "1. Compre leite e pão fresco na padaria da esquina.",
    ]
    for text in ordered_items:
        assert is_list_item(text) is True
        b_type, level = classify_text(text)
        assert b_type == BlockType.LIST_ITEM
        assert level == 0


def test_classify_multiline_list_block() -> None:
    multiline_list = "- Item alfa\n- Item beta\n- Item gama"
    assert is_list_item(multiline_list) is True
    b_type, level = classify_text(multiline_list)
    assert b_type == BlockType.LIST_ITEM
    assert level == 0


def test_classify_standard_paragraphs() -> None:
    paragraphs = [
        "Este é um parágrafo convencional de texto narrativo descrevendo a arquitetura.",
        "A taxa de crescimento foi de 2.5% ao ano conforme indicado pelos dados preliminares.",
        "Em 2026 foram realizados múltiplos testes unitários para garantir a confiabilidade.",
    ]
    for text in paragraphs:
        assert is_heading(text) is False
        assert is_list_item(text) is False
        assert is_code_block(text) is False
        b_type, level = classify_text(text)
        assert b_type == BlockType.PARAGRAPH
        assert level == 0


def test_classify_block_immutability_preservation() -> None:
    original = TextBlock(
        page_number=1,
        block_type=BlockType.PARAGRAPH,
        raw_text="1.1 Arquitetura de Software",
        normalized_text="1.1 Arquitetura de Software",
        bbox=(50.0, 100.0, 300.0, 120.0),
        heading_level=0,
    )

    classified = classify_block(original)

    assert original.block_type == BlockType.PARAGRAPH
    assert original.heading_level == 0

    assert classified.block_type == BlockType.HEADING
    assert classified.heading_level == 2
    assert classified.page_number == 1
    assert classified.raw_text == original.raw_text
    assert classified.normalized_text == original.normalized_text
    assert classified.bbox == original.bbox
    assert classified is not original


def test_classify_block_fallback_to_raw_text() -> None:
    block = TextBlock(
        page_number=2,
        raw_text="• Item de teste sem texto normalizado",
        normalized_text="",
    )
    classified = classify_block(block)
    assert classified.block_type == BlockType.LIST_ITEM
    assert classified.heading_level == 0


def test_classify_blocks_sequence() -> None:
    blocks = [
        TextBlock(page_number=1, normalized_text="1. Visão Geral"),
        TextBlock(page_number=1, normalized_text="Texto explicativo do sistema."),
        TextBlock(page_number=1, normalized_text="- Requisito funcional 1"),
        TextBlock(page_number=1, normalized_text="```python\nprint(1)\n```"),
    ]
    classified = classify_blocks(blocks)
    assert len(classified) == 4
    assert classified[0].block_type == BlockType.HEADING
    assert classified[0].heading_level == 1
    assert classified[1].block_type == BlockType.PARAGRAPH
    assert classified[2].block_type == BlockType.LIST_ITEM
    assert classified[3].block_type == BlockType.CODE_BLOCK


def test_classify_document_structure() -> None:
    doc = DocumentStructure(
        source_path="documento.pdf",
        total_pages=1,
        strategy=ExtractionStrategy.NATIVE_TEXT,
        blocks=[
            TextBlock(page_number=1, normalized_text="CAPÍTULO 1: INTRODUÇÃO"),
            TextBlock(page_number=1, normalized_text="Descrição do capítulo."),
        ],
    )
    classified_doc = classify_document_structure(doc)

    assert classified_doc.source_path == doc.source_path
    assert classified_doc.total_pages == doc.total_pages
    assert classified_doc.strategy == doc.strategy
    assert len(classified_doc.blocks) == 2
    assert classified_doc.blocks[0].block_type == BlockType.HEADING
    assert classified_doc.blocks[0].heading_level == 1
    assert classified_doc.blocks[1].block_type == BlockType.PARAGRAPH


def test_block_classifier_class() -> None:
    classifier = BlockClassifier(max_heading_length=120)
    block = TextBlock(page_number=1, normalized_text="1.1.1 Detalhe Técnico")
    classified = classifier.classify(block)
    assert classified.block_type == BlockType.HEADING
    assert classified.heading_level == 3

    blocks = [
        TextBlock(page_number=1, normalized_text="- Item 1"),
        TextBlock(page_number=1, normalized_text="Parágrafo final"),
    ]
    classified_list = classifier.classify_all(blocks)
    assert classified_list[0].block_type == BlockType.LIST_ITEM
    assert classified_list[1].block_type == BlockType.PARAGRAPH

    doc = DocumentStructure(
        source_path="doc.pdf",
        total_pages=1,
        strategy=ExtractionStrategy.NATIVE_TEXT,
        blocks=blocks,
    )
    classified_doc = classifier.classify_document(doc)
    assert len(classified_doc.blocks) == 2
    assert classified_doc.blocks[0].block_type == BlockType.LIST_ITEM


def test_heading_exceeding_max_length_becomes_paragraph() -> None:
    long_title = "1.1 " + "Palavra " * 30
    assert len(long_title) > 150
    block_type, level = classify_text(long_title, max_heading_length=150)
    assert block_type == BlockType.PARAGRAPH
    assert level == 0


def test_multiline_heading_rejection() -> None:
    multiline_heading = "1.1 Título\nCom muitas linhas adicionais\nQue descaracterizam cabeçalho"
    is_hd, level = detect_heading(multiline_heading)
    assert is_hd is False
    assert level == 0


def test_document_structure_to_markdown_with_classified_blocks() -> None:
    blocks = [
        TextBlock(page_number=1, normalized_text="1. INTRODUÇÃO"),
        TextBlock(page_number=1, normalized_text="Este é o primeiro parágrafo."),
        TextBlock(page_number=1, normalized_text="1.1 Arquitetura"),
        TextBlock(page_number=1, normalized_text="- Camada de domínio\n- Camada core"),
        TextBlock(page_number=1, normalized_text="def test():\n    return True"),
    ]
    classified_blocks = classify_blocks(blocks)
    doc = DocumentStructure(
        source_path="test.pdf",
        total_pages=1,
        strategy=ExtractionStrategy.NATIVE_TEXT,
        blocks=classified_blocks,
    )
    md = doc.to_markdown()

    assert "# 1. INTRODUÇÃO" in md
    assert "Este é o primeiro parágrafo." in md
    assert "## 1.1 Arquitetura" in md
    assert "- Camada de domínio\n- Camada core" in md
    assert "```\ndef test():\n    return True\n```" in md
