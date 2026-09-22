from __future__ import annotations

import argparse
import contextlib
from enum import Enum
import json
import os
from pathlib import Path
import platform
import sys
from typing import Any, Sequence, TextIO

from pdf_to_markdown_converter.core.tesseract_env import get_tesseract_diagnostics


class InfoExitCode(int, Enum):
    SUCCESS = 0
    FAILURE = 1


ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_GREEN = "\033[32m"
ANSI_YELLOW = "\033[33m"
ANSI_RED = "\033[31m"
ANSI_CYAN = "\033[36m"


def _colorize(text: str, code: str, enabled: bool) -> str:
    if not enabled:
        return text
    return f"{code}{text}{ANSI_RESET}"


def _get_package_version() -> str:
    try:
        from pdf_to_markdown_converter import __version__

        return __version__
    except ImportError:
        return "0.1.0"


def _get_lib_version(name: str, alt_name: str | None = None) -> str | None:
    candidates = (name, alt_name) if alt_name else (name,)
    for cand in candidates:
        try:
            mod = __import__(cand)
            ver = getattr(mod, "__version__", None)
            if ver:
                return str(ver)
        except ImportError:
            continue
    return None


def _get_pymupdf_version() -> str | None:
    return _get_lib_version("pymupdf", "fitz")


def _get_markdown_version() -> str | None:
    return _get_lib_version("markdown")


def _get_pillow_version() -> str | None:
    return _get_lib_version("PIL")


def _get_pytesseract_version() -> str | None:
    return _get_lib_version("pytesseract")


def get_environment_info(
    custom_tesseract_cmd: Path | str | None = None,
) -> dict[str, Any]:
    package_version = _get_package_version()
    pymupdf_ver = _get_pymupdf_version()
    markdown_ver = _get_markdown_version()
    pillow_ver = _get_pillow_version()
    pytesseract_ver = _get_pytesseract_version()

    tess_diag = get_tesseract_diagnostics(custom_tesseract_cmd)

    native_ready = pymupdf_ver is not None and markdown_ver is not None
    ocr_ready = tess_diag.is_available and pytesseract_ver is not None

    return {
        "package": {
            "name": "pdf-to-markdown-converter",
            "version": package_version,
        },
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
            "platform": platform.platform(),
            "system": platform.system(),
        },
        "libraries": {
            "pymupdf": {
                "installed": pymupdf_ver is not None,
                "version": pymupdf_ver,
            },
            "markdown": {
                "installed": markdown_ver is not None,
                "version": markdown_ver,
            },
            "pillow": {
                "installed": pillow_ver is not None,
                "version": pillow_ver,
            },
            "pytesseract": {
                "installed": pytesseract_ver is not None,
                "version": pytesseract_ver,
            },
        },
        "tesseract": {
            "is_available": tess_diag.is_available,
            "binary_path": tess_diag.binary_path,
            "version": tess_diag.version,
            "languages": list(tess_diag.available_languages),
            "tessdata_path": tess_diag.tessdata_path,
            "error_message": tess_diag.error_message,
            "instructions": tess_diag.instructions,
        },
        "status": {
            "ready_for_native": native_ready,
            "ready_for_ocr": ocr_ready,
        },
    }


def format_environment_info(info: dict[str, Any], use_colors: bool = False) -> str:
    lines: list[str] = []
    sep = "=" * 60

    ok_tag = _colorize("[OK]", ANSI_GREEN, use_colors)
    warn_tag = _colorize("[AVISO]", ANSI_YELLOW, use_colors)
    fail_tag = _colorize("[FALHA]", ANSI_RED, use_colors)

    lines.append(_colorize(sep, ANSI_BOLD, use_colors))
    lines.append(_colorize("        PDF to Markdown Converter - Diagnóstico", ANSI_BOLD, use_colors))
    lines.append(_colorize(sep, ANSI_BOLD, use_colors))

    pkg = info.get("package", {})
    py = info.get("python", {})
    lines.append(_colorize("[ Sistema e Runtime ]", ANSI_CYAN, use_colors))
    lines.append(f"  Pacote:          {pkg.get('name', '')} v{pkg.get('version', '')}")
    lines.append(f"  Python:          {py.get('version', '')} ({py.get('implementation', '')})")
    lines.append(f"  Plataforma:      {py.get('platform', '')}")
    lines.append(f"  Executável:      {py.get('executable', '')}")
    lines.append("")

    libs = info.get("libraries", {})
    lines.append(_colorize("[ Dependências Principais ]", ANSI_CYAN, use_colors))
    for lib_key, label in [
        ("pymupdf", "PyMuPDF"),
        ("markdown", "Markdown"),
        ("pillow", "Pillow (PIL)"),
        ("pytesseract", "pytesseract"),
    ]:
        lib_data = libs.get(lib_key, {})
        installed = lib_data.get("installed", False)
        ver = lib_data.get("version")
        tag = ok_tag if installed else (warn_tag if lib_key == "pytesseract" else fail_tag)
        desc = f"v{ver}" if ver else "não instalado"
        lines.append(f"  {label:<16} {desc:<18} {tag}")
    lines.append("")

    tess = info.get("tesseract", {})
    lines.append(_colorize("[ Tesseract OCR (Fallback Óptico) ]", ANSI_CYAN, use_colors))
    if tess.get("is_available", False):
        langs = tess.get("languages", [])
        langs_str = ", ".join(langs) if langs else "nenhum detectado"
        lines.append(f"  Status:          Disponível {ok_tag}")
        lines.append(f"  Binário:         {tess.get('binary_path', 'N/A')}")
        lines.append(f"  Versão:          {tess.get('version', 'N/A')}")
        lines.append(f"  Tessdata:        {tess.get('tessdata_path') or 'Padrão'}")
        lines.append(f"  Idiomas:         {langs_str} ({len(langs)} disponíveis)")
    else:
        lines.append(f"  Status:          Não disponível {warn_tag}")
        if tess.get("binary_path"):
            lines.append(f"  Binário:         {tess.get('binary_path')}")
        if tess.get("error_message"):
            lines.append(f"  Detalhe:         {tess.get('error_message')}")
        if tess.get("instructions"):
            lines.append(f"  Instruções:      {tess.get('instructions')}")
    lines.append("")

    status = info.get("status", {})
    lines.append(_colorize("[ Resumo de Prontidão ]", ANSI_CYAN, use_colors))
    native_ok = status.get("ready_for_native", False)
    ocr_ok = status.get("ready_for_ocr", False)
    lines.append(
        f"  Extração Nativa: {'Pronta' if native_ok else 'Indisponível'} "
        f"{ok_tag if native_ok else fail_tag}"
    )
    lines.append(
        f"  Extração OCR:    {'Pronta' if ocr_ok else 'Indisponível (fallback desativado)'} "
        f"{ok_tag if ocr_ok else warn_tag}"
    )
    lines.append(_colorize(sep, ANSI_BOLD, use_colors))

    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="info",
        description="Inspeciona e exibe o status do ambiente local, versões e Tesseract OCR.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Exibe as informações em formato JSON estruturado.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Retorna código 1 caso o Tesseract OCR ou dependências nativas estejam ausentes.",
    )
    parser.add_argument(
        "--color",
        action="store_true",
        default=None,
        help="Força exibição com cores ANSI.",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Desativa cores ANSI.",
    )
    parser.add_argument(
        "--tesseract-cmd",
        type=str,
        default=None,
        help="Caminho customizado para o executável do Tesseract.",
    )
    return parser


def run_info_command(
    argv: Sequence[str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    out = stdout or sys.stdout
    err = stderr or sys.stderr
    parser = _build_parser()

    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            args = parser.parse_args(args=argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
        return code

    custom_tess = Path(args.tesseract_cmd) if args.tesseract_cmd else None
    info = get_environment_info(custom_tesseract_cmd=custom_tess)

    if args.json:
        out.write(json.dumps(info, indent=2, ensure_ascii=False) + "\n")
    else:
        if args.no_color:
            use_colors = False
        elif args.color:
            use_colors = True
        elif os.environ.get("NO_COLOR"):
            use_colors = False
        elif hasattr(out, "isatty") and out.isatty():
            use_colors = True
        else:
            use_colors = False

        formatted = format_environment_info(info, use_colors=use_colors)
        out.write(formatted + "\n")

    if not info["status"]["ready_for_native"]:
        return InfoExitCode.FAILURE

    if args.strict and not info["status"]["ready_for_ocr"]:
        return InfoExitCode.FAILURE

    return InfoExitCode.SUCCESS
