from __future__ import annotations

import os
from pathlib import Path
import queue
import time
import tkinter as tk
from unittest.mock import MagicMock, patch

import pymupdf
import pytest

from pdf_to_markdown_converter.core.pdf_reader import (
    CorruptedPdfError,
    EmptyPdfError,
    EncryptedPdfError,
    PdfNotFoundError,
)
from pdf_to_markdown_converter.core.pipeline import PipelineStage
from pdf_to_markdown_converter.core.tesseract_env import TesseractNotFoundError
from pdf_to_markdown_converter.domain.models import ExtractionResult, ExtractionStrategy
from pdf_to_markdown_converter.exporters.markdown_exporter import DestinationExistsError
from pdf_to_markdown_converter.gui import (
    ConverterApp,
    launch_gui,
    main,
    open_in_system,
)


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 70), "# Documento de Teste GUI")
    pdf_path = tmp_path / "teste_gui.pdf"
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture(scope="module")
def tk_app_root():
    try:
        root = tk.Tk()
        root.withdraw()
        yield root
        try:
            root.destroy()
        except Exception:
            pass
    except tk.TclError:
        pytest.skip("Ambiente Tkinter gráfico não disponível.")


@pytest.fixture
def tk_root(tk_app_root: tk.Tk):
    top = tk.Toplevel(tk_app_root)
    top.withdraw()
    yield top
    try:
        top.destroy()
    except Exception:
        pass


def test_gui_module_exports() -> None:
    from pdf_to_markdown_converter import gui

    assert hasattr(gui, "ConverterApp")
    assert hasattr(gui, "launch_gui")
    assert hasattr(gui, "main")
    assert hasattr(gui, "open_in_system")


def test_open_in_system(tmp_path: Path) -> None:
    non_existent = tmp_path / "arquivo_fantasma.txt"
    assert not open_in_system(non_existent)

    real_file = tmp_path / "existente.txt"
    real_file.write_text("ok", encoding="utf-8")

    with patch("sys.platform", "win32"), patch("os.startfile", create=True) as mock_start:
        res = open_in_system(real_file)
        assert res is True
        mock_start.assert_called_once_with(str(real_file.resolve()))

    with patch("sys.platform", "darwin"), patch("subprocess.run") as mock_run:
        res = open_in_system(real_file)
        assert res is True
        mock_run.assert_called_once_with(["open", str(real_file.resolve())], check=False)

    with patch("sys.platform", "linux"), patch("subprocess.run") as mock_run:
        res = open_in_system(real_file)
        assert res is True
        mock_run.assert_called_once_with(["xdg-open", str(real_file.resolve())], check=False)


def test_converter_app_init(tk_root: tk.Tk) -> None:
    app = ConverterApp(tk_root)
    assert app.pdf_path_var.get() == ""
    assert app.output_dir_var.get() == ""
    assert app.format_md_var.get() is True
    assert app.format_html_var.get() is True
    assert app.overwrite_var.get() is True
    assert app.force_ocr_var.get() is False
    assert app.lang_var.get() == "por+eng"
    assert app.password_var.get() == ""
    assert "Selecione" in app.status_var.get()


def test_converter_app_browse_pdf(tk_root: tk.Tk, sample_pdf: Path) -> None:
    app = ConverterApp(tk_root)
    with patch("tkinter.filedialog.askopenfilename", return_value=str(sample_pdf)):
        app._on_browse_pdf()
        assert app.pdf_path_var.get() == str(sample_pdf)
        assert app.output_dir_var.get() == str(sample_pdf.parent)
        assert sample_pdf.name in app.status_var.get()


def test_converter_app_browse_output_dir(tk_root: tk.Tk, tmp_path: Path) -> None:
    app = ConverterApp(tk_root)
    dest_dir = tmp_path / "custom_output"
    dest_dir.mkdir()
    with patch("tkinter.filedialog.askdirectory", return_value=str(dest_dir)):
        app._on_browse_output_dir()
        assert app.output_dir_var.get() == str(dest_dir)
        assert app.same_folder_var.get() is False


def test_converter_app_toggle_same_folder(tk_root: tk.Tk, sample_pdf: Path) -> None:
    app = ConverterApp(tk_root)
    app.pdf_path_var.set(str(sample_pdf))
    app.output_dir_var.set("C:/outra_pasta")
    app.same_folder_var.set(True)
    app._on_toggle_same_folder()
    assert app.output_dir_var.get() == str(sample_pdf.parent)


def test_converter_app_validation_empty_path(tk_root: tk.Tk) -> None:
    app = ConverterApp(tk_root)
    valid, msg = app.validate_inputs()
    assert valid is False
    assert "selecione um arquivo PDF" in msg


def test_converter_app_validation_non_existent_file(tk_root: tk.Tk, tmp_path: Path) -> None:
    app = ConverterApp(tk_root)
    app.pdf_path_var.set(str(tmp_path / "nao_existe.pdf"))
    valid, msg = app.validate_inputs()
    assert valid is False
    assert "não existe" in msg


def test_converter_app_validation_no_formats_selected(tk_root: tk.Tk, sample_pdf: Path) -> None:
    app = ConverterApp(tk_root)
    app.pdf_path_var.set(str(sample_pdf))
    app.format_md_var.set(False)
    app.format_html_var.set(False)
    valid, msg = app.validate_inputs()
    assert valid is False
    assert "pelo menos um formato" in msg


def test_converter_app_validation_invalid_destination(tk_root: tk.Tk, sample_pdf: Path) -> None:
    app = ConverterApp(tk_root)
    app.pdf_path_var.set(str(sample_pdf))
    # destino apontando para um arquivo existente, nao uma pasta
    app.output_dir_var.set(str(sample_pdf))
    valid, msg = app.validate_inputs()
    assert valid is False
    assert "não é uma pasta válida" in msg


def test_converter_app_validation_success(tk_root: tk.Tk, sample_pdf: Path, tmp_path: Path) -> None:
    app = ConverterApp(tk_root)
    app.pdf_path_var.set(str(sample_pdf))
    app.output_dir_var.set(str(tmp_path))
    valid, msg = app.validate_inputs()
    assert valid is True
    assert msg == ""


def test_converter_app_get_conversion_parameters(tk_root: tk.Tk, sample_pdf: Path) -> None:
    app = ConverterApp(tk_root)
    app.pdf_path_var.set(str(sample_pdf))
    app.output_dir_var.set(str(sample_pdf.parent))
    app.format_md_var.set(True)
    app.format_html_var.set(False)
    app.force_ocr_var.set(True)
    app.lang_var.set("por")
    app.password_var.set("segredo")

    params = app.get_conversion_parameters()
    assert params["source"] == str(sample_pdf)
    assert params["output_dir"] == str(sample_pdf.parent)
    assert params["export_formats"] == ("md",)
    assert params["force_ocr"] is True
    assert params["lang"] == "por"
    assert params["password"] == "segredo"


def test_converter_app_start_conversion_invalid_inputs(tk_root: tk.Tk) -> None:
    app = ConverterApp(tk_root)
    with patch("tkinter.messagebox.showwarning") as mock_warn:
        app.start_conversion()
        assert mock_warn.called
        assert "Aviso de Validação" in mock_warn.call_args[0][0]


def test_converter_app_conversion_success_flow(tk_root: tk.Tk, sample_pdf: Path, tmp_path: Path) -> None:
    mock_result = ExtractionResult(
        source_path=str(sample_pdf),
        markdown_path=str(tmp_path / "teste_gui.md"),
        html_path=str(tmp_path / "teste_gui.html"),
        strategy_used=ExtractionStrategy.NATIVE_TEXT,
        pages_processed=1,
        execution_time_seconds=0.42,
    )

    mock_convert = MagicMock(return_value=mock_result)
    app = ConverterApp(tk_root, convert_fn=mock_convert)
    app.pdf_path_var.set(str(sample_pdf))
    app.output_dir_var.set(str(tmp_path))

    # Executa a conversao
    app.start_conversion()

    # Aguarda o worker terminar na fila
    start_wait = time.perf_counter()
    while app._is_converting and time.perf_counter() - start_wait < 3.0:
        app._check_queue()
        time.sleep(0.05)

    assert app._is_converting is False
    assert app.progress_var.get() == 100.0
    assert "Concluído" in app.status_var.get()
    assert "0.42s" in app.lbl_result_details.cget("text")
    assert str(app.btn_open_folder.cget("state")) == str(tk.NORMAL)
    assert str(app.btn_open_md.cget("state")) == str(tk.NORMAL)
    assert str(app.btn_open_html.cget("state")) == str(tk.NORMAL)


@pytest.mark.parametrize(
    "error_exc,expected_substr",
    [
        (PdfNotFoundError("Arquivo sumiu"), "Arquivo não encontrado"),
        (EmptyPdfError("Vazio"), "está vazio"),
        (CorruptedPdfError("Corrompido"), "não é um PDF válido"),
        (EncryptedPdfError("Protegido"), "protegido por senha"),
        (TesseractNotFoundError("Sem Tesseract"), "Tesseract OCR não encontrado"),
        (DestinationExistsError("Já existe"), "já existe"),
        (ValueError("Opção inválida"), "Falha no processamento"),
        (RuntimeError("Erro genérico"), "Erro inesperado"),
    ],
)
def test_converter_app_conversion_errors_flow(
    tk_root: tk.Tk,
    sample_pdf: Path,
    tmp_path: Path,
    error_exc: Exception,
    expected_substr: str,
) -> None:
    mock_convert = MagicMock(side_effect=error_exc)
    app = ConverterApp(tk_root, convert_fn=mock_convert)
    app.pdf_path_var.set(str(sample_pdf))
    app.output_dir_var.set(str(tmp_path))

    with patch("tkinter.messagebox.showerror") as mock_err:
        app.start_conversion()

        start_wait = time.perf_counter()
        while app._is_converting and time.perf_counter() - start_wait < 3.0:
            app._check_queue()
            time.sleep(0.05)

        assert app._is_converting is False
        assert mock_err.called
        err_msg = mock_err.call_args[0][1]
        assert expected_substr in err_msg


def test_converter_app_progress_callback(tk_root: tk.Tk) -> None:
    app = ConverterApp(tk_root)
    app._progress_callback(PipelineStage.EXTRACTING, 0.45, "Extraindo blocos")
    app._check_queue()
    assert app.progress_var.get() == pytest.approx(45.0)
    assert "45% - Extraindo blocos" in app.status_var.get()


def test_converter_app_open_actions(tk_root: tk.Tk, tmp_path: Path) -> None:
    md_file = tmp_path / "out.md"
    html_file = tmp_path / "out.html"
    md_file.write_text("md", encoding="utf-8")
    html_file.write_text("html", encoding="utf-8")

    app = ConverterApp(tk_root)
    app._last_result = ExtractionResult(
        source_path="doc.pdf",
        markdown_path=str(md_file),
        html_path=str(html_file),
        strategy_used=ExtractionStrategy.NATIVE_TEXT,
        pages_processed=1,
        execution_time_seconds=0.1,
    )

    with patch("pdf_to_markdown_converter.gui.app.open_in_system", return_value=True) as mock_open:
        app._on_open_folder()
        mock_open.assert_called_with(tmp_path)

        app._on_open_md()
        mock_open.assert_called_with(str(md_file))

        app._on_open_html()
        mock_open.assert_called_with(str(html_file))


def test_converter_app_open_actions_failure_warns(tk_root: tk.Tk, tmp_path: Path) -> None:
    app = ConverterApp(tk_root)
    app._last_result = ExtractionResult(
        source_path="doc.pdf",
        markdown_path=str(tmp_path / "nao_existe.md"),
        html_path="",
        strategy_used=ExtractionStrategy.NATIVE_TEXT,
        pages_processed=1,
        execution_time_seconds=0.1,
    )

    with patch("pdf_to_markdown_converter.gui.app.open_in_system", return_value=False), patch(
        "tkinter.messagebox.showwarning"
    ) as mock_warn:
        app._on_open_md()
        assert mock_warn.called


def test_launch_gui_and_main(tk_root: tk.Tk) -> None:
    with patch("tkinter.Tk", return_value=tk_root), patch.object(tk_root, "mainloop") as mock_mainloop:
        ret = launch_gui()
        assert ret == 0
        assert mock_mainloop.called

    with patch("pdf_to_markdown_converter.gui.app.launch_gui") as mock_launch:
        main()
        assert mock_launch.called
