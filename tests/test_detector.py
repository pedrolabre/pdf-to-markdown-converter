from pathlib import Path

import pymupdf
import pytest

from pdf_to_markdown_converter.core.detector import (
    DEFAULT_MAX_SAMPLE_PAGES,
    MAX_CORRUPTION_RATIO,
    MIN_READABLE_CHARS,
    MIN_READABLE_RATIO,
    TextQualityReport,
    analyze_text_quality,
    detect_extraction_strategy,
    is_corrupted_char,
    is_readable_char,
    select_sample_pages,
)
from pdf_to_markdown_converter.core.pdf_reader import EncryptedPdfError
from pdf_to_markdown_converter.domain.models import ExtractionStrategy


def _create_sample_pdf(
    text: str = "",
    page_count: int = 1,
    insert_image: bool = False,
    user_pw: str = "",
    owner_pw: str = "",
) -> bytes:
    doc = pymupdf.open()
    for _ in range(page_count):
        page = doc.new_page(width=595, height=842)
        if text:
            page.insert_text((40, 50), text)
        if insert_image:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), False)
            pix.clear_with(200)
            page.insert_image(pymupdf.Rect(20, 20, 100, 100), stream=pix.tobytes("png"))

    save_kwargs = {}
    if user_pw or owner_pw:
        save_kwargs["encryption"] = pymupdf.PDF_ENCRYPT_AES_256
        save_kwargs["user_pw"] = user_pw
        save_kwargs["owner_pw"] = owner_pw or "owner_default"

    pdf_bytes = doc.tobytes(**save_kwargs)
    doc.close()
    return pdf_bytes


def test_select_sample_pages_scenarios():
    assert select_sample_pages(0) == []
    assert select_sample_pages(-1) == []
    assert select_sample_pages(10, max_pages=0) == []
    assert select_sample_pages(10, max_pages=-2) == []
    assert select_sample_pages(1) == [0]
    assert select_sample_pages(3, max_pages=5) == [0, 1, 2]
    assert select_sample_pages(5, max_pages=5) == [0, 1, 2, 3, 4]
    assert select_sample_pages(6, max_pages=5) == [0, 1, 3, 4, 5]
    assert select_sample_pages(10, max_pages=5) == [0, 1, 5, 8, 9]
    assert select_sample_pages(100, max_pages=5) == [0, 1, 50, 98, 99]
    assert select_sample_pages(10, max_pages=1) == [0]
    assert select_sample_pages(10, max_pages=2) == [0, 9]
    assert select_sample_pages(10, max_pages=3) == [0, 5, 9]
    assert select_sample_pages(10, max_pages=4) == [0, 1, 5, 9]


def test_is_corrupted_char_detection():
    for char in ("\x00", "\ufffd", "\ufffc", "\x01", "\x1b"):
        assert is_corrupted_char(char) is True
    for char in ("a", " ", "\n", "\t", "ç", "ã"):
        assert is_corrupted_char(char) is False


def test_is_readable_char_portuguese_and_symbols():
    valid_chars = (
        "a", "Z", "9", "!", " ", "\n", "\t", "\r",
        "á", "é", "í", "ó", "ú", "ã", "õ", "ç", "Á", "Ç",
    )
    for char in valid_chars:
        assert is_readable_char(char) is True
    for char in ("\x00", "\ufffd", "\ufffc", "\x07"):
        assert is_readable_char(char) is False


def test_detect_native_text_single_page():
    content = "Este documento contém texto vetorial perfeitamente legível e estruturado."
    pdf_bytes = _create_sample_pdf(text=content)

    strategy = detect_extraction_strategy(pdf_bytes)
    assert strategy == ExtractionStrategy.NATIVE_TEXT

    report = analyze_text_quality(pdf_bytes)
    assert report.recommended_strategy == ExtractionStrategy.NATIVE_TEXT
    assert report.total_chars > MIN_READABLE_CHARS
    assert report.printable_chars > MIN_READABLE_CHARS
    assert report.corrupted_chars == 0
    assert report.corruption_ratio == 0.0
    assert report.readable_ratio == 1.0
    assert report.has_images is False
    assert report.pages_sampled == (0,)
    assert "Camada textual íntegra detectada" in report.reason


def test_detect_native_text_portuguese_accents():
    content = "Atenção: Ação de verificação e cálculo de índices orçamentários essenciais."
    pdf_bytes = _create_sample_pdf(text=content)

    strategy = detect_extraction_strategy(pdf_bytes)
    assert strategy == ExtractionStrategy.NATIVE_TEXT

    report = analyze_text_quality(pdf_bytes)
    assert report.corrupted_chars == 0
    assert report.readable_ratio == 1.0


def test_detect_scanned_pdf_image_only():
    pdf_bytes = _create_sample_pdf(text="", insert_image=True)

    strategy = detect_extraction_strategy(pdf_bytes)
    assert strategy == ExtractionStrategy.OCR_FALLBACK

    report = analyze_text_quality(pdf_bytes)
    assert report.recommended_strategy == ExtractionStrategy.OCR_FALLBACK
    assert report.total_chars == 0
    assert report.has_images is True
    assert "Nenhum caractere textual detectado" in report.reason


def test_detect_blank_pdf():
    pdf_bytes = _create_sample_pdf(text="", insert_image=False)

    strategy = detect_extraction_strategy(pdf_bytes)
    assert strategy == ExtractionStrategy.OCR_FALLBACK

    report = analyze_text_quality(pdf_bytes)
    assert report.recommended_strategy == ExtractionStrategy.OCR_FALLBACK
    assert report.total_chars == 0
    assert report.has_images is False


def test_detect_sparse_text_insufficient_density():
    pdf_bytes = _create_sample_pdf(text="Pág 1")

    strategy = detect_extraction_strategy(pdf_bytes)
    assert strategy == ExtractionStrategy.OCR_FALLBACK

    report = analyze_text_quality(pdf_bytes)
    assert report.recommended_strategy == ExtractionStrategy.OCR_FALLBACK
    assert "Densidade textual insuficiente" in report.reason


def test_detect_corrupted_control_characters_in_real_pdf():
    pdf_bytes = _create_sample_pdf(
        text="Texto válido com mais de trinta caracteres legíveis " + "\x01" * 20
    )
    strategy = detect_extraction_strategy(pdf_bytes)
    assert strategy == ExtractionStrategy.OCR_FALLBACK

    report = analyze_text_quality(pdf_bytes)
    assert report.recommended_strategy == ExtractionStrategy.OCR_FALLBACK
    assert report.corrupted_chars == 20
    assert report.corruption_ratio > MAX_CORRUPTION_RATIO
    assert "Taxa de corrupção textual" in report.reason


def test_detect_corrupted_text_high_replacement_chars(monkeypatch):
    pdf_bytes = _create_sample_pdf(text="Texto base de tamanho suficiente para teste")
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")

    monkeypatch.setattr(
        pymupdf.Page,
        "get_text",
        lambda self, *args, **kwargs: "Texto extraído com " + "\ufffd" * 20 + "\x00" * 5,
    )

    strategy = detect_extraction_strategy(doc)
    assert strategy == ExtractionStrategy.OCR_FALLBACK

    report = analyze_text_quality(doc)
    assert report.recommended_strategy == ExtractionStrategy.OCR_FALLBACK
    assert report.corrupted_chars == 25
    assert report.corruption_ratio > MAX_CORRUPTION_RATIO
    assert "Taxa de corrupção textual" in report.reason
    doc.close()


def test_force_ocr_precedence_over_native_text():
    content = "Texto longo e limpo que normalmente seria classificado como texto nativo."
    pdf_bytes = _create_sample_pdf(text=content)

    strategy = detect_extraction_strategy(pdf_bytes, force_ocr=True)
    assert strategy == ExtractionStrategy.OCR_FALLBACK

    report = analyze_text_quality(pdf_bytes, force_ocr=True)
    assert report.recommended_strategy == ExtractionStrategy.OCR_FALLBACK
    assert "force_ocr" in report.reason
    assert report.total_chars > 0
    assert report.printable_chars > 0


def test_multipage_pdf_sampling():
    pdf_bytes = _create_sample_pdf(
        text="Página com conteúdo analítico de teste para verificar a amostragem.",
        page_count=8,
    )

    report = analyze_text_quality(pdf_bytes, max_sample_pages=5)
    assert report.pages_sampled == (0, 1, 4, 6, 7)
    assert report.recommended_strategy == ExtractionStrategy.NATIVE_TEXT


def test_whitespace_only_document():
    pdf_bytes = _create_sample_pdf(text="   \n   \t   \n   ")

    strategy = detect_extraction_strategy(pdf_bytes)
    assert strategy == ExtractionStrategy.OCR_FALLBACK

    report = analyze_text_quality(pdf_bytes)
    assert report.recommended_strategy == ExtractionStrategy.OCR_FALLBACK
    assert "Densidade textual insuficiente" in report.reason


def test_detect_source_types(tmp_path: Path):
    content = "Documento padrão utilizado para testar compatibilidade de fontes de entrada."
    pdf_bytes = _create_sample_pdf(text=content)
    pdf_path = tmp_path / "teste_entrada.pdf"
    pdf_path.write_bytes(pdf_bytes)

    assert detect_extraction_strategy(pdf_bytes) == ExtractionStrategy.NATIVE_TEXT
    assert detect_extraction_strategy(pdf_path) == ExtractionStrategy.NATIVE_TEXT
    assert detect_extraction_strategy(str(pdf_path)) == ExtractionStrategy.NATIVE_TEXT

    doc = pymupdf.open(str(pdf_path))
    assert detect_extraction_strategy(doc) == ExtractionStrategy.NATIVE_TEXT
    assert not doc.is_closed
    doc.close()


def test_detect_encrypted_pdf_with_password():
    content = "Documento protegido com camada textual válida sob senha de acesso."
    pdf_bytes = _create_sample_pdf(text=content, user_pw="segredo123")

    strategy = detect_extraction_strategy(pdf_bytes, password="segredo123")
    assert strategy == ExtractionStrategy.NATIVE_TEXT

    with pytest.raises(EncryptedPdfError):
        detect_extraction_strategy(pdf_bytes, password="errada")

    with pytest.raises(EncryptedPdfError):
        detect_extraction_strategy(pdf_bytes)


def test_text_quality_report_dataclass():
    report = TextQualityReport(
        total_chars=100,
        printable_chars=98,
        corrupted_chars=2,
        readable_ratio=0.98,
        corruption_ratio=0.02,
        has_images=False,
        pages_sampled=[0, 1, 2],
        recommended_strategy=ExtractionStrategy.NATIVE_TEXT,
        reason="Teste",
    )

    assert report.pages_sampled == (0, 1, 2)
    assert report.total_chars == 100
    assert report.recommended_strategy == ExtractionStrategy.NATIVE_TEXT

    with pytest.raises(AttributeError):
        report.total_chars = 200

    with pytest.raises(ValueError, match="total_chars cannot be negative"):
        TextQualityReport(
            total_chars=-1,
            printable_chars=0,
            corrupted_chars=0,
            readable_ratio=0.0,
            corruption_ratio=0.0,
            has_images=False,
            pages_sampled=(0,),
            recommended_strategy=ExtractionStrategy.NATIVE_TEXT,
            reason="Erro",
        )
