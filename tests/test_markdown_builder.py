import pytest

from pdf_to_markdown_converter.core.markdown_builder import (
    MarkdownBuilder,
    build_markdown,
    format_block,
    format_code_block,
    format_heading,
    format_list_item,
    format_paragraph,
    is_code_fenced,
)
from pdf_to_markdown_converter.domain.models import (
    BlockType,
    DocumentStructure,
    ExtractionStrategy,
    TextBlock,
)


def test_format_heading_levels() -> None:
    for level in range(1, 7):
        result = format_heading(f"Título de Nível {level}", heading_level=level)
        assert result == f"{'#' * level} Título de Nível {level}"


def test_format_heading_fallback_and_clamping() -> None:
    assert format_heading("Título Zero", heading_level=0) == "# Título Zero"
    assert format_heading("Título Negativo", heading_level=-2) == "# Título Negativo"
    assert format_heading("Título Sete", heading_level=7) == "###### Título Sete"
    assert format_heading("Título Dez", heading_level=10) == "###### Título Dez"


def test_format_heading_clean_existing_hashes() -> None:
    assert format_heading("# Título com Hash", heading_level=1) == "# Título com Hash"
    assert format_heading("### Título Triplo", heading_level=1) == "# Título Triplo"
    assert format_heading("# Título Simples", heading_level=3) == "### Título Simples"
    assert format_heading("##TítuloSemEspaco", heading_level=2) == "## TítuloSemEspaco"
    assert format_heading("###", heading_level=2) == "##"


def test_format_heading_multiline_normalization() -> None:
    multiline = "Título Principal\nSubtítulo na Linha Seguinte"
    result = format_heading(multiline, heading_level=1)
    assert result == "# Título Principal Subtítulo na Linha Seguinte"


def test_format_heading_empty_and_whitespace() -> None:
    assert format_heading("") == ""
    assert format_heading("   \n  \t ") == ""


def test_is_code_fenced() -> None:
    assert is_code_fenced("```python\nprint(1)\n```") is True
    assert is_code_fenced("~~~bash\necho ok\n~~~") is True
    assert is_code_fenced("print('hello')") is False
    assert is_code_fenced("```\nsingle line") is False
    assert is_code_fenced("") is False


def test_format_code_block_unfenced() -> None:
    raw_code = "def somar(a, b):\n    return a + b"
    expected = "```\ndef somar(a, b):\n    return a + b\n```"
    assert format_code_block(raw_code) == expected


def test_format_code_block_with_language() -> None:
    raw_code = "const x = 42;"
    expected = "```javascript\nconst x = 42;\n```"
    assert format_code_block(raw_code, default_language="javascript") == expected


def test_format_code_block_dedent() -> None:
    indented_code = "    def teste():\n        x = 10\n        return x"
    expected = "```python\ndef teste():\n    x = 10\n    return x\n```"
    assert format_code_block(indented_code, default_language="python") == expected


def test_format_code_block_already_fenced_prevents_nesting() -> None:
    fenced_backticks = "```python\nprint('sem nesting')\n```"
    assert format_code_block(fenced_backticks) == fenced_backticks

    fenced_tildes = "~~~json\n{\"chave\": \"valor\"}\n~~~"
    assert format_code_block(fenced_tildes) == fenced_tildes


def test_format_code_block_empty_and_whitespace() -> None:
    assert format_code_block("") == ""
    assert format_code_block("   \n \t ") == ""


def test_format_list_item_unordered_bullets() -> None:
    bullets = [
        "• Item com bullet tradicional",
        "◦ Item com circulo",
        "▪ Item com quadrado preto",
        "▫ Item com quadrado branco",
        "– Item com en-dash",
        "— Item com em-dash",
        "* Item com asterisco",
        "+ Item com mais",
        "- Item com traco",
    ]
    for bullet_text in bullets:
        formatted = format_list_item(bullet_text)
        assert formatted.startswith("- ")
        assert "Item com" in formatted


def test_format_list_item_nested_indentation() -> None:
    nested_text = (
        "• Item Raiz\n"
        "  • Subitem Nível 1\n"
        "    • Subitem Nível 2"
    )
    expected = (
        "- Item Raiz\n"
        "  - Subitem Nível 1\n"
        "    - Subitem Nível 2"
    )
    assert format_list_item(nested_text) == expected


def test_format_list_item_without_marker() -> None:
    text = "Item sem nenhum marcador explicito"
    assert format_list_item(text) == "- Item sem nenhum marcador explicito"


def test_format_list_item_multiline_block() -> None:
    block_text = (
        "* Primeira entrada\n"
        "+ Segunda entrada\n"
        "• Terceira entrada"
    )
    expected = (
        "- Primeira entrada\n"
        "- Segunda entrada\n"
        "- Terceira entrada"
    )
    assert format_list_item(block_text) == expected


def test_format_list_item_ordered_preserved() -> None:
    assert format_list_item("1. Passo um", preserve_ordered=True) == "1. Passo um"
    assert format_list_item("2) Passo dois", preserve_ordered=True) == "2. Passo dois"
    assert format_list_item("(3) Passo tres", preserve_ordered=True) == "3. Passo tres"
    assert format_list_item("a. Subitem alfabetico", preserve_ordered=True) == "a. Subitem alfabetico"


def test_format_list_item_ordered_standardized_to_dash() -> None:
    assert format_list_item("1. Passo um", preserve_ordered=False) == "- Passo um"
    assert format_list_item("2) Passo dois", preserve_ordered=False) == "- Passo dois"
    assert format_list_item("(3) Passo tres", preserve_ordered=False) == "- Passo tres"
    assert format_list_item("a. Subitem alfabetico", preserve_ordered=False) == "- Subitem alfabetico"


def test_format_list_item_continuation_lines() -> None:
    continuation_text = (
        "- Item com descricao longa\n"
        "  que continua na linha de baixo\n"
        "  com recuo alinhado."
    )
    expected = (
        "- Item com descricao longa\n"
        "  que continua na linha de baixo\n"
        "  com recuo alinhado."
    )
    assert format_list_item(continuation_text) == expected

    unindented_continuation = (
        "- Item com quebra sem recuo\n"
        "continuação na linha seguinte"
    )
    expected_indented = (
        "- Item com quebra sem recuo\n"
        "  continuação na linha seguinte"
    )
    assert format_list_item(unindented_continuation) == expected_indented


def test_format_list_item_empty_and_whitespace() -> None:
    assert format_list_item("") == ""
    assert format_list_item("   \n\t  ") == ""


def test_format_paragraph() -> None:
    text = "  Este e um paragrafo comum de teste.  "
    assert format_paragraph(text) == "Este e um paragrafo comum de teste."

    multiline = "Linha um do paragrafo.\nLinha dois do mesmo paragrafo."
    assert format_paragraph(multiline) == "Linha um do paragrafo.\nLinha dois do mesmo paragrafo."

    assert format_paragraph("") == ""
    assert format_paragraph("   \n \t ") == ""


def test_format_block_dispatch() -> None:
    heading_block = TextBlock(
        page_number=1,
        block_type=BlockType.HEADING,
        heading_level=2,
        normalized_text="1.1 Visão Geral",
    )
    assert format_block(heading_block) == "## 1.1 Visão Geral"

    code_block = TextBlock(
        page_number=1,
        block_type=BlockType.CODE_BLOCK,
        normalized_text="print('ola')",
    )
    assert format_block(code_block, default_code_language="python") == "```python\nprint('ola')\n```"

    list_block = TextBlock(
        page_number=1,
        block_type=BlockType.LIST_ITEM,
        normalized_text="• Elemento da lista",
    )
    assert format_block(list_block) == "- Elemento da lista"

    paragraph_block = TextBlock(
        page_number=1,
        block_type=BlockType.PARAGRAPH,
        normalized_text="Texto simples.",
    )
    assert format_block(paragraph_block) == "Texto simples."


def test_format_block_fallback_to_raw_text() -> None:
    block = TextBlock(
        page_number=1,
        block_type=BlockType.HEADING,
        heading_level=1,
        raw_text="Capítulo 1",
        normalized_text="",
    )
    assert format_block(block) == "# Capítulo 1"


def test_format_block_empty_content_returns_empty() -> None:
    block = TextBlock(page_number=1, raw_text="   ", normalized_text="")
    assert format_block(block) == ""


def test_build_markdown_sequence_of_blocks() -> None:
    blocks = [
        TextBlock(page_number=1, block_type=BlockType.HEADING, heading_level=1, normalized_text="Documento"),
        TextBlock(page_number=1, block_type=BlockType.PARAGRAPH, normalized_text="Parágrafo introdutório."),
        TextBlock(page_number=1, block_type=BlockType.LIST_ITEM, normalized_text="• Tópico 1\n• Tópico 2"),
        TextBlock(page_number=1, block_type=BlockType.CODE_BLOCK, normalized_text="x = 10"),
    ]
    md = build_markdown(blocks, default_code_language="python")
    expected = (
        "# Documento\n\n"
        "Parágrafo introdutório.\n\n"
        "- Tópico 1\n"
        "- Tópico 2\n\n"
        "```python\nx = 10\n```"
    )
    assert md == expected


def test_build_markdown_with_document_structure() -> None:
    blocks = [
        TextBlock(page_number=1, block_type=BlockType.HEADING, heading_level=2, normalized_text="Seção"),
        TextBlock(page_number=1, block_type=BlockType.PARAGRAPH, normalized_text="Conteúdo da seção."),
    ]
    doc = DocumentStructure(
        source_path="manual.pdf",
        total_pages=1,
        strategy=ExtractionStrategy.NATIVE_TEXT,
        blocks=blocks,
    )
    md = build_markdown(doc)
    assert md == "## Seção\n\nConteúdo da seção."


def test_build_markdown_empty_or_whitespace_omitted() -> None:
    blocks = [
        TextBlock(page_number=1, block_type=BlockType.PARAGRAPH, normalized_text=""),
        TextBlock(page_number=1, block_type=BlockType.HEADING, heading_level=1, normalized_text="Válido"),
        TextBlock(page_number=1, block_type=BlockType.PARAGRAPH, normalized_text="   \n "),
    ]
    md = build_markdown(blocks)
    assert md == "# Válido"

    assert build_markdown([]) == ""


def test_build_markdown_custom_separator() -> None:
    blocks = [
        TextBlock(page_number=1, block_type=BlockType.PARAGRAPH, normalized_text="Bloco A"),
        TextBlock(page_number=1, block_type=BlockType.PARAGRAPH, normalized_text="Bloco B"),
    ]
    md = build_markdown(blocks, separator="\n---\n")
    assert md == "Bloco A\n---\nBloco B"


def test_markdown_builder_class() -> None:
    builder = MarkdownBuilder(
        separator="\n\n",
        preserve_ordered_lists=True,
        default_code_language="python",
    )
    block = TextBlock(page_number=1, block_type=BlockType.CODE_BLOCK, normalized_text="return True")
    assert builder.format_block(block) == "```python\nreturn True\n```"

    blocks = [
        TextBlock(page_number=1, block_type=BlockType.HEADING, heading_level=1, normalized_text="Guia"),
        TextBlock(page_number=1, block_type=BlockType.PARAGRAPH, normalized_text="Texto."),
    ]
    assert builder.build_blocks(blocks) == "# Guia\n\nTexto."

    doc = DocumentStructure(
        source_path="teste.pdf",
        total_pages=1,
        strategy=ExtractionStrategy.NATIVE_TEXT,
        blocks=blocks,
    )
    assert builder.build_document(doc) == "# Guia\n\nTexto."
    assert builder.build(doc) == "# Guia\n\nTexto."
    assert builder.build(blocks) == "# Guia\n\nTexto."


def test_markdown_builder_class_standardize_ordered() -> None:
    builder = MarkdownBuilder(preserve_ordered_lists=False)
    block = TextBlock(page_number=1, block_type=BlockType.LIST_ITEM, normalized_text="1. Item ordenado")
    assert builder.format_block(block) == "- Item ordenado"
