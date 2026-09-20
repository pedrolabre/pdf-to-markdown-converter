from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import subprocess
import sys


class TesseractError(Exception):
    """Excecao base para operacoes relacionadas ao Tesseract OCR."""


class TesseractNotFoundError(TesseractError):
    """Excecao levantada quando o executavel ou pacotes de idiomas nao sao encontrados."""


class TesseractExecutionError(TesseractError):
    """Excecao levantada quando a execucao do Tesseract falha criticamente."""


@dataclass(frozen=True)
class TesseractDiagnostics:
    is_available: bool
    binary_path: str | None = None
    version: str | None = None
    available_languages: tuple[str, ...] = ()
    tessdata_path: str | None = None
    error_message: str | None = None
    instructions: str | None = None

    def has_language(self, lang: str) -> bool:
        target = lang.strip().lower()
        return any(installed.strip().lower() == target for installed in self.available_languages)

    def has_languages(self, langs: Iterable[str]) -> tuple[bool, tuple[str, ...]]:
        missing = tuple(l for l in langs if not self.has_language(l))
        return (len(missing) == 0, missing)


def get_installation_instructions(platform_name: str | None = None) -> str:
    target_platform = platform_name or sys.platform
    if target_platform == "win32":
        return (
            "Tesseract OCR nao encontrado. No Windows, instale via "
            "'winget install UB-Mannheim.TesseractOCR' ou baixe o instalador em "
            "https://github.com/UB-Mannheim/tesseract/wiki. "
            "Certifique-se de marcar os pacotes de idiomas 'Portuguese' e 'English' durante a instalacao."
        )
    if target_platform == "darwin":
        return (
            "Tesseract OCR nao encontrado. No macOS, instale via "
            "'brew install tesseract tesseract-lang'."
        )
    return (
        "Tesseract OCR nao encontrado. No Linux (Debian/Ubuntu), instale via "
        "'sudo apt-get update && sudo apt-get install -y tesseract-ocr tesseract-ocr-por tesseract-ocr-eng'."
    )


def get_default_search_paths(platform_name: str | None = None) -> list[Path]:
    target_platform = platform_name or sys.platform
    paths: list[Path] = []

    if target_platform == "win32":
        prog_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        prog_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local_app_data = os.environ.get("LOCALAPPDATA", "")

        candidates = [
            Path(prog_files) / "Tesseract-OCR" / "tesseract.exe",
            Path(prog_files_x86) / "Tesseract-OCR" / "tesseract.exe",
        ]
        if local_app_data:
            candidates.append(Path(local_app_data) / "Programs" / "Tesseract-OCR" / "tesseract.exe")

        for candidate in candidates:
            if candidate not in paths:
                paths.append(candidate)
    elif target_platform == "darwin":
        candidates = [
            Path("/opt/homebrew/bin/tesseract"),
            Path("/usr/local/bin/tesseract"),
            Path("/opt/local/bin/tesseract"),
            Path("/usr/bin/tesseract"),
        ]
        for candidate in candidates:
            if candidate not in paths:
                paths.append(candidate)
    else:
        candidates = [
            Path("/usr/bin/tesseract"),
            Path("/usr/local/bin/tesseract"),
            Path("/snap/bin/tesseract"),
            Path("/usr/bin/tesseract-ocr"),
        ]
        for candidate in candidates:
            if candidate not in paths:
                paths.append(candidate)

    return paths


def _is_executable_file(path: Path) -> bool:
    try:
        if not path.is_file():
            return False
        if sys.platform == "win32":
            return path.suffix.lower() in (".exe", ".cmd", ".bat")
        return os.access(path, os.X_OK)
    except (OSError, PermissionError):
        return False


def resolve_tesseract_binary(custom_cmd: Path | str | None = None) -> Path | None:
    if custom_cmd:
        custom_path = Path(os.path.expandvars(os.path.expanduser(str(custom_cmd))))
        if _is_executable_file(custom_path):
            return custom_path.resolve()
        return None

    env_cmd = os.environ.get("TESSERACT_CMD")
    if env_cmd:
        env_path = Path(os.path.expandvars(os.path.expanduser(env_cmd.strip())))
        if _is_executable_file(env_path):
            return env_path.resolve()

    which_name = "tesseract.exe" if sys.platform == "win32" else "tesseract"
    which_path = shutil.which(which_name) or shutil.which("tesseract")
    if which_path:
        resolved = Path(which_path)
        if _is_executable_file(resolved):
            return resolved.resolve()

    for default_path in get_default_search_paths():
        if _is_executable_file(default_path):
            return default_path.resolve()

    return None


def query_tesseract_version(binary_path: Path | str, timeout: float = 5.0) -> str | None:
    try:
        cmd = [str(binary_path), "--version"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        output = f"{res.stdout}\n{res.stderr}".strip()
        match = re.search(r"tesseract\s+v?(\d+\.\d+[\.\d\w\-]*)", output, re.IGNORECASE)
        if match:
            return match.group(1)
        first_line = output.splitlines()[0].strip() if output else ""
        return first_line or None
    except (subprocess.SubprocessError, OSError, UnicodeDecodeError):
        return None


def query_tesseract_languages(binary_path: Path | str, timeout: float = 5.0) -> tuple[str, ...]:
    try:
        cmd = [str(binary_path), "--list-langs"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        output = f"{res.stdout}\n{res.stderr}".strip()
        langs: list[str] = []
        for line in output.splitlines():
            cleaned = line.strip()
            if not cleaned or cleaned.lower().startswith("list of available languages"):
                continue
            if re.match(r"^[a-zA-Z0-9_\-]+$", cleaned):
                langs.append(cleaned)
        return tuple(sorted(set(langs)))
    except (subprocess.SubprocessError, OSError, UnicodeDecodeError):
        return ()


def detect_tessdata_path(binary_path: Path | str | None = None) -> str | None:
    env_prefix = os.environ.get("TESSDATA_PREFIX")
    if env_prefix:
        env_path = Path(os.path.expandvars(os.path.expanduser(env_prefix.strip())))
        if env_path.is_dir():
            return str(env_path.resolve())

    if binary_path:
        bin_dir = Path(binary_path).resolve().parent
        candidate = bin_dir / "tessdata"
        if candidate.is_dir():
            return str(candidate.resolve())

    common_unix = [
        Path("/usr/share/tesseract-ocr/5/tessdata"),
        Path("/usr/share/tesseract-ocr/4.00/tessdata"),
        Path("/usr/share/tessdata"),
        Path("/usr/local/share/tessdata"),
        Path("/opt/homebrew/share/tessdata"),
    ]
    for unix_dir in common_unix:
        if unix_dir.is_dir():
            return str(unix_dir.resolve())

    return None


def configure_pytesseract(binary_path: Path | str | None = None) -> bool:
    resolved = Path(binary_path) if binary_path else resolve_tesseract_binary()
    if not resolved:
        return False

    try:
        import pytesseract  # type: ignore

        pytesseract.pytesseract.tesseract_cmd = str(resolved)
        return True
    except (ImportError, AttributeError):
        return False


def get_tesseract_diagnostics(custom_cmd: Path | str | None = None) -> TesseractDiagnostics:
    binary = resolve_tesseract_binary(custom_cmd)
    if not binary:
        return TesseractDiagnostics(
            is_available=False,
            instructions=get_installation_instructions(),
            error_message="Executavel do Tesseract nao foi encontrado no sistema.",
        )

    version = query_tesseract_version(binary)
    if not version:
        return TesseractDiagnostics(
            is_available=False,
            binary_path=str(binary),
            instructions=get_installation_instructions(),
            error_message="Binario encontrado, mas a consulta de versao (--version) falhou.",
        )

    languages = query_tesseract_languages(binary)
    tessdata = detect_tessdata_path(binary)
    configure_pytesseract(binary)

    return TesseractDiagnostics(
        is_available=True,
        binary_path=str(binary),
        version=version,
        available_languages=languages,
        tessdata_path=tessdata,
        error_message=None,
        instructions=None,
    )


def ensure_tesseract_available(
    custom_cmd: Path | str | None = None,
    required_languages: Iterable[str] | None = None,
) -> TesseractDiagnostics:
    diag = get_tesseract_diagnostics(custom_cmd)
    if not diag.is_available:
        details = diag.error_message or "Tesseract OCR indisponivel."
        instructions = f"\n{diag.instructions}" if diag.instructions else ""
        raise TesseractNotFoundError(f"{details}{instructions}")

    if required_languages:
        ok, missing = diag.has_languages(required_languages)
        if not ok:
            missing_str = ", ".join(missing)
            instructions = f"\n{get_installation_instructions()}"
            raise TesseractNotFoundError(
                f"Tesseract OCR disponivel, mas falta(m) pacote(s) de idioma: {missing_str}.{instructions}"
            )

    return diag
