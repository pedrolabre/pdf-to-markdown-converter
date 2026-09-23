from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

import pymupdf
import pytest

from pdf_to_markdown_converter.cli.main import CliExitCode, run_cli
from pdf_to_markdown_converter.core.pipeline import ConversionPipeline, convert_pdf
from pdf_to_markdown_converter.domain.models import (
    BlockType,
    DocumentStructure,
    ExtractionResult,
    ExtractionStrategy,
    TextBlock,
)


def _exec(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = run_cli(argv, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def _create_rich_pdf(target: Path) -> Path:
    doc = pymupdf.open()
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((50, 60), "# Manual do Sistema de Testes", fontsize=18)
    p1.insert_text((50, 95), "Este guia descreve a integracao de sis- \ntemas essenciais de automacao.", fontsize=11)
    p1.insert_text((50, 135), "## 1. Diretrizes Principais", fontsize=14)
    p1.insert_text((50, 165), "* Alta performance e integridade", fontsize=11)
    p1.insert_text((50, 185), "* Processamento seguro local", fontsize=11)
    p1.insert_text((50, 215), "1. Validacao preliminar de formato", fontsize=11)
    p1.insert_text((50, 235), "2. Normalizacao canonica de dados", fontsize=11)

    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((50, 60), "## 2. Codigo e Execucao", fontsize=14)
    p2.insert_text((50, 95), "```python\ndef execute():\n    return True\n```", fontsize=10)
    p2.insert_text((50, 155), "Documentacao concluida com acentuacao: acao, integridade e conclusao.", fontsize=11)

    doc.save(str(target))
    doc.close()
    return target


def _create_scanned_pdf(target: Path) -> Path:
    doc = pymupdf.open()
    p = doc.new_page(width=595, height=842)
    pix = pymupdf.Pixmap(pymupdf.csRGB, (0, 0, 400, 300), 0)
    pix.clear_with(255)
    p.insert_image(pymupdf.Rect(50, 50, 450, 350), pixmap=pix)
    doc.save(str(target))
    doc.close()
    return target


def _create_encrypted_pdf(target: Path, password: str) -> Path:
    doc = pymupdf.open()
    p = doc.new_page(width=595, height=842)
    p.insert_text((50, 60), "# Documento Protegido", fontsize=16)
    p.insert_text((50, 100), "Segredo confidencial de negocio.", fontsize=11)
    doc.save(str(target), encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw=password, owner_pw="master_" + password)
    doc.close()
    return target


def test_e2e_native_pipeline_cli_complete_flow(tmp_path: Path) -> None:
    pdf_path = _create_rich_pdf(tmp_path / "manual.pdf")
    out_dir = tmp_path / "dist"

    code, out, _ = _exec(["extract", str(pdf_path), "-o", str(out_dir)])
    assert code == CliExitCode.SUCCESS
    assert "concluída com sucesso" in out or "concluida com sucesso" in out

    md_file = out_dir / "manual.md"
    html_file = out_dir / "manual.html"
    assert md_file.exists()
    assert html_file.exists()

    md_content = md_file.read_text(encoding="utf-8")
    assert "# Manual do Sistema de Testes" in md_content
    assert "## 1. Diretrizes Principais" in md_content
    assert "sistemas essenciais" in md_content
    assert "- Alta performance e integridade" in md_content
    assert "- Processamento seguro local" in md_content
    assert "1. Validacao preliminar de formato" in md_content
    assert "```python" in md_content or "def execute():" in md_content
    assert "acao, integridade e conclusao" in md_content

    html_content = html_file.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html_content
    assert '<html lang="pt-BR">' in html_content
    assert "<style>" in html_content
    assert "@media (prefers-color-scheme: dark)" in html_content
    assert "<h1>Manual do Sistema de Testes</h1>" in html_content
    assert "<li>" in html_content
    assert "Alta performance e integridade" in html_content
    assert "<code>" in html_content


def test_e2e_cli_implicit_alias(tmp_path: Path) -> None:
    pdf_path = _create_rich_pdf(tmp_path / "alias_doc.pdf")
    out_dir = tmp_path / "saida_alias"

    code, out, _ = _exec([str(pdf_path), "-o", str(out_dir)])
    assert code == CliExitCode.SUCCESS
    assert (out_dir / "alias_doc.md").exists()
    assert (out_dir / "alias_doc.html").exists()


def test_e2e_format_filter_and_custom_output_path(tmp_path: Path) -> None:
    pdf_path = _create_rich_pdf(tmp_path / "format_test.pdf")

    out_md_only = tmp_path / "md_only"
    code, _, _ = _exec(["extract", str(pdf_path), "-o", str(out_md_only), "--format", "md"])
    assert code == CliExitCode.SUCCESS
    assert (out_md_only / "format_test.md").exists()
    assert not (out_md_only / "format_test.html").exists()

    out_html_only = tmp_path / "html_only"
    code, _, _ = _exec(["extract", str(pdf_path), "-o", str(out_html_only), "--format", "html"])
    assert code == CliExitCode.SUCCESS
    assert (out_html_only / "format_test.html").exists()
    assert not (out_html_only / "format_test.md").exists()

    custom_md = tmp_path / "custom" / "relatorio_final.md"
    code, _, _ = _exec(["extract", str(pdf_path), "--output-path", str(custom_md)])
    assert code == CliExitCode.SUCCESS
    assert custom_md.exists()
    assert "# Manual do Sistema de Testes" in custom_md.read_text(encoding="utf-8")


def test_e2e_encrypted_pdf_flow(tmp_path: Path) -> None:
    pdf_path = _create_encrypted_pdf(tmp_path / "protegido.pdf", "senha_secreta")
    out_dir = tmp_path / "saida_protegida"

    code, _, err = _exec(["extract", str(pdf_path), "-o", str(out_dir)])
    assert code == CliExitCode.ENCRYPTION_ERROR
    assert "protegido por senha" in err

    code, out, _ = _exec(["extract", str(pdf_path), "-o", str(out_dir), "--password", "senha_secreta"])
    assert code == CliExitCode.SUCCESS
    assert (out_dir / "protegido.md").exists()
    assert "Segredo confidencial de negocio" in (out_dir / "protegido.md").read_text(encoding="utf-8")


def test_e2e_scanned_ocr_fallback_flow(tmp_path: Path) -> None:
    scanned_pdf = _create_scanned_pdf(tmp_path / "escaneado.pdf")
    out_dir = tmp_path / "saida_ocr"

    fake_block = TextBlock(1, BlockType.PARAGRAPH, "Texto OCR Fallback", "Texto OCR Fallback", (10, 10, 50, 50), 0)
    fake_doc = DocumentStructure(str(scanned_pdf), 1, ExtractionStrategy.OCR_FALLBACK, [fake_block])

    with patch("pdf_to_markdown_converter.core.pipeline.OcrExtractor.extract", return_value=fake_doc):
        code, out, _ = _exec(["extract", str(scanned_pdf), "-o", str(out_dir)])
        assert code == CliExitCode.SUCCESS
        assert "ocr_fallback" in out
        md_file = out_dir / "escaneado.md"
        assert md_file.exists()
        assert "Texto OCR Fallback" in md_file.read_text(encoding="utf-8")

    temp_images = list(tmp_path.glob("*.png")) + list(tmp_path.glob("*.jpg"))
    assert len(temp_images) == 0


def test_e2e_overwrite_protection(tmp_path: Path) -> None:
    pdf_path = _create_rich_pdf(tmp_path / "overwrite_test.pdf")
    out_dir = tmp_path / "saida_sobrescrita"

    code, _, _ = _exec(["extract", str(pdf_path), "-o", str(out_dir)])
    assert code == CliExitCode.SUCCESS

    code, _, err = _exec(["extract", str(pdf_path), "-o", str(out_dir), "--no-overwrite"])
    assert code == CliExitCode.DESTINATION_EXISTS
    assert "ja existe" in err

    code, _, _ = _exec(["extract", str(pdf_path), "-o", str(out_dir)])
    assert code == CliExitCode.SUCCESS


def test_e2e_error_handling_invalid_inputs(tmp_path: Path) -> None:
    code, _, err = _exec(["extract", str(tmp_path / "nao_existe.pdf")])
    assert code == CliExitCode.FILE_NOT_FOUND
    assert "não encontrado" in err or "nao encontrado" in err

    empty_file = tmp_path / "vazio.pdf"
    empty_file.write_bytes(b"")
    code, _, err = _exec(["extract", str(empty_file)])
    assert code == CliExitCode.INVALID_PDF
    assert "vazio" in err

    bad_file = tmp_path / "corrompido.pdf"
    bad_file.write_bytes(b"Isto nao e um PDF valido.")
    code, _, err = _exec(["extract", str(bad_file)])
    assert code == CliExitCode.INVALID_PDF
    assert "corrompido" in err

    code, _, err = _exec(["extract", str(empty_file), "--dpi", "0"])
    assert code == CliExitCode.GENERAL_ERROR
    assert "DPI" in err


def test_e2e_cli_info_command() -> None:
    code, out, _ = _exec(["info"])
    assert code == CliExitCode.SUCCESS
    assert "Diagnóstico" in out or "Diagnostico" in out
    assert "Python" in out
    assert "PyMuPDF" in out
    assert "Markdown" in out

    code, out, _ = _exec(["info", "--json"])
    assert code == CliExitCode.SUCCESS
    data = json.loads(out)
    assert "python" in data
    assert "package" in data
    assert "tesseract" in data
    assert data["package"]["name"] == "pdf-to-markdown-converter"


def test_e2e_direct_python_api(tmp_path: Path) -> None:
    pdf_path = _create_rich_pdf(tmp_path / "api_doc.pdf")
    out_dir = tmp_path / "api_out"

    result = convert_pdf(pdf_path, output_dir=out_dir)
    assert isinstance(result, ExtractionResult)
    assert result.strategy_used == ExtractionStrategy.NATIVE_TEXT
    assert result.pages_processed == 2
    assert result.execution_time_seconds >= 0.0
    assert Path(result.markdown_path).exists()
    assert Path(result.html_path).exists()
    assert "# Manual do Sistema de Testes" in Path(result.markdown_path).read_text(encoding="utf-8")
