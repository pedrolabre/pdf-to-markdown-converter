from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image
import pymupdf
import pytest

from pdf_to_markdown_converter.core.ocr_extractor import (
    DEFAULT_DPI,
    OcrExtractor,
    build_tesseract_config,
    extract_document_structure_ocr,
    extract_page_blocks_ocr,
    extract_page_text_ocr,
    parse_ocr_data_to_blocks,
    parse_ocr_text_to_blocks,
    render_page_to_bytes,
    render_page_to_image,
)
from pdf_to_markdown_converter.core.tesseract_env import (
    TesseractNotFoundError,
    get_tesseract_diagnostics,
)
from pdf_to_markdown_converter.domain.models import (
    BlockType,
    DocumentStructure,
    ExtractionStrategy,
    TextBlock,
)


@pytest.fixture
def sample_pdf_doc() -> pymupdf.Document:
    doc = pymupdf.open()
    page1 = doc.new_page(width=500, height=700)
    page1.insert_text((50, 100), "Pagina 1 Linha 1")
    page1.insert_text((50, 150), "Pagina 1 Linha 2")
    page2 = doc.new_page(width=500, height=700)
    page2.insert_text((50, 100), "Pagina 2 Conteudo")
    return doc


def test_render_page_to_bytes(sample_pdf_doc: pymupdf.Document) -> None:
    page = sample_pdf_doc[0]
    png_bytes = render_page_to_bytes(page, dpi=150)
    assert isinstance(png_bytes, bytes)
    assert len(png_bytes) > 0
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")


def test_render_page_to_image(sample_pdf_doc: pymupdf.Document) -> None:
    page = sample_pdf_doc[0]
    img = render_page_to_image(page, dpi=72)
    assert isinstance(img, Image.Image)
    assert img.width == 500
    assert img.height == 700


def test_render_page_custom_dpi(sample_pdf_doc: pymupdf.Document) -> None:
    page = sample_pdf_doc[0]
    img_72 = render_page_to_image(page, dpi=72)
    img_144 = render_page_to_image(page, dpi=144)
    assert img_144.width == img_72.width * 2
    assert img_144.height == img_72.height * 2


def test_build_tesseract_config() -> None:
    assert build_tesseract_config(psm=3, oem=3) == "--psm 3 --oem 3"
    assert build_tesseract_config(psm=6, oem=1) == "--psm 6 --oem 1"
    assert build_tesseract_config(psm=None, oem=None) == ""
    cfg = build_tesseract_config(psm=3, oem=3, extra_config="-c test=1")
    assert cfg == "--psm 3 --oem 3 -c test=1"


def test_parse_ocr_data_to_blocks_with_words() -> None:
    data = {
        "text": ["", "Primeira", "linha", "", "Segunda", "linha"],
        "block_num": [0, 1, 1, 0, 2, 2],
        "par_num": [0, 1, 1, 0, 1, 1],
        "line_num": [0, 1, 1, 0, 1, 1],
        "left": [0, 72, 180, 0, 72, 190],
        "top": [0, 100, 100, 0, 200, 200],
        "width": [0, 100, 100, 0, 110, 100],
        "height": [0, 20, 20, 0, 20, 20],
        "conf": [-1, 95, 92, -1, 90, 88],
    }
    blocks = parse_ocr_data_to_blocks(data, page_number=1, scale=1.0)
    assert len(blocks) == 2
    assert blocks[0].raw_text == "Primeira linha"
    assert blocks[0].normalized_text == "Primeira linha"
    assert blocks[0].bbox == (72.0, 100.0, 280.0, 120.0)
    assert blocks[1].raw_text == "Segunda linha"


def test_parse_ocr_data_to_blocks_empty() -> None:
    assert parse_ocr_data_to_blocks({}, page_number=1) == []
    assert parse_ocr_data_to_blocks({"text": ["", "  "]}, page_number=1) == []
    data_filtered = {"text": ["token"], "conf": [-1]}
    assert parse_ocr_data_to_blocks(data_filtered, page_number=1) == []


def test_parse_ocr_data_multiline_normalization() -> None:
    data = {
        "text": ["Palavra-", "chave", "continua."],
        "block_num": [1, 1, 1],
        "par_num": [1, 1, 1],
        "line_num": [1, 2, 2],
        "left": [50, 50, 120],
        "top": [50, 80, 80],
        "width": [80, 60, 80],
        "height": [20, 20, 20],
        "conf": [95, 95, 95],
    }
    blocks = parse_ocr_data_to_blocks(data, page_number=1, scale=2.0)
    assert len(blocks) == 1
    assert "Palavra-" in blocks[0].raw_text
    assert blocks[0].bbox == (25.0, 25.0, 100.0, 50.0)


def test_parse_ocr_text_to_blocks() -> None:
    text = "Primeiro paragrafo.\n\nSegundo paragrafo com quebra\nde linha."
    blocks = parse_ocr_text_to_blocks(text, page_number=2, bbox=(10.0, 10.0, 400.0, 600.0))
    assert len(blocks) == 2
    assert blocks[0].page_number == 2
    assert blocks[0].raw_text == "Primeiro paragrafo."
    assert blocks[1].normalized_text == "Segundo paragrafo com quebra de linha."


@patch("pdf_to_markdown_converter.core.ocr_extractor.pytesseract.image_to_data")
def test_extract_page_blocks_ocr_use_data(mock_data: MagicMock, sample_pdf_doc: pymupdf.Document) -> None:
    mock_data.return_value = {
        "text": ["Texto", "reconhecido"],
        "block_num": [1, 1],
        "par_num": [1, 1],
        "line_num": [1, 1],
        "left": [10, 80],
        "top": [10, 10],
        "width": [60, 90],
        "height": [20, 20],
        "conf": [95, 95],
    }
    blocks = extract_page_blocks_ocr(sample_pdf_doc[0], check_environment=False, use_data=True)
    assert len(blocks) == 1
    assert blocks[0].normalized_text == "Texto reconhecido"
    assert mock_data.called


@patch("pdf_to_markdown_converter.core.ocr_extractor.pytesseract.image_to_string")
def test_extract_page_blocks_ocr_fallback_text(mock_str: MagicMock, sample_pdf_doc: pymupdf.Document) -> None:
    mock_str.return_value = "Bloco fallback 1\n\nBloco fallback 2"
    blocks = extract_page_blocks_ocr(sample_pdf_doc[0], check_environment=False, use_data=False)
    assert len(blocks) == 2
    assert blocks[0].normalized_text == "Bloco fallback 1"
    assert blocks[1].normalized_text == "Bloco fallback 2"


@patch("pdf_to_markdown_converter.core.ocr_extractor.pytesseract.image_to_string")
def test_extract_page_text_ocr(mock_str: MagicMock, sample_pdf_doc: pymupdf.Document) -> None:
    mock_str.return_value = "Texto corrido da pagina"
    res = extract_page_text_ocr(sample_pdf_doc[0], check_environment=False)
    assert res == "Texto corrido da pagina"


@patch("pdf_to_markdown_converter.core.ocr_extractor.extract_page_blocks_ocr")
def test_extract_document_structure_ocr_multi_page(mock_page: MagicMock, sample_pdf_doc: pymupdf.Document) -> None:
    b1 = TextBlock(1, BlockType.PARAGRAPH, "P1", "P1", (0.0, 0.0, 10.0, 10.0), 0)
    b2 = TextBlock(2, BlockType.PARAGRAPH, "P2", "P2", (0.0, 0.0, 10.0, 10.0), 0)
    mock_page.side_effect = [[b1], [b2]]

    doc_struct = extract_document_structure_ocr(sample_pdf_doc, check_environment=False)
    assert isinstance(doc_struct, DocumentStructure)
    assert doc_struct.total_pages == 2
    assert doc_struct.strategy == ExtractionStrategy.OCR_FALLBACK
    assert len(doc_struct.blocks) == 2
    assert doc_struct.blocks[0].raw_text == "P1"
    assert doc_struct.blocks[1].raw_text == "P2"


@patch("pdf_to_markdown_converter.core.ocr_extractor.extract_page_blocks_ocr")
def test_extract_document_structure_ocr_from_bytes(mock_page: MagicMock, sample_pdf_doc: pymupdf.Document) -> None:
    mock_page.return_value = [TextBlock(1, BlockType.PARAGRAPH, "Bytes text", "Bytes text", (0, 0, 1, 1), 0)]
    pdf_bytes = sample_pdf_doc.tobytes()
    res = extract_document_structure_ocr(pdf_bytes, check_environment=False)
    assert res.total_pages == 2
    assert res.source_path == "<memory>"
    assert res.strategy == ExtractionStrategy.OCR_FALLBACK


@patch("pdf_to_markdown_converter.core.ocr_extractor.ensure_tesseract_available")
def test_missing_tesseract_raises_error(mock_ensure: MagicMock, sample_pdf_doc: pymupdf.Document) -> None:
    mock_ensure.side_effect = TesseractNotFoundError("Tesseract nao encontrado")
    with pytest.raises(TesseractNotFoundError):
        extract_page_blocks_ocr(sample_pdf_doc[0], check_environment=True)


@patch("pdf_to_markdown_converter.core.ocr_extractor.pytesseract.image_to_data")
def test_ocr_extractor_class(mock_data: MagicMock, sample_pdf_doc: pymupdf.Document) -> None:
    mock_data.return_value = {
        "text": ["Classe", "OCR"],
        "block_num": [1, 1],
        "par_num": [1, 1],
        "line_num": [1, 1],
        "left": [0, 50],
        "top": [0, 0],
        "width": [40, 50],
        "height": [20, 20],
        "conf": [95, 95],
    }
    extractor = OcrExtractor(dpi=150, lang="por", check_environment=False)
    assert extractor.dpi == 150
    assert extractor.lang == "por"

    img_bytes = extractor.render_page(sample_pdf_doc[0])
    assert img_bytes.startswith(b"\x89PNG")

    page_blocks = extractor.extract_page(sample_pdf_doc[0])
    assert len(page_blocks) == 1
    assert page_blocks[0].normalized_text == "Classe OCR"

    with patch("pdf_to_markdown_converter.core.ocr_extractor.pytesseract.image_to_string") as mock_str:
        mock_str.return_value = "Texto de teste"
        assert extractor.extract_page_text(sample_pdf_doc[0]) == "Texto de teste"

    doc_struct = extractor.extract(sample_pdf_doc)
    assert doc_struct.strategy == ExtractionStrategy.OCR_FALLBACK
    assert doc_struct.total_pages == 2


def test_no_disk_files_created(tmp_path: Path, sample_pdf_doc: pymupdf.Document) -> None:
    initial_files = set(tmp_path.glob("**/*"))
    page = sample_pdf_doc[0]
    _ = render_page_to_bytes(page)
    _ = render_page_to_image(page)
    final_files = set(tmp_path.glob("**/*"))
    assert initial_files == final_files


def test_real_smoke_if_tesseract_available(sample_pdf_doc: pymupdf.Document) -> None:
    diag = get_tesseract_diagnostics()
    if not diag.is_available:
        pytest.skip("Tesseract OCR nao instalado neste ambiente.")
    if not (diag.has_language("eng") or diag.has_language("por")):
        pytest.skip("Pacotes de idiomas 'eng' ou 'por' ausentes.")

    blocks = extract_page_blocks_ocr(sample_pdf_doc[0], lang=diag.available_languages[0], check_environment=True)
    assert isinstance(blocks, list)
