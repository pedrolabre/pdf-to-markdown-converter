from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

import pymupdf
import pytest

from pdf_to_markdown_converter import cli
from pdf_to_markdown_converter.cli import (
    CliExitCode,
    build_main_parser,
    main,
    run_cli,
    run_info_command,
)
from pdf_to_markdown_converter.core.tesseract_env import TesseractNotFoundError


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 70), "# 1. Documento de Teste", fontsize=16)
    page.insert_text((50, 120), "Texto de teste para validacao da CLI principal.")
    pdf_path = tmp_path / "teste_cli.pdf"
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def _exec(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = run_cli(argv, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def test_cli_exports() -> None:
    assert CliExitCode.SUCCESS == 0
    assert CliExitCode.GENERAL_ERROR == 1
    assert CliExitCode.FILE_NOT_FOUND == 2
    assert CliExitCode.INVALID_PDF == 3
    assert CliExitCode.TESSERACT_NOT_FOUND == 4
    assert CliExitCode.DESTINATION_EXISTS == 5
    assert CliExitCode.ENCRYPTION_ERROR == 6
    assert CliExitCode.INTERRUPTED == 130
    assert hasattr(cli, "CliExitCode")
    assert hasattr(cli, "build_main_parser")
    assert hasattr(cli, "main")
    assert hasattr(cli, "run_cli")
    assert hasattr(cli, "run_info_command")


def test_cli_no_args_shows_help() -> None:
    code, out, _ = _exec([])
    assert code == CliExitCode.SUCCESS
    assert "pdf-to-markdown" in out
    assert "extract" in out
    assert "info" in out


def test_cli_help_flag() -> None:
    code, out, _ = _exec(["--help"])
    assert code == CliExitCode.SUCCESS
    assert "subcomandos" in out


def test_cli_version_flag() -> None:
    code, out, _ = _exec(["--version"])
    assert code == CliExitCode.SUCCESS
    assert "pdf-to-markdown" in out


def test_cli_invalid_argument() -> None:
    code, _, err = _exec(["--opcao-inexistente"])
    assert code == CliExitCode.GENERAL_ERROR
    assert "unrecognized arguments" in err


def test_cli_subcommand_info() -> None:
    code, out, _ = _exec(["info"])
    assert code == CliExitCode.SUCCESS
    assert "Diagnóstico" in out


def test_cli_subcommand_info_json() -> None:
    code, out, _ = _exec(["info", "--json"])
    assert code == CliExitCode.SUCCESS
    data = json.loads(out)
    assert "package" in data
    assert "tesseract" in data


def test_cli_extract_explicit(sample_pdf: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "saida"
    code, out, _ = _exec(["extract", str(sample_pdf), "-o", str(out_dir)])
    assert code == CliExitCode.SUCCESS
    assert (out_dir / "teste_cli.md").exists()
    assert (out_dir / "teste_cli.html").exists()
    assert "[OK] Conversão concluída" in out


def test_cli_extract_implicit_alias(sample_pdf: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "alias_saida"
    code, _, _ = _exec([str(sample_pdf), "-o", str(out_dir)])
    assert code == CliExitCode.SUCCESS
    assert (out_dir / "teste_cli.md").exists()
    assert (out_dir / "teste_cli.html").exists()


def test_cli_extract_format_filter(sample_pdf: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "somente_md"
    code, _, _ = _exec(["extract", str(sample_pdf), "-o", str(out_dir), "--format", "md"])
    assert code == CliExitCode.SUCCESS
    assert (out_dir / "teste_cli.md").exists()
    assert not (out_dir / "teste_cli.html").exists()


def test_cli_extract_multiple_formats_csv(sample_pdf: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "multi_csv"
    code, _, _ = _exec(["extract", str(sample_pdf), "-o", str(out_dir), "--format", "md,html"])
    assert code == CliExitCode.SUCCESS
    assert (out_dir / "teste_cli.md").exists()
    assert (out_dir / "teste_cli.html").exists()


def test_cli_extract_quiet_mode(sample_pdf: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "quiet_out"
    code, out, err = _exec(["extract", str(sample_pdf), "-o", str(out_dir), "-q"])
    assert code == CliExitCode.SUCCESS
    assert out.strip() == ""
    assert err.strip() == ""


def test_cli_extract_custom_output_path(sample_pdf: Path, tmp_path: Path) -> None:
    custom_target = tmp_path / "custom_doc.md"
    code, _, _ = _exec(["extract", str(sample_pdf), "--output-path", str(custom_target)])
    assert code == CliExitCode.SUCCESS
    assert custom_target.exists()
    assert (tmp_path / "custom_doc.html").exists()


def test_cli_extract_colors_and_no_color(sample_pdf: Path, tmp_path: Path) -> None:
    code, out, _ = _exec(["extract", str(sample_pdf), "-o", str(tmp_path / "c1"), "--color"])
    assert code == CliExitCode.SUCCESS
    assert "\033[32m" in out

    code_nc, out_nc, _ = _exec(["extract", str(sample_pdf), "-o", str(tmp_path / "c2"), "--no-color"])
    assert code_nc == CliExitCode.SUCCESS
    assert "\033[32m" not in out_nc


def test_cli_error_file_not_found(tmp_path: Path) -> None:
    non_existent = tmp_path / "inexistente.pdf"
    code, _, err = _exec(["extract", str(non_existent)])
    assert code == CliExitCode.FILE_NOT_FOUND
    assert "[FALHA]" in err
    assert "Arquivo PDF não encontrado" in err


def test_cli_error_empty_pdf(tmp_path: Path) -> None:
    empty = tmp_path / "vazio.pdf"
    empty.write_bytes(b"")
    code, _, err = _exec(["extract", str(empty)])
    assert code == CliExitCode.INVALID_PDF
    assert "[FALHA]" in err
    assert "vazio (0 bytes)" in err


def test_cli_error_corrupted_pdf(tmp_path: Path) -> None:
    corrupted = tmp_path / "corrompido.pdf"
    corrupted.write_bytes(b"nao e um documento pdf valido %PDF lixo")
    code, _, err = _exec(["extract", str(corrupted)])
    assert code == CliExitCode.INVALID_PDF
    assert "[FALHA]" in err


def test_cli_error_encrypted_pdf_without_password(tmp_path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Este e um documento protegido com texto valido para extracao nativa.")
    enc_path = tmp_path / "protegido.pdf"
    doc.save(str(enc_path), encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="123")
    doc.close()

    code, _, err = _exec(["extract", str(enc_path)])
    assert code == CliExitCode.ENCRYPTION_ERROR
    assert "protegido por senha" in err

    code_pw, _, _ = _exec(["extract", str(enc_path), "--password", "123", "-o", str(tmp_path / "enc_ok")])
    assert code_pw == CliExitCode.SUCCESS


def test_cli_error_destination_exists_no_overwrite(sample_pdf: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "no_over"
    code1, _, _ = _exec(["extract", str(sample_pdf), "-o", str(out_dir)])
    assert code1 == CliExitCode.SUCCESS

    code2, _, err = _exec(["extract", str(sample_pdf), "-o", str(out_dir), "--no-overwrite"])
    assert code2 == CliExitCode.DESTINATION_EXISTS
    assert "[FALHA]" in err


def test_cli_error_tesseract_not_found(sample_pdf: Path, tmp_path: Path) -> None:
    with patch(
        "pdf_to_markdown_converter.core.pipeline.detect_extraction_strategy",
        side_effect=TesseractNotFoundError("Tesseract OCR ausente"),
    ):
        code, _, err = _exec(["extract", str(sample_pdf), "-o", str(tmp_path), "--force-ocr"])
        assert code == CliExitCode.TESSERACT_NOT_FOUND
        assert "Tesseract OCR ausente" in err


def test_cli_error_invalid_option(sample_pdf: Path, tmp_path: Path) -> None:
    code, _, err = _exec(["extract", str(sample_pdf), "--format", "invalido"])
    assert code == CliExitCode.GENERAL_ERROR
    assert "Configuração inválida" in err


def test_cli_keyboard_interrupt(sample_pdf: Path, tmp_path: Path) -> None:
    with patch("pdf_to_markdown_converter.cli.main.convert_pdf", side_effect=KeyboardInterrupt()):
        code, _, err = _exec(["extract", str(sample_pdf), "-o", str(tmp_path)])
        assert code == CliExitCode.INTERRUPTED
        assert "Operação cancelada pelo usuário" in err


def test_cli_unexpected_exception(sample_pdf: Path, tmp_path: Path) -> None:
    with patch("pdf_to_markdown_converter.cli.main.convert_pdf", side_effect=RuntimeError("falha misteriosa")):
        code, _, err = _exec(["extract", str(sample_pdf), "-o", str(tmp_path)])
        assert code == CliExitCode.GENERAL_ERROR
        assert "falha misteriosa" in err

    with patch("pdf_to_markdown_converter.cli.main.convert_pdf", side_effect=RuntimeError("falha misteriosa debug")):
        with pytest.raises(RuntimeError, match="falha misteriosa debug"):
            _exec(["extract", str(sample_pdf), "--debug"])


def test_cli_subcommand_gui() -> None:
    with patch("pdf_to_markdown_converter.gui.launch_gui", return_value=0) as mock_launch:
        code, _, _ = _exec(["gui"])
        assert code == CliExitCode.SUCCESS
        assert mock_launch.called


def test_cli_subcommand_gui_failure() -> None:
    with patch("pdf_to_markdown_converter.gui.launch_gui", side_effect=RuntimeError("GUI crash")):
        code, _, err = _exec(["gui"])
        assert code == CliExitCode.GENERAL_ERROR
        assert "Erro ao inicializar interface gráfica" in err


def test_main_entrypoint(monkeypatch: pytest.MonkeyPatch, sample_pdf: Path, tmp_path: Path) -> None:
    monkeypatch.setattr("sys.argv", ["pdf-to-markdown", str(sample_pdf), "-o", str(tmp_path / "main_entry")])
    exit_codes: list[int] = []
    monkeypatch.setattr("sys.exit", lambda code: exit_codes.append(code))
    main()
    assert exit_codes == [0]
