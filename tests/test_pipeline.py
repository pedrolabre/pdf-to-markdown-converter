from collections.abc import Sequence
from pathlib import Path
from unittest.mock import MagicMock, patch

import pymupdf
import pytest

from pdf_to_markdown_converter.core.pdf_reader import EmptyPdfError, EncryptedPdfError
from pdf_to_markdown_converter.core.pipeline import (
    ConversionPipeline,
    InvalidOptionError,
    Pipeline,
    PipelineError,
    PipelineStage,
    convert_pdf,
)
from pdf_to_markdown_converter.domain.models import (
    BlockType,
    DocumentStructure,
    ExtractionResult,
    ExtractionStrategy,
    TextBlock,
)
from pdf_to_markdown_converter.exporters.markdown_exporter import DestinationExistsError


def _create_sample_pdf(num_pages: int = 1) -> bytes:
    doc = pymupdf.open()
    for i in range(num_pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((50, 70), f"1. Titulo da Pagina {i + 1}", fontsize=16)
        page.insert_text((50, 120), "Este e um paragrafo de teste que contem texto legivel.")
    data = doc.tobytes()
    doc.close()
    return data


def test_pipeline_init_defaults() -> None:
    pipeline = ConversionPipeline()
    assert pipeline.output_dir is None
    assert pipeline.force_ocr is False
    assert pipeline.dpi == 300
    assert pipeline.lang == "por+eng"
    assert pipeline.overwrite is True
    assert pipeline.export_formats == ("md", "html")
    assert Pipeline is ConversionPipeline


def test_pipeline_init_custom(tmp_path: Path) -> None:
    pipeline = ConversionPipeline(
        output_dir=tmp_path,
        force_ocr=True,
        dpi=150,
        lang="eng",
        overwrite=False,
        export_formats=["markdown", "html5"],
    )
    assert pipeline.output_dir == tmp_path
    assert pipeline.force_ocr is True
    assert pipeline.dpi == 150
    assert pipeline.lang == "eng"
    assert pipeline.overwrite is False
    assert pipeline.export_formats == ("markdown", "html5")


def test_pipeline_init_invalid_options() -> None:
    with pytest.raises(InvalidOptionError, match="DPI deve ser um inteiro positivo"):
        ConversionPipeline(dpi=0)

    with pytest.raises(InvalidOptionError, match="Pelo menos um formato"):
        ConversionPipeline(export_formats=[])

    with pytest.raises(InvalidOptionError, match="nao suportado"):
        ConversionPipeline(export_formats=["docx"])


def test_pipeline_convert_native_pdf(tmp_path: Path) -> None:
    pdf_bytes = _create_sample_pdf(num_pages=2)
    pdf_file = tmp_path / "documento.pdf"
    pdf_file.write_bytes(pdf_bytes)

    out_dir = tmp_path / "saida"
    pipeline = ConversionPipeline(output_dir=out_dir)
    result = pipeline.convert(pdf_file)

    assert isinstance(result, ExtractionResult)
    assert result.source_path == str(pdf_file)
    assert result.pages_processed == 2
    assert result.strategy_used == ExtractionStrategy.NATIVE_TEXT
    assert result.execution_time_seconds >= 0.0

    md_file = Path(result.markdown_path)
    html_file = Path(result.html_path)

    assert md_file.exists()
    assert md_file.parent == out_dir
    assert md_file.name == "documento.md"
    assert "# 1. Titulo da Pagina 1" in md_file.read_text(encoding="utf-8")

    assert html_file.exists()
    assert html_file.parent == out_dir
    assert html_file.name == "documento.html"
    assert "<!DOCTYPE html>" in html_file.read_text(encoding="utf-8")


def test_pipeline_convert_from_bytes(tmp_path: Path) -> None:
    pdf_bytes = _create_sample_pdf(num_pages=1)
    pipeline = ConversionPipeline(output_dir=tmp_path)
    result = pipeline.convert(pdf_bytes)

    assert result.source_path == "<memory>"
    assert result.pages_processed == 1
    assert Path(result.markdown_path).name == "output.md"
    assert Path(result.html_path).name == "output.html"
    assert Path(result.markdown_path).exists()
    assert Path(result.html_path).exists()


def test_pipeline_convert_document_instance(tmp_path: Path) -> None:
    pdf_bytes = _create_sample_pdf(num_pages=1)
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    pipeline = ConversionPipeline(output_dir=tmp_path)

    result = pipeline.convert_document(doc, filename="meu_doc")
    doc.close()

    assert Path(result.markdown_path).name == "meu_doc.md"
    assert Path(result.html_path).name == "meu_doc.html"
    assert Path(result.markdown_path).exists()


def test_pipeline_selective_formats(tmp_path: Path) -> None:
    pdf_bytes = _create_sample_pdf(num_pages=1)
    pdf_file = tmp_path / "relatorio.pdf"
    pdf_file.write_bytes(pdf_bytes)

    pipeline_md = ConversionPipeline(output_dir=tmp_path, export_formats=["md"])
    res_md = pipeline_md.convert(pdf_file, filename="apenas_md")
    assert res_md.markdown_path != ""
    assert res_md.html_path == ""
    assert Path(res_md.markdown_path).exists()

    pipeline_html = ConversionPipeline(output_dir=tmp_path, export_formats=["html"])
    res_html = pipeline_html.convert(pdf_file, filename="apenas_html")
    assert res_html.markdown_path == ""
    assert res_html.html_path != ""
    assert Path(res_html.html_path).exists()


def test_pipeline_custom_output_path(tmp_path: Path) -> None:
    pdf_bytes = _create_sample_pdf(num_pages=1)
    pdf_file = tmp_path / "input.pdf"
    pdf_file.write_bytes(pdf_bytes)

    custom_out = tmp_path / "custom" / "resultado.md"
    pipeline = ConversionPipeline()
    result = pipeline.convert(pdf_file, output_path=custom_out)

    assert Path(result.markdown_path) == custom_out
    assert Path(result.html_path) == custom_out.with_suffix(".html")
    assert custom_out.exists()
    assert custom_out.with_suffix(".html").exists()


def test_pipeline_overwrite_control(tmp_path: Path) -> None:
    pdf_bytes = _create_sample_pdf(num_pages=1)
    pdf_file = tmp_path / "doc.pdf"
    pdf_file.write_bytes(pdf_bytes)

    pipeline = ConversionPipeline(output_dir=tmp_path, overwrite=True)
    res1 = pipeline.convert(pdf_file)
    assert Path(res1.markdown_path).exists()

    pipeline_no_overwrite = ConversionPipeline(output_dir=tmp_path, overwrite=False)
    with pytest.raises(DestinationExistsError):
        pipeline_no_overwrite.convert(pdf_file)


def test_pipeline_progress_callbacks(tmp_path: Path) -> None:
    pdf_bytes = _create_sample_pdf(num_pages=1)
    pdf_file = tmp_path / "callback.pdf"
    pdf_file.write_bytes(pdf_bytes)

    events: list[tuple[PipelineStage, float, str]] = []

    def callback(stage: PipelineStage, progress: float, message: str) -> None:
        events.append((stage, progress, message))

    pipeline = ConversionPipeline(output_dir=tmp_path, progress_callback=callback)
    pipeline.convert(pdf_file)

    stages = [event[0] for event in events]
    assert PipelineStage.OPENING in stages
    assert PipelineStage.START in stages
    assert PipelineStage.DETECTING in stages
    assert PipelineStage.EXTRACTING in stages
    assert PipelineStage.CLASSIFYING in stages
    assert PipelineStage.EXPORTING in stages
    assert PipelineStage.FINISHED in stages

    for _, progress, _ in events:
        assert 0.0 <= progress <= 1.0


def test_pipeline_progress_callback_two_params(tmp_path: Path) -> None:
    pdf_bytes = _create_sample_pdf(num_pages=1)
    stages_seen: list[PipelineStage] = []

    def callback_two_args(stage: PipelineStage, progress: float) -> None:
        stages_seen.append(stage)

    pipeline = ConversionPipeline(output_dir=tmp_path, progress_callback=callback_two_args)
    pipeline.convert(pdf_bytes)
    assert PipelineStage.FINISHED in stages_seen


@patch.object(ConversionPipeline, "_process_document")
def test_pipeline_force_ocr(mock_proc: MagicMock, tmp_path: Path) -> None:
    pipeline = ConversionPipeline(force_ocr=True)
    pdf_bytes = _create_sample_pdf(num_pages=1)
    mock_proc.return_value = ExtractionResult(
        source_path="<memory>",
        markdown_path="",
        html_path="",
        strategy_used=ExtractionStrategy.OCR_FALLBACK,
        pages_processed=1,
        execution_time_seconds=0.1,
    )
    res = pipeline.convert(pdf_bytes)
    assert res.strategy_used == ExtractionStrategy.OCR_FALLBACK
    assert mock_proc.called


def test_pipeline_ocr_fallback_execution(tmp_path: Path) -> None:
    pdf_bytes = _create_sample_pdf(num_pages=1)
    pipeline = ConversionPipeline(
        output_dir=tmp_path,
        force_ocr=True,
        check_ocr_environment=False,
    )

    fake_block = TextBlock(1, BlockType.PARAGRAPH, "Texto OCR", "Texto OCR", (10, 10, 50, 50), 0)
    fake_doc = DocumentStructure("doc", 1, ExtractionStrategy.OCR_FALLBACK, [fake_block])

    with patch.object(pipeline.ocr_extractor, "extract", return_value=fake_doc):
        res = pipeline.convert(pdf_bytes, filename="ocr_test")
        assert res.strategy_used == ExtractionStrategy.OCR_FALLBACK
        assert "Texto OCR" in Path(res.markdown_path).read_text(encoding="utf-8")


def test_pipeline_encrypted_pdf(tmp_path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Este e um documento confidencial e secreto com conteudo extenso para teste.")
    enc_path = tmp_path / "enc.pdf"
    doc.save(
        str(enc_path),
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        user_pw="senha123",
        owner_pw="master123",
    )
    doc.close()

    with pytest.raises(EncryptedPdfError):
        pipeline = ConversionPipeline(output_dir=tmp_path)
        pipeline.convert(enc_path)

    pipeline = ConversionPipeline(output_dir=tmp_path)
    res = pipeline.convert(enc_path, password="senha123")
    assert res.pages_processed == 1
    assert "confidencial" in Path(res.markdown_path).read_text(encoding="utf-8")


def test_pipeline_empty_file_error(tmp_path: Path) -> None:
    empty_file = tmp_path / "empty.pdf"
    empty_file.write_bytes(b"")

    pipeline = ConversionPipeline()
    with pytest.raises(EmptyPdfError):
        pipeline.convert(empty_file)


def test_convert_pdf_top_level_function(tmp_path: Path) -> None:
    pdf_bytes = _create_sample_pdf(num_pages=1)
    res = convert_pdf(
        pdf_bytes,
        output_dir=tmp_path,
        filename="via_func",
        export_formats=["md"],
    )
    assert res.markdown_path != ""
    assert res.html_path == ""
    assert Path(res.markdown_path).name == "via_func.md"
    assert Path(res.markdown_path).exists()
