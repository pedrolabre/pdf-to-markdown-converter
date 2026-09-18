from dataclasses import FrozenInstanceError

import pytest

from pdf_to_markdown_converter.domain import (
    BlockType,
    DocumentStructure,
    ExtractionResult,
    ExtractionStrategy,
    TextBlock,
)


def test_extraction_strategy_members() -> None:
    assert ExtractionStrategy.NATIVE_TEXT == "native_text"
    assert ExtractionStrategy.OCR_FALLBACK == "ocr_fallback"
    assert isinstance(ExtractionStrategy.NATIVE_TEXT, str)


def test_block_type_members() -> None:
    assert BlockType.PARAGRAPH == "paragraph"
    assert BlockType.HEADING == "heading"
    assert BlockType.CODE_BLOCK == "code_block"
    assert BlockType.LIST_ITEM == "list_item"
    assert isinstance(BlockType.PARAGRAPH, str)


def test_text_block_defaults() -> None:
    block = TextBlock(page_number=1)
    assert block.page_number == 1
    assert block.block_type == BlockType.PARAGRAPH
    assert block.raw_text == ""
    assert block.normalized_text == ""
    assert block.bbox == (0.0, 0.0, 0.0, 0.0)
    assert block.heading_level == 0


def test_text_block_custom_values() -> None:
    bbox = (72.0, 100.0, 500.0, 140.0)
    block = TextBlock(
        page_number=2,
        block_type=BlockType.HEADING,
        raw_text="Capítulo 1\n",
        normalized_text="Capítulo 1",
        bbox=bbox,
        heading_level=1,
    )
    assert block.page_number == 2
    assert block.block_type == BlockType.HEADING
    assert block.raw_text == "Capítulo 1\n"
    assert block.normalized_text == "Capítulo 1"
    assert block.bbox == bbox
    assert block.heading_level == 1


def test_text_block_immutability() -> None:
    block = TextBlock(page_number=1, raw_text="Texto")
    with pytest.raises(FrozenInstanceError):
        block.raw_text = "Novo Texto"  # type: ignore[misc]


def test_text_block_validations() -> None:
    with pytest.raises(ValueError, match="page_number must be greater than or equal to 1"):
        TextBlock(page_number=0)

    with pytest.raises(ValueError, match="heading_level must be between 0 and 6"):
        TextBlock(page_number=1, heading_level=-1)

    with pytest.raises(ValueError, match="heading_level must be between 0 and 6"):
        TextBlock(page_number=1, heading_level=7)

    with pytest.raises(ValueError, match="bbox must contain exactly 4 coordinates"):
        TextBlock(page_number=1, bbox=(0.0, 0.0, 10.0))  # type: ignore[arg-type]


def test_document_structure_instantiation() -> None:
    doc = DocumentStructure(
        source_path="documento.pdf",
        total_pages=5,
        strategy=ExtractionStrategy.NATIVE_TEXT,
    )
    assert doc.source_path == "documento.pdf"
    assert doc.total_pages == 5
    assert doc.strategy == ExtractionStrategy.NATIVE_TEXT
    assert doc.blocks == []


def test_document_structure_validations() -> None:
    with pytest.raises(ValueError, match="total_pages cannot be negative"):
        DocumentStructure(
            source_path="documento.pdf",
            total_pages=-1,
            strategy=ExtractionStrategy.NATIVE_TEXT,
        )


def test_document_structure_add_blocks() -> None:
    doc = DocumentStructure(
        source_path="doc.pdf",
        total_pages=1,
        strategy=ExtractionStrategy.NATIVE_TEXT,
    )
    block = TextBlock(page_number=1, raw_text="Primeiro bloco")
    doc.blocks.append(block)
    assert len(doc.blocks) == 1
    assert doc.blocks[0] == block


def test_document_structure_to_markdown_empty() -> None:
    doc = DocumentStructure(
        source_path="doc.pdf",
        total_pages=0,
        strategy=ExtractionStrategy.NATIVE_TEXT,
    )
    assert doc.to_markdown() == ""

    doc.blocks.append(TextBlock(page_number=1, raw_text="   "))
    assert doc.to_markdown() == ""


def test_document_structure_to_markdown_rendering() -> None:
    blocks = [
        TextBlock(
            page_number=1,
            block_type=BlockType.HEADING,
            heading_level=1,
            raw_text="Titulo Principal",
        ),
        TextBlock(
            page_number=1,
            block_type=BlockType.PARAGRAPH,
            raw_text="Primeiro paragrafo de explicacao.",
        ),
        TextBlock(
            page_number=1,
            block_type=BlockType.CODE_BLOCK,
            raw_text="print('ola mundo')",
        ),
        TextBlock(
            page_number=1,
            block_type=BlockType.LIST_ITEM,
            raw_text="Item da lista sem marcador",
        ),
        TextBlock(
            page_number=1,
            block_type=BlockType.LIST_ITEM,
            raw_text="- Item com marcador previo",
        ),
    ]
    doc = DocumentStructure(
        source_path="doc.pdf",
        total_pages=1,
        strategy=ExtractionStrategy.NATIVE_TEXT,
        blocks=blocks,
    )
    expected = (
        "# Titulo Principal\n\n"
        "Primeiro paragrafo de explicacao.\n\n"
        "```\nprint('ola mundo')\n```\n\n"
        "- Item da lista sem marcador\n\n"
        "- Item com marcador previo"
    )
    assert doc.to_markdown() == expected


def test_extraction_result_instantiation() -> None:
    result = ExtractionResult(
        source_path="doc.pdf",
        markdown_path="doc.md",
        html_path="doc.html",
        strategy_used=ExtractionStrategy.OCR_FALLBACK,
        pages_processed=10,
        execution_time_seconds=1.25,
    )
    assert result.source_path == "doc.pdf"
    assert result.markdown_path == "doc.md"
    assert result.html_path == "doc.html"
    assert result.strategy_used == ExtractionStrategy.OCR_FALLBACK
    assert result.pages_processed == 10
    assert result.execution_time_seconds == 1.25


def test_extraction_result_immutability() -> None:
    result = ExtractionResult(
        source_path="doc.pdf",
        markdown_path="doc.md",
        html_path="doc.html",
        strategy_used=ExtractionStrategy.NATIVE_TEXT,
        pages_processed=1,
        execution_time_seconds=0.5,
    )
    with pytest.raises(FrozenInstanceError):
        result.pages_processed = 2  # type: ignore[misc]


def test_extraction_result_validations() -> None:
    with pytest.raises(ValueError, match="pages_processed cannot be negative"):
        ExtractionResult(
            source_path="doc.pdf",
            markdown_path="doc.md",
            html_path="doc.html",
            strategy_used=ExtractionStrategy.NATIVE_TEXT,
            pages_processed=-1,
            execution_time_seconds=0.5,
        )

    with pytest.raises(ValueError, match="execution_time_seconds cannot be negative"):
        ExtractionResult(
            source_path="doc.pdf",
            markdown_path="doc.md",
            html_path="doc.html",
            strategy_used=ExtractionStrategy.NATIVE_TEXT,
            pages_processed=1,
            execution_time_seconds=-0.1,
        )
