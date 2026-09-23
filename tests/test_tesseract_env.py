from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock, patch
import pytest

from pdf_to_markdown_converter.core.tesseract_env import (
    TesseractDiagnostics,
    TesseractError,
    TesseractExecutionError,
    TesseractNotFoundError,
    _is_executable_file,
    clear_tesseract_cache,
    configure_pytesseract,
    detect_tessdata_path,
    ensure_tesseract_available,
    get_default_search_paths,
    get_installation_instructions,
    get_tesseract_diagnostics,
    query_tesseract_languages,
    query_tesseract_version,
    resolve_tesseract_binary,
)


@pytest.fixture(autouse=True)
def _reset_tesseract_cache_fixture():
    clear_tesseract_cache()
    yield
    clear_tesseract_cache()


def test_diagnostics_dataclass_membership_and_immutability():
    diag = TesseractDiagnostics(
        is_available=True,
        binary_path="/usr/bin/tesseract",
        version="5.3.3",
        available_languages=("eng", "por", "osd"),
    )
    assert diag.is_available is True
    assert diag.has_language("por") is True
    assert diag.has_language("POR") is True
    assert diag.has_language("fra") is False

    ok, missing = diag.has_languages(["eng", "por"])
    assert ok is True
    assert missing == ()

    ok, missing = diag.has_languages(["por", "deu", "fra"])
    assert ok is False
    assert missing == ("deu", "fra")

    with pytest.raises(Exception):
        diag.is_available = False  # type: ignore[misc]


def test_installation_instructions_per_platform():
    win_inst = get_installation_instructions("win32")
    assert "winget install" in win_inst
    assert "Portuguese" in win_inst

    mac_inst = get_installation_instructions("darwin")
    assert "brew install" in mac_inst

    linux_inst = get_installation_instructions("linux")
    assert "apt-get install" in linux_inst


def test_get_default_search_paths():
    win_paths = get_default_search_paths("win32")
    assert any("Tesseract-OCR" in str(p) for p in win_paths)
    assert all(p.suffix == ".exe" for p in win_paths)

    mac_paths = get_default_search_paths("darwin")
    assert Path("/opt/homebrew/bin/tesseract") in mac_paths

    linux_paths = get_default_search_paths("linux")
    assert Path("/usr/bin/tesseract") in linux_paths


def test_is_executable_file(tmp_path: Path):
    fake_file = tmp_path / "app.exe"
    fake_file.write_text("dummy")
    with patch("os.access", return_value=True):
        assert _is_executable_file(fake_file) is True

    non_file = tmp_path / "subfolder"
    non_file.mkdir()
    assert _is_executable_file(non_file) is False

    non_existent = tmp_path / "missing.exe"
    assert _is_executable_file(non_existent) is False


def test_resolve_tesseract_binary_precedence(tmp_path: Path):
    custom_bin = tmp_path / "custom" / "tesseract.exe"
    custom_bin.parent.mkdir(parents=True)
    custom_bin.write_text("custom")

    env_bin = tmp_path / "env" / "tesseract.exe"
    env_bin.parent.mkdir(parents=True)
    env_bin.write_text("env")

    with patch("pdf_to_markdown_converter.core.tesseract_env._is_executable_file", return_value=True):
        # 1. Custom cmd has highest priority
        res = resolve_tesseract_binary(custom_bin)
        assert res == custom_bin.resolve()

        # Custom pointing to non-existent returns None directly
        with patch("pdf_to_markdown_converter.core.tesseract_env._is_executable_file", return_value=False):
            assert resolve_tesseract_binary(tmp_path / "missing.exe") is None

        # 2. TESSERACT_CMD env var has second priority
        with patch.dict(os.environ, {"TESSERACT_CMD": str(env_bin)}):
            assert resolve_tesseract_binary() == env_bin.resolve()

        # 3. PATH discovery via shutil.which
        with patch.dict(os.environ, {"TESSERACT_CMD": ""}):
            with patch("shutil.which", return_value=str(custom_bin)):
                assert resolve_tesseract_binary() == custom_bin.resolve()

            # 4. Default OS search paths fallback
            with patch("shutil.which", return_value=None):
                with patch(
                    "pdf_to_markdown_converter.core.tesseract_env.get_default_search_paths",
                    return_value=[env_bin],
                ):
                    assert resolve_tesseract_binary() == env_bin.resolve()

                # 5. Nothing found returns None
                with patch(
                    "pdf_to_markdown_converter.core.tesseract_env.get_default_search_paths",
                    return_value=[],
                ):
                    assert resolve_tesseract_binary() is None


def test_query_tesseract_version():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout="tesseract 5.3.3.20231005\n leptonica-1.83.1\n",
            stderr="",
        )
        ver = query_tesseract_version(Path("/fake/tesseract"))
        assert ver == "5.3.3.20231005"

    clear_tesseract_cache()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout="",
            stderr="tesseract v4.1.1\n",
        )
        assert query_tesseract_version(Path("/fake/tesseract")) == "4.1.1"

    clear_tesseract_cache()
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 5)):
        assert query_tesseract_version(Path("/fake/tesseract")) is None

    clear_tesseract_cache()
    with patch("subprocess.run", side_effect=OSError("permission denied")):
        assert query_tesseract_version(Path("/fake/tesseract")) is None


def test_query_tesseract_languages():
    raw_output = """List of available languages (4):
eng
osd
por
srp
"""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=raw_output, stderr="")
        langs = query_tesseract_languages(Path("/fake/tesseract"))
        assert langs == ("eng", "osd", "por", "srp")

    clear_tesseract_cache()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", stderr="Error opening data file")
        assert query_tesseract_languages(Path("/fake/tesseract")) == ()

    clear_tesseract_cache()
    with patch("subprocess.run", side_effect=subprocess.SubprocessError("failed")):
        assert query_tesseract_languages(Path("/fake/tesseract")) == ()


def test_detect_tessdata_path(tmp_path: Path):
    tess_dir = tmp_path / "tessdata"
    tess_dir.mkdir()

    with patch.dict(os.environ, {"TESSDATA_PREFIX": str(tess_dir)}):
        assert detect_tessdata_path() == str(tess_dir.resolve())

    with patch.dict(os.environ, {"TESSDATA_PREFIX": ""}):
        bin_path = tmp_path / "bin" / "tesseract.exe"
        bin_tessdata = tmp_path / "bin" / "tessdata"
        bin_tessdata.mkdir(parents=True)
        assert detect_tessdata_path(bin_path) == str(bin_tessdata.resolve())

        assert detect_tessdata_path(tmp_path / "other" / "tesseract.exe") is None


def test_configure_pytesseract(tmp_path: Path):
    fake_bin = tmp_path / "tesseract.exe"
    fake_bin.write_text("binary")

    with patch("pdf_to_markdown_converter.core.tesseract_env.resolve_tesseract_binary", return_value=fake_bin):
        mock_pytesseract = MagicMock()
        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract}):
            ok = configure_pytesseract()
            assert ok is True
            assert mock_pytesseract.pytesseract.tesseract_cmd == str(fake_bin)

    with patch("pdf_to_markdown_converter.core.tesseract_env.resolve_tesseract_binary", return_value=None):
        assert configure_pytesseract() is False


def test_get_tesseract_diagnostics_unavailable():
    with patch("pdf_to_markdown_converter.core.tesseract_env.resolve_tesseract_binary", return_value=None):
        diag = get_tesseract_diagnostics()
        assert diag.is_available is False
        assert diag.binary_path is None
        assert diag.version is None
        assert "nao foi encontrado" in (diag.error_message or "")
        assert diag.instructions is not None


def test_get_tesseract_diagnostics_version_failed(tmp_path: Path):
    fake_bin = tmp_path / "tesseract.exe"
    with patch("pdf_to_markdown_converter.core.tesseract_env.resolve_tesseract_binary", return_value=fake_bin):
        with patch("pdf_to_markdown_converter.core.tesseract_env.query_tesseract_version", return_value=None):
            diag = get_tesseract_diagnostics()
            assert diag.is_available is False
            assert diag.binary_path == str(fake_bin)
            assert "falhou" in (diag.error_message or "")


def test_get_tesseract_diagnostics_success(tmp_path: Path):
    fake_bin = tmp_path / "tesseract.exe"
    with patch("pdf_to_markdown_converter.core.tesseract_env.resolve_tesseract_binary", return_value=fake_bin):
        with patch("pdf_to_markdown_converter.core.tesseract_env.query_tesseract_version", return_value="5.3.3"):
            with patch(
                "pdf_to_markdown_converter.core.tesseract_env.query_tesseract_languages",
                return_value=("eng", "por"),
            ):
                with patch("pdf_to_markdown_converter.core.tesseract_env.detect_tessdata_path", return_value="/fake/tessdata"):
                    with patch("pdf_to_markdown_converter.core.tesseract_env.configure_pytesseract", return_value=True):
                        diag = get_tesseract_diagnostics()
                        assert diag.is_available is True
                        assert diag.binary_path == str(fake_bin)
                        assert diag.version == "5.3.3"
                        assert diag.available_languages == ("eng", "por")
                        assert diag.tessdata_path == "/fake/tessdata"
                        assert diag.error_message is None
                        assert diag.instructions is None


def test_ensure_tesseract_available_raising():
    with patch(
        "pdf_to_markdown_converter.core.tesseract_env.get_tesseract_diagnostics",
        return_value=TesseractDiagnostics(
            is_available=False,
            error_message="Executable missing",
            instructions="Run installer",
        ),
    ):
        with pytest.raises(TesseractNotFoundError, match="Executable missing"):
            ensure_tesseract_available()

    with patch(
        "pdf_to_markdown_converter.core.tesseract_env.get_tesseract_diagnostics",
        return_value=TesseractDiagnostics(
            is_available=True,
            binary_path="/bin/tesseract",
            version="5.3.3",
            available_languages=("eng",),
        ),
    ):
        with pytest.raises(TesseractNotFoundError, match="falta\\(m\\) pacote\\(s\\) de idioma: por"):
            ensure_tesseract_available(required_languages=["por", "eng"])

        diag = ensure_tesseract_available(required_languages=["eng"])
        assert diag.is_available is True


def test_real_system_smoke_test():
    diag = get_tesseract_diagnostics()
    assert isinstance(diag, TesseractDiagnostics)
    assert isinstance(diag.is_available, bool)
    if diag.is_available:
        assert diag.version is not None
        assert diag.binary_path is not None
    else:
        assert diag.instructions is not None


def test_tesseract_queries_and_diagnostics_cache_repetition():
    binary = Path("/fake/bin/tesseract")

    # 1. query_tesseract_version caching
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="tesseract 5.3.3\n", stderr="")
        v1 = query_tesseract_version(binary)
        v2 = query_tesseract_version(binary)
        assert v1 == "5.3.3"
        assert v2 == "5.3.3"
        assert mock_run.call_count == 1

    # 2. query_tesseract_languages caching
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="por\neng\n", stderr="")
        l1 = query_tesseract_languages(binary)
        l2 = query_tesseract_languages(binary)
        assert l1 == ("eng", "por")
        assert l2 == ("eng", "por")
        assert mock_run.call_count == 1

    # 3. get_tesseract_diagnostics caching
    with patch("pdf_to_markdown_converter.core.tesseract_env.resolve_tesseract_binary", return_value=binary):
        d1 = get_tesseract_diagnostics(binary)
        d2 = get_tesseract_diagnostics(binary)
        assert d1 is d2
        assert d1.version == "5.3.3"


def test_clear_tesseract_cache_resets_caches():
    binary = Path("/fake/bin/tesseract")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="tesseract 5.0.0\n", stderr="")
        assert query_tesseract_version(binary) == "5.0.0"
        assert mock_run.call_count == 1

        clear_tesseract_cache()

        mock_run.return_value = MagicMock(stdout="tesseract 5.1.0\n", stderr="")
        assert query_tesseract_version(binary) == "5.1.0"
        assert mock_run.call_count == 2
