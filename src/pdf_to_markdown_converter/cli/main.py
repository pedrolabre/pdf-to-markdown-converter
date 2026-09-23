from __future__ import annotations

import argparse
import contextlib
from enum import Enum
import os
from pathlib import Path
import sys
from typing import Callable, Sequence, TextIO

from pdf_to_markdown_converter.cli.info import run_info_command
from pdf_to_markdown_converter.core.ocr_extractor import DEFAULT_DPI, DEFAULT_LANG
from pdf_to_markdown_converter.core.pdf_reader import (
    CorruptedPdfError,
    EmptyPdfError,
    EncryptedPdfError,
    PdfNotFoundError,
)
from pdf_to_markdown_converter.core.pipeline import (
    InvalidOptionError,
    PipelineError,
    PipelineStage,
    convert_pdf,
)
from pdf_to_markdown_converter.core.tesseract_env import (
    TesseractNotFoundError,
    configure_pytesseract,
)
from pdf_to_markdown_converter.domain.models import ExtractionResult
from pdf_to_markdown_converter.exporters.markdown_exporter import DestinationExistsError


class CliExitCode(int, Enum):
    SUCCESS = 0
    GENERAL_ERROR = 1
    FILE_NOT_FOUND = 2
    INVALID_PDF = 3
    TESSERACT_NOT_FOUND = 4
    DESTINATION_EXISTS = 5
    ENCRYPTION_ERROR = 6
    INTERRUPTED = 130


ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_GREEN = "\033[32m"
ANSI_YELLOW = "\033[33m"
ANSI_RED = "\033[31m"
ANSI_CYAN = "\033[36m"


def _colorize(text: str, code: str, enabled: bool) -> str:
    return f"{code}{text}{ANSI_RESET}" if enabled else text


def _get_package_version() -> str:
    try:
        from pdf_to_markdown_converter import __version__

        return __version__
    except ImportError:
        return "0.1.0"


def _parse_formats(raw: Sequence[str] | None) -> tuple[str, ...]:
    if not raw:
        return ("md", "html")
    result: list[str] = []
    for item in raw:
        for part in item.split(","):
            clean = part.strip().lower().lstrip(".")
            if clean and clean not in result:
                result.append(clean)
    return tuple(result) or ("md", "html")


def _print_error(message: str, stream: TextIO, use_colors: bool) -> None:
    stream.write(f"{_colorize('[FALHA]', ANSI_RED, use_colors)} {message}\n")
    stream.flush()


def _print_warning(message: str, stream: TextIO, use_colors: bool) -> None:
    stream.write(f"{_colorize('[AVISO]', ANSI_YELLOW, use_colors)} {message}\n")
    stream.flush()


def _print_success(result: ExtractionResult, stream: TextIO, use_colors: bool) -> None:
    ok_tag = _colorize("[OK]", ANSI_GREEN, use_colors)
    sep = _colorize("=" * 60, ANSI_BOLD, use_colors)
    stream.write(f"{sep}\n{ok_tag} Conversão concluída com sucesso em {result.execution_time_seconds:.2f}s\n")
    stream.write(f"  Origem:      {result.source_path}\n  Estratégia:  {result.strategy_used.value}\n")
    stream.write(f"  Páginas:     {result.pages_processed}\n")
    if result.markdown_path:
        stream.write(f"  Markdown:    {result.markdown_path}\n")
    if result.html_path:
        stream.write(f"  HTML5:       {result.html_path}\n")
    stream.write(f"{sep}\n")
    stream.flush()


def _create_progress_callback(
    stream: TextIO,
    use_colors: bool,
) -> Callable[[PipelineStage, float, str], None]:
    def cb(stage: PipelineStage, progress: float, message: str = "") -> None:
        tag = _colorize(f"[{int(progress * 100):3d}%]", ANSI_CYAN, use_colors)
        stream.write(f"  {tag} {message or stage.value.capitalize()}\n")
        stream.flush()

    return cb


def build_main_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--color", action="store_true", default=None, help="Força cores ANSI.")
    common.add_argument("--no-color", action="store_true", help="Desativa cores ANSI.")
    common.add_argument("--debug", action="store_true", help="Exibe tracebacks detalhados.")

    parser = argparse.ArgumentParser(
        prog="pdf-to-markdown",
        parents=[common],
        description="Ferramenta local-first para converter documentos PDF em Markdown estruturado e HTML5.",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"pdf-to-markdown v{_get_package_version()}",
    )

    subparsers = parser.add_subparsers(dest="subcommand", title="subcomandos")

    extract_p = subparsers.add_parser("extract", parents=[common], help="Converte PDF em Markdown e HTML5.")
    extract_p.add_argument("pdf_path", type=str, help="Caminho do arquivo PDF.")
    extract_p.add_argument("-o", "--output-dir", type=str, default=None, help="Diretório de saída.")
    extract_p.add_argument("--output-path", type=str, default=None, help="Caminho base de saída específico.")
    extract_p.add_argument("--format", type=str, action="append", default=None, help="Formatos (md, html).")
    extract_p.add_argument("--force-ocr", action="store_true", help="Força extração óptica via OCR.")
    extract_p.add_argument("--dpi", type=int, default=DEFAULT_DPI, help="DPI para OCR (padrão: 300).")
    extract_p.add_argument("--lang", type=str, default=DEFAULT_LANG, help="Idiomas OCR (padrão: por+eng).")
    extract_p.add_argument("--no-overwrite", action="store_true", help="Impede sobrescrever saídas.")
    extract_p.add_argument("--password", type=str, default="", help="Senha para PDF protegido.")
    extract_p.add_argument("--tesseract-cmd", type=str, default=None, help="Caminho do executável Tesseract.")
    extract_p.add_argument("-q", "--quiet", action="store_true", help="Suprime mensagens informativas.")

    info_p = subparsers.add_parser("info", parents=[common], help="Exibe diagnóstico de ambiente.")
    info_p.add_argument("--json", action="store_true", help="Exibe informações em formato JSON.")
    info_p.add_argument("--strict", action="store_true", help="Retorna código 1 se dependências faltarem.")
    info_p.add_argument("--tesseract-cmd", type=str, default=None, help="Caminho do executável Tesseract.")

    return parser


def _handle_info_command(
    args: argparse.Namespace,
    out: TextIO,
    err: TextIO,
) -> int:
    info_argv: list[str] = []
    if getattr(args, "json", False):
        info_argv.append("--json")
    if getattr(args, "strict", False):
        info_argv.append("--strict")
    if getattr(args, "tesseract_cmd", None):
        info_argv.extend(["--tesseract-cmd", str(args.tesseract_cmd)])
    if getattr(args, "color", False):
        info_argv.append("--color")
    if getattr(args, "no_color", False):
        info_argv.append("--no-color")
    return run_info_command(info_argv, stdout=out, stderr=err)


def _handle_extract_command(
    args: argparse.Namespace,
    out: TextIO,
    err: TextIO,
    use_colors: bool,
) -> int:
    try:
        if getattr(args, "tesseract_cmd", None):
            configure_pytesseract(args.tesseract_cmd)

        formats = _parse_formats(args.format)
        cb = _create_progress_callback(err, use_colors) if not args.quiet else None

        result = convert_pdf(
            args.pdf_path,
            output_dir=args.output_dir,
            output_path=args.output_path,
            force_ocr=args.force_ocr,
            dpi=args.dpi,
            lang=args.lang,
            overwrite=not args.no_overwrite,
            export_formats=formats,
            password=args.password,
            progress_callback=cb,
        )

        if not args.quiet:
            _print_success(result, out, use_colors)

        return int(CliExitCode.SUCCESS)

    except PdfNotFoundError:
        _print_error(f"Arquivo PDF não encontrado: {args.pdf_path}", err, use_colors)
        return int(CliExitCode.FILE_NOT_FOUND)
    except EmptyPdfError:
        _print_error(f"O arquivo PDF está vazio (0 bytes): {args.pdf_path}", err, use_colors)
        return int(CliExitCode.INVALID_PDF)
    except CorruptedPdfError:
        _print_error(f"O documento não é um PDF válido ou está corrompido: {args.pdf_path}", err, use_colors)
        return int(CliExitCode.INVALID_PDF)
    except EncryptedPdfError:
        _print_error("O documento PDF está protegido por senha. Forneça a senha com --password.", err, use_colors)
        return int(CliExitCode.ENCRYPTION_ERROR)
    except TesseractNotFoundError as exc:
        _print_error(str(exc), err, use_colors)
        return int(CliExitCode.TESSERACT_NOT_FOUND)
    except (DestinationExistsError, FileExistsError) as exc:
        _print_error(str(exc), err, use_colors)
        return int(CliExitCode.DESTINATION_EXISTS)
    except (InvalidOptionError, ValueError) as exc:
        _print_error(f"Configuração inválida: {exc}", err, use_colors)
        return int(CliExitCode.GENERAL_ERROR)
    except PipelineError as exc:
        _print_error(f"Erro no pipeline: {exc}", err, use_colors)
        return int(CliExitCode.GENERAL_ERROR)
    except KeyboardInterrupt:
        _print_warning("Operação cancelada pelo usuário.", err, use_colors)
        return int(CliExitCode.INTERRUPTED)
    except Exception as exc:
        if getattr(args, "debug", False) or os.environ.get("PDF2MD_DEBUG"):
            raise
        _print_error(f"Erro inesperado: {exc}", err, use_colors)
        return int(CliExitCode.GENERAL_ERROR)


def run_cli(
    argv: Sequence[str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    out = stdout or sys.stdout
    err = stderr or sys.stderr

    raw_argv = sys.argv[1:] if argv is None else list(argv)
    if not raw_argv:
        parser = build_main_parser()
        parser.print_help(out)
        return int(CliExitCode.SUCCESS)

    first = raw_argv[0]
    if first not in ("extract", "info", "-h", "--help", "-v", "--version") and not first.startswith("-"):
        processed_argv = ["extract"] + raw_argv
    else:
        processed_argv = raw_argv

    parser = build_main_parser()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            args = parser.parse_args(args=processed_argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
        return int(CliExitCode.SUCCESS if code == 0 else CliExitCode.GENERAL_ERROR)

    if not getattr(args, "subcommand", None):
        parser.print_help(out)
        return int(CliExitCode.SUCCESS)

    if getattr(args, "no_color", False):
        use_colors = False
    elif getattr(args, "color", False):
        use_colors = True
    elif os.environ.get("NO_COLOR"):
        use_colors = False
    elif hasattr(out, "isatty") and out.isatty():
        use_colors = True
    else:
        use_colors = False

    if args.subcommand == "info":
        return _handle_info_command(args, out, err)
    if args.subcommand == "extract":
        return _handle_extract_command(args, out, err, use_colors)
    return int(CliExitCode.GENERAL_ERROR)


def main() -> None:
    code = run_cli()
    sys.exit(code)


if __name__ == "__main__":
    main()
