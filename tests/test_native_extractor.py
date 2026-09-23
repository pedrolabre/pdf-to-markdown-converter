from pathlib import Path
import io
import pymupdf
import pytest

from pdf_to_markdown_converter.core.native_extractor import (
    DEFAULT_X_TOLERANCE,
    DEFAULT_Y_TOLERANCE,
    NativeExtractor,
    extract_document_structure,
    extract_page_blocks,
    sort_blocks_spatially,
)
from pdf_to_markdown_converter.domain.models import (
    BlockType,
    DocumentStructure,
    ExtractionStrategy,
    TextBlock,
)


def _make_block(
    text: str,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    page: int = 1,
) -> TextBlock:
    return TextBlock(
        page_number=page,
        block_type=BlockType.PARAGRAPH,
        raw_text=text,
        normalized_text=text,
        bbox=(x0, y0, x1, y1),
    )


def test_sort_blocks_spatially_empty_and_single() -> None:
    assert sort_blocks_spatially([]) == []
    single = _make_block("One", 10.0, 10.0, 50.0, 20.0)
    assert sort_blocks_spatially([single]) == [single]


def test_sort_blocks_spatially_single_column() -> None:
    b1 = _make_block("P1", 50.0, 100.0, 500.0, 150.0)
    b2 = _make_block("P2", 50.0, 170.0, 500.0, 220.0)
    b3 = _make_block("P3", 50.0, 240.0, 500.0, 290.0)
    assert sort_blocks_spatially([b3, b1, b2]) == [b1, b2, b3]


def test_sort_blocks_spatially_two_columns_staggered() -> None:
    c1_1 = _make_block("C1_1", 50.0, 100.0, 240.0, 180.0)
    c1_2 = _make_block("C1_2", 50.0, 190.0, 240.0, 300.0)
    c1_3 = _make_block("C1_3", 50.0, 310.0, 240.0, 420.0)
    c2_1 = _make_block("C2_1", 280.0, 100.0, 480.0, 220.0)
    c2_2 = _make_block("C2_2", 280.0, 230.0, 480.0, 370.0)

    blocks = [c2_1, c1_2, c2_2, c1_1, c1_3]
    assert sort_blocks_spatially(blocks) == [c1_1, c1_2, c1_3, c2_1, c2_2]


def test_sort_blocks_spatially_three_columns() -> None:
    col1 = _make_block("C1", 40.0, 100.0, 180.0, 300.0)
    col2 = _make_block("C2", 200.0, 100.0, 340.0, 300.0)
    col3 = _make_block("C3", 360.0, 100.0, 500.0, 300.0)
    assert sort_blocks_spatially([col3, col1, col2]) == [col1, col2, col3]


def test_sort_blocks_spatially_header_columns_footer() -> None:
    header = _make_block("Header", 50.0, 40.0, 550.0, 80.0)
    col1_1 = _make_block("Col1_P1", 50.0, 100.0, 270.0, 160.0)
    col1_2 = _make_block("Col1_P2", 50.0, 180.0, 270.0, 240.0)
    col2_1 = _make_block("Col2_P1", 300.0, 100.0, 520.0, 170.0)
    col2_2 = _make_block("Col2_P2", 300.0, 190.0, 520.0, 250.0)
    footer = _make_block("Footer", 50.0, 700.0, 550.0, 730.0)

    blocks = [footer, col2_2, header, col1_2, col2_1, col1_1]
    assert sort_blocks_spatially(blocks) == [header, col1_1, col1_2, col2_1, col2_2, footer]


def test_sort_blocks_spatially_side_by_side_and_tolerance() -> None:
    left = _make_block("Left", 50.0, 100.0, 200.0, 120.0)
    right = _make_block("Right", 350.0, 101.5, 500.0, 121.5)
    body = _make_block("Body", 50.0, 150.0, 500.0, 200.0)
    assert sort_blocks_spatially([body, right, left]) == [left, right, body]
    assert len(sort_blocks_spatially([left, right], y_tolerance=0.0)) == 2


@pytest.fixture
def synthetic_page() -> pymupdf.Page:
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text((50, 60), "Titulo do Documento", fontsize=16)
    page.insert_text((50, 120), "Primeiro paragrafo con- \n tinuo e limpo.", fontsize=11)
    page.insert_text((320, 120), "Coluna da direita.", fontsize=11)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 50, 50), 1)
    page.insert_image(pymupdf.Rect(400, 600, 450, 650), pixmap=pix)
    return page


def test_extract_page_blocks_basic(synthetic_page: pymupdf.Page) -> None:
    blocks = extract_page_blocks(synthetic_page, page_number=1)
    assert len(blocks) == 3
    assert blocks[0].raw_text.strip() == "Titulo do Documento"
    assert blocks[1].normalized_text == "Primeiro paragrafo continuo e limpo."
    assert blocks[2].raw_text.strip() == "Coluna da direita."
    assert all(b.page_number == 1 for b in blocks)
    assert all(b.block_type == BlockType.PARAGRAPH for b in blocks)
    assert all(len(b.bbox) == 4 for b in blocks)


def test_extract_page_blocks_options(synthetic_page: pymupdf.Page) -> None:
    raw_norm = extract_page_blocks(synthetic_page, normalize=False)
    assert "con- \n tinuo" in raw_norm[1].normalized_text

    nosort = extract_page_blocks(synthetic_page, sort_spatial=False)
    assert len(nosort) == 3


def test_extract_document_structure_multipage(tmp_path: Path) -> None:
    doc = pymupdf.open()
    p1 = doc.new_page(width=500, height=700)
    p1.insert_text((50, 50), "Pagina 1")
    p2 = doc.new_page(width=500, height=700)
    p2.insert_text((50, 50), "Pagina 2")
    pdf_path = tmp_path / "sample.pdf"
    doc.save(str(pdf_path))
    doc.close()

    result = extract_document_structure(pdf_path)
    assert isinstance(result, DocumentStructure)
    assert result.total_pages == 2
    assert result.strategy == ExtractionStrategy.NATIVE_TEXT
    assert len(result.blocks) == 2
    assert result.blocks[0].page_number == 1
    assert result.blocks[1].page_number == 2
    assert result.blocks[0].normalized_text == "Pagina 1"
    assert result.blocks[1].normalized_text == "Pagina 2"
    assert "Pagina 1\n\nPagina 2" in result.to_markdown()


def test_extract_document_structure_sources(tmp_path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Conteudo de Teste")
    data = doc.tobytes()
    pdf_path = tmp_path / "sources.pdf"
    pdf_path.write_bytes(data)

    res_doc = extract_document_structure(doc)
    assert len(res_doc.blocks) == 1
    doc.close()

    res_path = extract_document_structure(pdf_path)
    assert res_path.source_path == str(pdf_path)

    res_str = extract_document_structure(str(pdf_path))
    assert res_str.source_path == str(pdf_path)

    res_bytes = extract_document_structure(data)
    assert res_bytes.source_path == "<memory>"
    assert len(res_bytes.blocks) == 1


def test_extract_document_structure_encrypted(tmp_path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Texto Secreto")
    enc_path = tmp_path / "secret.pdf"
    doc.save(
        str(enc_path),
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        user_pw="senha123",
        owner_pw="master123",
    )
    doc.close()

    res = extract_document_structure(enc_path, password="senha123")
    assert len(res.blocks) == 1
    assert res.blocks[0].normalized_text == "Texto Secreto"


def test_native_extractor_class(tmp_path: Path) -> None:
    extractor = NativeExtractor(
        y_tolerance=4.0,
        x_tolerance=4.0,
        sort_spatial=True,
        normalize=True,
        ignore_empty=True,
    )
    assert extractor.y_tolerance == 4.0
    assert extractor.x_tolerance == 4.0

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Classe Extratora")

    page_blocks = extractor.extract_page(page)
    assert len(page_blocks) == 1
    assert page_blocks[0].normalized_text == "Classe Extratora"

    doc_struct = extractor.extract(doc)
    assert doc_struct.total_pages == 1
    assert len(doc_struct.blocks) == 1
    doc.close()


def test_sort_blocks_spatially_multi_column_pruning() -> None:
    # Cria grade com 20 blocos em 2 colunas verticais desordenadas
    col1 = [_make_block(f"C1_{i}", 50.0, 100.0 + i * 40.0, 250.0, 130.0 + i * 40.0) for i in range(10)]
    col2 = [_make_block(f"C2_{i}", 300.0, 100.0 + i * 40.0, 500.0, 130.0 + i * 40.0) for i in range(10)]
    header = _make_block("Header", 50.0, 30.0, 500.0, 70.0)
    footer = _make_block("Footer", 50.0, 550.0, 500.0, 590.0)

    # Embaralha os blocos intencionalmente
    shuffled = [footer] + col2[5:] + col1[3:7] + [header] + col1[:3] + col2[:5] + col1[7:]
    sorted_blocks = sort_blocks_spatially(shuffled)

    assert len(sorted_blocks) == 22
    assert sorted_blocks[0].raw_text == "Header"
    assert [b.raw_text for b in sorted_blocks[1:11]] == [f"C1_{i}" for i in range(10)]
    assert [b.raw_text for b in sorted_blocks[11:21]] == [f"C2_{i}" for i in range(10)]
    assert sorted_blocks[21].raw_text == "Footer"


def test_extract_page_blocks_with_table() -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text((50, 40), "Titulo do Relatorio")
    # Linhas de grade da tabela
    page.draw_line([50, 100], [450, 100])
    page.draw_line([50, 130], [450, 130])
    page.draw_line([50, 160], [450, 160])
    page.draw_line([50, 100], [50, 160])
    page.draw_line([250, 100], [250, 160])
    page.draw_line([450, 100], [450, 160])
    page.insert_text((70, 120), "Item")
    page.insert_text((270, 120), "Preco")
    page.insert_text((70, 150), "Notebook")
    page.insert_text((270, 150), "3500.00")
    page.insert_text((50, 200), "Observacoes finais.")

    blocks = extract_page_blocks(page)
    table_blocks = [b for b in blocks if b.block_type == BlockType.TABLE]
    assert len(table_blocks) == 1
    assert "Item" in table_blocks[0].raw_text
    assert "Notebook" in table_blocks[0].raw_text

    # Verifica que as celulas nao geraram paragrafos desconexos duplicados
    p_texts = [b.raw_text for b in blocks if b.block_type == BlockType.PARAGRAPH]
    assert len(p_texts) == 2
    assert any("Titulo do Relatorio" in t for t in p_texts)
    assert any("Observacoes finais" in t for t in p_texts)
    assert not any("3500.00" in t for t in p_texts)
    doc.close()


def test_extract_page_blocks_without_table_fallback() -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text((50, 50), "Texto simples sem tabela.")

    blocks = extract_page_blocks(page, extract_tables=True)
    assert len(blocks) == 1
    assert blocks[0].block_type == BlockType.PARAGRAPH
    assert "Texto simples sem tabela" in blocks[0].raw_text
    doc.close()


def test_native_extractor_page_callback() -> None:
    doc = pymupdf.open()
    for i in range(3):
        p = doc.new_page()
        p.insert_text((50, 50), f"Pagina {i + 1}")

    calls: list[tuple[int, int]] = []

    def on_page(current: int, total: int) -> None:
        calls.append((current, total))

    extractor = NativeExtractor()
    extractor.extract(doc, page_callback=on_page)
    assert calls == [(1, 3), (2, 3), (3, 3)]
    doc.close()
