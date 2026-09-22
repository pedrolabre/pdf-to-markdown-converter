from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

import pdf_to_markdown_converter.cli as cli
from pdf_to_markdown_converter.cli.info import (
    InfoExitCode,
    _colorize,
    _get_markdown_version,
    _get_package_version,
    _get_pillow_version,
    _get_pymupdf_version,
    _get_pytesseract_version,
    format_environment_info,
    get_environment_info,
    run_info_command,
)
from pdf_to_markdown_converter.core.tesseract_env import TesseractDiagnostics


def test_cli_init_exports() -> None:
    assert hasattr(cli, "InfoExitCode")
    assert hasattr(cli, "get_environment_info")
    assert hasattr(cli, "format_environment_info")
    assert hasattr(cli, "run_info_command")
    assert set(cli.__all__) == {
        "InfoExitCode",
        "get_environment_info",
        "format_environment_info",
        "run_info_command",
    }


def test_get_package_and_library_versions() -> None:
    pkg_ver = _get_package_version()
    assert pkg_ver == "0.1.0"

    pymupdf_ver = _get_pymupdf_version()
    assert pymupdf_ver is not None

    markdown_ver = _get_markdown_version()
    assert markdown_ver is not None

    pillow_ver = _get_pillow_version()
    assert pillow_ver is not None

    pytess_ver = _get_pytesseract_version()
    assert pytess_ver is not None


def test_get_environment_info_structure() -> None:
    info = get_environment_info()
    assert "package" in info
    assert "python" in info
    assert "libraries" in info
    assert "tesseract" in info
    assert "status" in info

    assert info["package"]["name"] == "pdf-to-markdown-converter"
    assert info["package"]["version"] == "0.1.0"

    py = info["python"]
    assert bool(py["version"])
    assert bool(py["platform"])
    assert bool(py["executable"])

    libs = info["libraries"]
    assert "pymupdf" in libs
    assert "markdown" in libs
    assert "pillow" in libs
    assert "pytesseract" in libs
    assert libs["pymupdf"]["installed"] is True
    assert libs["markdown"]["installed"] is True

    status = info["status"]
    assert status["ready_for_native"] is True
    assert isinstance(status["ready_for_ocr"], bool)


def test_get_environment_info_tesseract_mock_available() -> None:
    mock_diag = TesseractDiagnostics(
        is_available=True,
        binary_path=r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        version="5.4.0",
        available_languages=("eng", "osd", "por"),
        tessdata_path=r"C:\Program Files\Tesseract-OCR\tessdata",
    )
    with patch(
        "pdf_to_markdown_converter.cli.info.get_tesseract_diagnostics",
        return_value=mock_diag,
    ):
        info = get_environment_info()
        assert info["tesseract"]["is_available"] is True
        assert info["tesseract"]["version"] == "5.4.0"
        assert info["tesseract"]["languages"] == ["eng", "osd", "por"]
        assert info["status"]["ready_for_ocr"] is True


def test_get_environment_info_tesseract_mock_unavailable() -> None:
    mock_diag = TesseractDiagnostics(
        is_available=False,
        error_message="Executavel nao encontrado",
        instructions="Instale via winget",
    )
    with patch(
        "pdf_to_markdown_converter.cli.info.get_tesseract_diagnostics",
        return_value=mock_diag,
    ):
        info = get_environment_info()
        assert info["tesseract"]["is_available"] is False
        assert info["tesseract"]["error_message"] == "Executavel nao encontrado"
        assert info["tesseract"]["instructions"] == "Instale via winget"
        assert info["status"]["ready_for_ocr"] is False


def test_get_environment_info_missing_core_library() -> None:
    with patch("pdf_to_markdown_converter.cli.info._get_pymupdf_version", return_value=None):
        info = get_environment_info()
        assert info["libraries"]["pymupdf"]["installed"] is False
        assert info["status"]["ready_for_native"] is False


def test_colorize_helper() -> None:
    assert _colorize("test", "\033[32m", enabled=False) == "test"
    colored = _colorize("test", "\033[32m", enabled=True)
    assert colored.startswith("\033[32m")
    assert colored.endswith("\033[0m")


def test_format_environment_info_plain() -> None:
    info = {
        "package": {"name": "pdf-to-markdown-converter", "version": "0.1.0"},
        "python": {
            "version": "3.14.0",
            "implementation": "CPython",
            "platform": "Windows-11",
            "executable": "python.exe",
        },
        "libraries": {
            "pymupdf": {"installed": True, "version": "1.28.2"},
            "markdown": {"installed": True, "version": "3.10.3"},
            "pillow": {"installed": True, "version": "12.3.0"},
            "pytesseract": {"installed": True, "version": "0.3.13"},
        },
        "tesseract": {
            "is_available": True,
            "binary_path": r"C:\tesseract.exe",
            "version": "5.4.0",
            "languages": ["eng", "por"],
            "tessdata_path": r"C:\tessdata",
            "error_message": None,
            "instructions": None,
        },
        "status": {"ready_for_native": True, "ready_for_ocr": True},
    }

    formatted = format_environment_info(info, use_colors=False)
    assert "[ Sistema e Runtime ]" in formatted
    assert "[ Dependências Principais ]" in formatted
    assert "[ Tesseract OCR (Fallback Óptico) ]" in formatted
    assert "[ Resumo de Prontidão ]" in formatted
    assert "[OK]" in formatted
    assert "\033[" not in formatted
    assert "eng, por" in formatted


def test_format_environment_info_with_colors() -> None:
    info = {
        "package": {"name": "pdf-to-markdown-converter", "version": "0.1.0"},
        "python": {
            "version": "3.14.0",
            "implementation": "CPython",
            "platform": "Windows-11",
            "executable": "python.exe",
        },
        "libraries": {
            "pymupdf": {"installed": True, "version": "1.28.2"},
            "markdown": {"installed": True, "version": "3.10.3"},
            "pillow": {"installed": True, "version": "12.3.0"},
            "pytesseract": {"installed": False, "version": None},
        },
        "tesseract": {
            "is_available": False,
            "binary_path": None,
            "version": None,
            "languages": [],
            "tessdata_path": None,
            "error_message": "Nao encontrado",
            "instructions": "winget install",
        },
        "status": {"ready_for_native": True, "ready_for_ocr": False},
    }

    formatted = format_environment_info(info, use_colors=True)
    assert "\033[" in formatted
    assert "[AVISO]" in formatted
    assert "Instruções:" in formatted


def test_run_info_command_default() -> None:
    out = io.StringIO()
    code = run_info_command([], stdout=out)
    assert code == InfoExitCode.SUCCESS
    text = out.getvalue()
    assert "PDF to Markdown Converter" in text
    assert "[ Sistema e Runtime ]" in text


def test_run_info_command_json() -> None:
    out = io.StringIO()
    code = run_info_command(["--json"], stdout=out)
    assert code == InfoExitCode.SUCCESS
    parsed = json.loads(out.getvalue())
    assert parsed["package"]["name"] == "pdf-to-markdown-converter"
    assert "libraries" in parsed
    assert "tesseract" in parsed


def test_run_info_command_colors_flags() -> None:
    out_color = io.StringIO()
    code_color = run_info_command(["--color"], stdout=out_color)
    assert code_color == InfoExitCode.SUCCESS
    assert "\033[" in out_color.getvalue()

    out_no_color = io.StringIO()
    code_no_color = run_info_command(["--no-color"], stdout=out_no_color)
    assert code_no_color == InfoExitCode.SUCCESS
    assert "\033[" not in out_no_color.getvalue()


def test_run_info_command_strict_available() -> None:
    mock_diag = TesseractDiagnostics(
        is_available=True,
        binary_path="tesseract",
        version="5.0",
        available_languages=("eng",),
    )
    with patch(
        "pdf_to_markdown_converter.cli.info.get_tesseract_diagnostics",
        return_value=mock_diag,
    ):
        out = io.StringIO()
        code = run_info_command(["--strict"], stdout=out)
        assert code == InfoExitCode.SUCCESS


def test_run_info_command_strict_unavailable() -> None:
    mock_diag = TesseractDiagnostics(
        is_available=False,
        error_message="Nao instalado",
    )
    with patch(
        "pdf_to_markdown_converter.cli.info.get_tesseract_diagnostics",
        return_value=mock_diag,
    ):
        out = io.StringIO()
        code = run_info_command(["--strict"], stdout=out)
        assert code == InfoExitCode.FAILURE


def test_run_info_command_native_failure() -> None:
    with patch("pdf_to_markdown_converter.cli.info._get_pymupdf_version", return_value=None):
        out = io.StringIO()
        code = run_info_command([], stdout=out)
        assert code == InfoExitCode.FAILURE


def test_run_info_command_help() -> None:
    out = io.StringIO()
    code = run_info_command(["--help"], stdout=out)
    assert code == 0
    assert "Inspeciona e exibe o status" in out.getvalue()


def test_run_info_command_custom_tesseract_cmd() -> None:
    with patch("pdf_to_markdown_converter.cli.info.get_tesseract_diagnostics") as mock_diag:
        mock_diag.return_value = TesseractDiagnostics(is_available=True, version="5.0")
        out = io.StringIO()
        custom_cmd = r"C:\Custom\tesseract.exe"
        run_info_command(["--tesseract-cmd", custom_cmd], stdout=out)
        mock_diag.assert_called_once_with(Path(custom_cmd))
