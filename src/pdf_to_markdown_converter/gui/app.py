from __future__ import annotations

import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

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
from pdf_to_markdown_converter.core.tesseract_env import TesseractNotFoundError
from pdf_to_markdown_converter.domain.models import ExtractionResult
from pdf_to_markdown_converter.exporters.markdown_exporter import DestinationExistsError


def open_in_system(path: str | Path) -> bool:
    """Abre um arquivo ou diretório no visualizador/gerenciador padrão do sistema."""
    target = Path(path).resolve()
    if not target.exists():
        return False

    try:
        if sys.platform == "win32":
            os.startfile(str(target))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(target)], check=False)
        else:
            subprocess.run(["xdg-open", str(target)], check=False)
        return True
    except Exception:
        return False


class ConverterApp:
    """Interface gráfica simples para conversão de PDFs em Markdown e HTML5."""

    def __init__(
        self,
        master: tk.Tk | tk.Toplevel,
        *,
        convert_fn: Callable[..., ExtractionResult] = convert_pdf,
    ) -> None:
        self.master = master
        self.convert_fn = convert_fn
        self._msg_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._is_converting = False
        self._last_result: ExtractionResult | None = None

        self._init_variables()
        self._setup_window()
        self._setup_styles()
        self._build_ui()
        self._schedule_queue_check()

    def _init_variables(self) -> None:
        self.pdf_path_var = tk.StringVar(value="")
        self.output_dir_var = tk.StringVar(value="")
        self.same_folder_var = tk.BooleanVar(value=True)

        self.format_md_var = tk.BooleanVar(value=True)
        self.format_html_var = tk.BooleanVar(value=True)
        self.overwrite_var = tk.BooleanVar(value=True)

        self.force_ocr_var = tk.BooleanVar(value=False)
        self.lang_var = tk.StringVar(value=DEFAULT_LANG)
        self.password_var = tk.StringVar(value="")

        self.progress_var = tk.DoubleVar(value=0.0)
        self.status_var = tk.StringVar(value="Selecione um arquivo PDF para iniciar.")

    def _setup_window(self) -> None:
        self.master.title("PDF to Markdown & HTML Converter")
        self.master.geometry("700x630")
        self.master.minsize(620, 560)

    def _setup_styles(self) -> None:
        style = ttk.Style(self.master)
        available_themes = style.theme_names()
        if "vista" in available_themes:
            style.theme_use("vista")
        elif "clam" in available_themes:
            style.theme_use("clam")

        style.configure("Title.TLabel", font=("Segoe UI", 14, "bold"))
        style.configure("Subtitle.TLabel", font=("Segoe UI", 9), foreground="#555555")
        style.configure("Header.TLabelframe.Label", font=("Segoe UI", 10, "bold"))
        style.configure("Action.TButton", font=("Segoe UI", 10, "bold"), padding=6)
        style.configure("Status.TLabel", font=("Segoe UI", 9))

    def _build_ui(self) -> None:
        main_frame = ttk.Frame(self.master, padding="16 12 16 16")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Cabeçalho
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 10))

        title_lbl = ttk.Label(
            header_frame,
            text="PDF to Markdown Converter",
            style="Title.TLabel",
        )
        title_lbl.pack(anchor="w")

        subtitle_lbl = ttk.Label(
            header_frame,
            text="Converta documentos PDF em Markdown estruturado e HTML5 de forma 100% local e segura.",
            style="Subtitle.TLabel",
        )
        subtitle_lbl.pack(anchor="w", pady=(2, 0))

        # Seção 1: Arquivos e Destino
        io_frame = ttk.LabelFrame(
            main_frame,
            text=" Arquivos e Destino ",
            padding="12 10 12 10",
        )
        io_frame.pack(fill=tk.X, pady=(0, 10))

        # PDF de Origem
        ttk.Label(io_frame, text="Arquivo PDF de Origem:").grid(row=0, column=0, sticky="w", pady=4)
        self.entry_pdf = ttk.Entry(io_frame, textvariable=self.pdf_path_var)
        self.entry_pdf.grid(row=0, column=1, sticky="ew", padx=(6, 6), pady=4)
        self.btn_browse_pdf = ttk.Button(
            io_frame,
            text="Procurar...",
            command=self._on_browse_pdf,
        )
        self.btn_browse_pdf.grid(row=0, column=2, pady=4)

        # Pasta de Destino
        ttk.Label(io_frame, text="Pasta de Destino:").grid(row=1, column=0, sticky="w", pady=4)
        self.entry_output = ttk.Entry(io_frame, textvariable=self.output_dir_var)
        self.entry_output.grid(row=1, column=1, sticky="ew", padx=(6, 6), pady=4)
        self.btn_browse_output = ttk.Button(
            io_frame,
            text="Procurar...",
            command=self._on_browse_output_dir,
        )
        self.btn_browse_output.grid(row=1, column=2, pady=4)

        # Opção mesma pasta
        self.chk_same_folder = ttk.Checkbutton(
            io_frame,
            text="Usar mesma pasta do PDF de origem",
            variable=self.same_folder_var,
            command=self._on_toggle_same_folder,
        )
        self.chk_same_folder.grid(row=2, column=1, sticky="w", padx=(6, 0), pady=(2, 2))

        io_frame.columnconfigure(1, weight=1)

        # Seção 2: Configurações de Exportação
        options_frame = ttk.LabelFrame(
            main_frame,
            text=" Opções de Conversão ",
            padding="12 10 12 10",
        )
        options_frame.pack(fill=tk.X, pady=(0, 10))

        # Formatos
        fmt_frame = ttk.Frame(options_frame)
        fmt_frame.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(fmt_frame, text="Formatos de Saída:").pack(side=tk.LEFT, padx=(0, 10))
        self.chk_md = ttk.Checkbutton(fmt_frame, text="Markdown (.md)", variable=self.format_md_var)
        self.chk_md.pack(side=tk.LEFT, padx=(0, 12))
        self.chk_html = ttk.Checkbutton(fmt_frame, text="HTML5 (.html)", variable=self.format_html_var)
        self.chk_html.pack(side=tk.LEFT, padx=(0, 12))

        self.chk_overwrite = ttk.Checkbutton(
            fmt_frame,
            text="Sobrescrever arquivos existentes",
            variable=self.overwrite_var,
        )
        self.chk_overwrite.pack(side=tk.RIGHT)

        ttk.Separator(options_frame, orient="horizontal").pack(fill=tk.X, pady=6)

        # Opções complementares: OCR e Senha
        adv_grid = ttk.Frame(options_frame)
        adv_grid.pack(fill=tk.X)

        self.chk_force_ocr = ttk.Checkbutton(
            adv_grid,
            text="Forçar OCR (PDFs digitalizados / imagens)",
            variable=self.force_ocr_var,
        )
        self.chk_force_ocr.grid(row=0, column=0, columnspan=2, sticky="w", pady=2)

        ttk.Label(adv_grid, text="Idiomas OCR:").grid(row=0, column=2, sticky="e", padx=(16, 4))
        self.entry_lang = ttk.Entry(adv_grid, textvariable=self.lang_var, width=12)
        self.entry_lang.grid(row=0, column=3, sticky="w")

        ttk.Label(adv_grid, text="Senha (se protegido):").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.entry_password = ttk.Entry(adv_grid, textvariable=self.password_var, show="*")
        self.entry_password.grid(row=1, column=1, columnspan=3, sticky="ew", pady=(6, 0), padx=(4, 0))

        adv_grid.columnconfigure(1, weight=1)

        # Seção 3: Execução e Progresso
        process_frame = ttk.LabelFrame(
            main_frame,
            text=" Execução e Progresso ",
            padding="12 10 12 10",
        )
        process_frame.pack(fill=tk.X, pady=(0, 10))

        # Botão Converter
        btn_box = ttk.Frame(process_frame)
        btn_box.pack(fill=tk.X, pady=(2, 8))

        self.btn_convert = ttk.Button(
            btn_box,
            text="Converter Documento",
            style="Action.TButton",
            command=self.start_conversion,
        )
        self.btn_convert.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Barra de Progresso
        self.progressbar = ttk.Progressbar(
            process_frame,
            orient="horizontal",
            mode="determinate",
            variable=self.progress_var,
            maximum=100.0,
        )
        self.progressbar.pack(fill=tk.X, pady=(0, 6))

        # Status text
        self.lbl_status = ttk.Label(
            process_frame,
            textvariable=self.status_var,
            style="Status.TLabel",
        )
        self.lbl_status.pack(anchor="w")

        # Seção 4: Resultados e Ações Rápidas
        self.result_frame = ttk.LabelFrame(
            main_frame,
            text=" Resultados ",
            padding="12 10 12 10",
        )
        self.result_frame.pack(fill=tk.BOTH, expand=True)

        self.lbl_result_details = ttk.Label(
            self.result_frame,
            text="Nenhuma conversão recente.",
            wraplength=640,
            justify=tk.LEFT,
        )
        self.lbl_result_details.pack(anchor="w", pady=(0, 8))

        self.actions_box = ttk.Frame(self.result_frame)
        self.actions_box.pack(fill=tk.X)

        self.btn_open_folder = ttk.Button(
            self.actions_box,
            text="Abrir Pasta de Destino",
            command=self._on_open_folder,
            state=tk.DISABLED,
        )
        self.btn_open_folder.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_open_md = ttk.Button(
            self.actions_box,
            text="Visualizar Markdown",
            command=self._on_open_md,
            state=tk.DISABLED,
        )
        self.btn_open_md.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_open_html = ttk.Button(
            self.actions_box,
            text="Visualizar HTML5",
            command=self._on_open_html,
            state=tk.DISABLED,
        )
        self.btn_open_html.pack(side=tk.LEFT)

    def _on_browse_pdf(self) -> None:
        chosen = filedialog.askopenfilename(
            title="Selecionar Documento PDF",
            filetypes=[("Arquivos PDF (*.pdf)", "*.pdf"), ("Todos os Arquivos", "*.*")],
        )
        if chosen:
            self.pdf_path_var.set(chosen)
            if self.same_folder_var.get() or not self.output_dir_var.get().strip():
                parent_dir = str(Path(chosen).parent)
                self.output_dir_var.set(parent_dir)
            self.status_var.set(f"Arquivo selecionado: {Path(chosen).name}")

    def _on_browse_output_dir(self) -> None:
        initial = self.output_dir_var.get().strip() or None
        chosen = filedialog.askdirectory(
            title="Selecionar Pasta de Destino",
            initialdir=initial,
        )
        if chosen:
            self.output_dir_var.set(chosen)
            self.same_folder_var.set(False)

    def _on_toggle_same_folder(self) -> None:
        if self.same_folder_var.get():
            pdf_path = self.pdf_path_var.get().strip()
            if pdf_path:
                self.output_dir_var.set(str(Path(pdf_path).parent))

    def validate_inputs(self) -> tuple[bool, str]:
        pdf_path = self.pdf_path_var.get().strip()
        if not pdf_path:
            return False, "Por favor, selecione um arquivo PDF de origem."

        p = Path(pdf_path)
        if not p.exists() or not p.is_file():
            return False, f"O arquivo PDF informado não existe:\n{pdf_path}"

        if not self.format_md_var.get() and not self.format_html_var.get():
            return False, "Selecione pelo menos um formato de saída (Markdown ou HTML5)."

        output_dir = self.output_dir_var.get().strip()
        if output_dir:
            out_p = Path(output_dir)
            if out_p.exists() and not out_p.is_dir():
                return False, f"O destino informado não é uma pasta válida:\n{output_dir}"

        return True, ""

    def get_conversion_parameters(self) -> dict[str, Any]:
        formats: list[str] = []
        if self.format_md_var.get():
            formats.append("md")
        if self.format_html_var.get():
            formats.append("html")

        out_dir = self.output_dir_var.get().strip() or None

        return {
            "source": self.pdf_path_var.get().strip(),
            "output_dir": out_dir,
            "force_ocr": self.force_ocr_var.get(),
            "lang": self.lang_var.get().strip() or DEFAULT_LANG,
            "overwrite": self.overwrite_var.get(),
            "export_formats": tuple(formats),
            "password": self.password_var.get(),
        }

    def _set_ui_converting(self, converting: bool) -> None:
        self._is_converting = converting
        state = tk.DISABLED if converting else tk.NORMAL
        self.btn_convert.config(state=state)
        self.btn_browse_pdf.config(state=state)
        self.btn_browse_output.config(state=state)
        self.entry_pdf.config(state=state)
        self.entry_output.config(state=state)

    def start_conversion(self) -> None:
        if self._is_converting:
            return

        valid, error_msg = self.validate_inputs()
        if not valid:
            messagebox.showwarning("Aviso de Validação", error_msg, parent=self.master)
            return

        params = self.get_conversion_parameters()
        self._set_ui_converting(True)
        self.progress_var.set(0.0)
        self.status_var.set("Iniciando conversão...")
        self.lbl_result_details.config(text="Processando documento...")
        self.btn_open_folder.config(state=tk.DISABLED)
        self.btn_open_md.config(state=tk.DISABLED)
        self.btn_open_html.config(state=tk.DISABLED)

        thread = threading.Thread(
            target=self._worker_conversion,
            args=(params,),
            daemon=True,
        )
        thread.start()

    def _progress_callback(self, stage: PipelineStage, progress: float, message: str = "") -> None:
        display_msg = f"{int(progress * 100)}% - {message or stage.value.capitalize()}"
        self._msg_queue.put(("progress", (progress * 100.0, display_msg)))

    def _worker_conversion(self, params: dict[str, Any]) -> None:
        try:
            result = self.convert_fn(
                params["source"],
                output_dir=params["output_dir"],
                force_ocr=params["force_ocr"],
                lang=params["lang"],
                overwrite=params["overwrite"],
                export_formats=params["export_formats"],
                password=params["password"],
                progress_callback=self._progress_callback,
            )
            self._msg_queue.put(("success", result))
        except PdfNotFoundError as exc:
            self._msg_queue.put(("error", f"Arquivo não encontrado: {exc}"))
        except EmptyPdfError:
            self._msg_queue.put(("error", "O arquivo PDF selecionado está vazio (0 bytes)."))
        except CorruptedPdfError:
            self._msg_queue.put(("error", "O documento não é um PDF válido ou está corrompido."))
        except EncryptedPdfError:
            self._msg_queue.put(("error", "O documento está protegido por senha. Forneça a senha no campo correspondente."))
        except TesseractNotFoundError as exc:
            self._msg_queue.put(("error", f"Tesseract OCR não encontrado: {exc}"))
        except (DestinationExistsError, FileExistsError) as exc:
            self._msg_queue.put(("error", f"Arquivo de destino já existe e a opção de sobrescrita está desativada:\n{exc}"))
        except (InvalidOptionError, PipelineError, ValueError) as exc:
            self._msg_queue.put(("error", f"Falha no processamento: {exc}"))
        except Exception as exc:
            self._msg_queue.put(("error", f"Erro inesperado durante a conversão:\n{exc}"))

    def _schedule_queue_check(self) -> None:
        self.master.after(50, self._check_queue)

    def _check_queue(self) -> None:
        try:
            while True:
                msg_type, data = self._msg_queue.get_nowait()
                if msg_type == "progress":
                    percent, text = data
                    self.progress_var.set(percent)
                    self.status_var.set(text)
                elif msg_type == "success":
                    self._handle_success(data)
                elif msg_type == "error":
                    self._handle_error(data)
        except queue.Empty:
            pass
        finally:
            self._schedule_queue_check()

    def _handle_success(self, result: ExtractionResult) -> None:
        self._last_result = result
        self._set_ui_converting(False)
        self.progress_var.set(100.0)
        self.status_var.set(f"Concluído com sucesso em {result.execution_time_seconds:.2f}s!")

        details = (
            f"Origem: {result.source_path}\n"
            f"Páginas: {result.pages_processed} | Estratégia: {result.strategy_used.value} | "
            f"Tempo: {result.execution_time_seconds:.2f}s\n"
        )
        if result.markdown_path:
            details += f"• Markdown: {result.markdown_path}\n"
        if result.html_path:
            details += f"• HTML5: {result.html_path}\n"

        self.lbl_result_details.config(text=details.strip())

        # Habilita botões pós-processamento
        if result.markdown_path or result.html_path:
            self.btn_open_folder.config(state=tk.NORMAL)
        if result.markdown_path:
            self.btn_open_md.config(state=tk.NORMAL)
        if result.html_path:
            self.btn_open_html.config(state=tk.NORMAL)

    def _handle_error(self, message: str) -> None:
        self._set_ui_converting(False)
        self.status_var.set("Ocorreu um erro durante a conversão.")
        self.lbl_result_details.config(text=message)
        messagebox.showerror("Erro de Conversão", message, parent=self.master)

    def _on_open_folder(self) -> None:
        if not self._last_result:
            return
        target = self._last_result.markdown_path or self._last_result.html_path
        if target:
            folder = Path(target).parent
            if not open_in_system(folder):
                messagebox.showwarning("Aviso", f"Não foi possível abrir a pasta:\n{folder}", parent=self.master)

    def _on_open_md(self) -> None:
        if self._last_result and self._last_result.markdown_path:
            if not open_in_system(self._last_result.markdown_path):
                messagebox.showwarning(
                    "Aviso",
                    f"Não foi possível abrir o arquivo:\n{self._last_result.markdown_path}",
                    parent=self.master,
                )

    def _on_open_html(self) -> None:
        if self._last_result and self._last_result.html_path:
            if not open_in_system(self._last_result.html_path):
                messagebox.showwarning(
                    "Aviso",
                    f"Não foi possível abrir o arquivo:\n{self._last_result.html_path}",
                    parent=self.master,
                )


def launch_gui(root: tk.Tk | None = None) -> int:
    """Inicia a aplicação gráfica Tkinter."""
    owns_root = root is None
    app_root = tk.Tk() if owns_root else root
    assert app_root is not None

    ConverterApp(app_root)

    if owns_root:
        app_root.mainloop()
    return 0


def main() -> None:
    """Ponto de entrada executável para a GUI."""
    launch_gui()


if __name__ == "__main__":
    main()
