from collections.abc import Callable, Sequence
from enum import Enum
import inspect
from pathlib import Path
import time
from typing import Any

import pymupdf

from pdf_to_markdown_converter.core.block_classifier import classify_document_structure
from pdf_to_markdown_converter.core.detector import detect_extraction_strategy
from pdf_to_markdown_converter.core.native_extractor import NativeExtractor
from pdf_to_markdown_converter.core.ocr_extractor import (
    DEFAULT_DPI,
    DEFAULT_LANG,
    OcrExtractor,
)
from pdf_to_markdown_converter.core.pdf_reader import open_pdf
from pdf_to_markdown_converter.domain.models import (
    BlockType,
    DocumentStructure,
    ExtractionResult,
    ExtractionStrategy,
)
from pdf_to_markdown_converter.exporters.html_exporter import HtmlExporter
from pdf_to_markdown_converter.exporters.markdown_exporter import MarkdownExporter


class PipelineError(Exception):
    pass


class InvalidOptionError(PipelineError, ValueError):
    pass


class PipelineStage(str, Enum):
    START = "start"
    OPENING = "opening"
    DETECTING = "detecting"
    EXTRACTING = "extracting"
    CLASSIFYING = "classifying"
    EXPORTING = "exporting"
    FINISHED = "finished"


SUPPORTED_FORMATS: frozenset[str] = frozenset({"md", "markdown", "html", "html5"})


def _notify_progress(
    callback: Callable[..., None] | None, stage: PipelineStage, progress: float, message: str,
) -> None:
    if callback is None:
        return
    try:
        if len(inspect.signature(callback).parameters) == 2:
            callback(stage, progress)
        else:
            callback(stage, progress, message)
    except Exception:
        try:
            callback(stage, progress, message)
        except Exception:
            try:
                callback(stage, progress)
            except Exception:
                pass


class ConversionPipeline:
    def __init__(
        self,
        *,
        output_dir: str | Path | None = None,
        force_ocr: bool = False,
        dpi: int = DEFAULT_DPI,
        lang: str = DEFAULT_LANG,
        overwrite: bool = True,
        export_formats: Sequence[str] = ("md", "html"),
        check_ocr_environment: bool = True,
        progress_callback: Callable[..., None] | None = None,
    ) -> None:
        if dpi <= 0:
            raise InvalidOptionError(f"DPI deve ser um inteiro positivo, recebido: {dpi}")

        self.output_dir = Path(output_dir) if output_dir is not None else None
        self.force_ocr = force_ocr
        self.dpi, self.lang, self.overwrite = dpi, lang, overwrite
        self.check_ocr_environment = check_ocr_environment
        self.progress_callback = progress_callback
        self._export_formats = self._validate_and_normalize_formats(export_formats)
        self.native_extractor = NativeExtractor()
        self.ocr_extractor = OcrExtractor(
            dpi=self.dpi, lang=self.lang, check_environment=self.check_ocr_environment
        )

    @property
    def export_formats(self) -> tuple[str, ...]:
        return self._export_formats

    @staticmethod
    def _validate_and_normalize_formats(formats: Sequence[str]) -> tuple[str, ...]:
        if not formats:
            raise InvalidOptionError("Pelo menos um formato de exportacao deve ser especificado.")

        normalized: list[str] = []
        for fmt in formats:
            clean_fmt = fmt.lower().strip().lstrip(".")
            if clean_fmt not in SUPPORTED_FORMATS:
                raise InvalidOptionError(
                    f"Formato de exportacao '{fmt}' nao suportado. "
                    f"Formatos suportados: {sorted(SUPPORTED_FORMATS)}"
                )
            if clean_fmt not in normalized:
                normalized.append(clean_fmt)
        return tuple(normalized)

    def _resolve_output_targets(
        self,
        source: pymupdf.Document | str | Path | bytes,
        output_path: str | Path | None,
        filename: str | None,
    ) -> tuple[Path | None, Path | None]:
        target_stem = self._derive_stem(source, filename)
        if output_path is not None:
            out_p = Path(output_path)
            if out_p.is_dir() or str(output_path).endswith(("\\", "/")):
                return out_p / f"{target_stem}.md", out_p / f"{target_stem}.html"
            return out_p.with_suffix(".md"), out_p.with_suffix(".html")
        base_dir = self.output_dir if self.output_dir is not None else Path.cwd()
        return base_dir / f"{target_stem}.md", base_dir / f"{target_stem}.html"

    @staticmethod
    def _derive_stem(
        source: pymupdf.Document | str | Path | bytes,
        filename: str | None,
    ) -> str:
        if filename:
            return Path(filename).stem
        src_name = getattr(source, "name", None) if isinstance(source, pymupdf.Document) else (source if isinstance(source, (str, Path)) else None)
        if src_name:
            stem = Path(src_name).stem
            if stem and stem != "<memory>":
                return stem
        return "output"

    def _export_results(
        self,
        doc_structure: DocumentStructure,
        md_target: Path | None,
        html_target: Path | None,
    ) -> tuple[str, str]:
        md_exported_path = ""
        html_exported_path = ""
        if md_target is not None and any(fmt in self._export_formats for fmt in ("md", "markdown")):
            md_exported_path = str(MarkdownExporter(overwrite=self.overwrite).export_document(doc_structure, output_path=md_target))
        if html_target is not None and any(fmt in self._export_formats for fmt in ("html", "html5")):
            html_exported_path = str(HtmlExporter(overwrite=self.overwrite).export_document(doc_structure, output_path=html_target))
        return md_exported_path, html_exported_path

    def _process_document(
        self,
        doc: pymupdf.Document,
        source_label: str,
        output_path: str | Path | None,
        filename: str | None,
        password: str,
        start_time: float,
    ) -> ExtractionResult:
        total_pages = doc.page_count
        _notify_progress(self.progress_callback, PipelineStage.START, 0.05, "Iniciando processamento")
        _notify_progress(self.progress_callback, PipelineStage.DETECTING, 0.15, "Detectando estrategia")
        strategy = detect_extraction_strategy(doc, force_ocr=self.force_ocr, password=password)

        _notify_progress(self.progress_callback, PipelineStage.EXTRACTING, 0.15, f"Extraindo ({strategy.value})")

        def _on_page_progress(page_num: int, total: int) -> None:
            tot = total if total > 0 else 1
            progress = round(0.15 + 0.50 * (page_num / tot), 4)
            msg = f"Extraindo pagina {page_num}/{tot} ({strategy.value})"
            _notify_progress(self.progress_callback, PipelineStage.EXTRACTING, progress, msg)

        if strategy == ExtractionStrategy.OCR_FALLBACK:
            extracted_doc = self.ocr_extractor.extract(doc, password=password, page_callback=_on_page_progress)
        else:
            extracted_doc = self.native_extractor.extract(doc, password=password, page_callback=_on_page_progress)

        _notify_progress(self.progress_callback, PipelineStage.CLASSIFYING, 0.70, "Classificando blocos")
        classified_doc = classify_document_structure(extracted_doc)
        if any(b.block_type == BlockType.TABLE for b in extracted_doc.blocks):
            table_map = {i: b for i, b in enumerate(extracted_doc.blocks) if b.block_type == BlockType.TABLE}
            new_blocks = list(classified_doc.blocks)
            for idx, tbl in table_map.items():
                if idx < len(new_blocks):
                    new_blocks[idx] = tbl
            classified_doc = DocumentStructure(
                source_path=classified_doc.source_path,
                total_pages=classified_doc.total_pages,
                strategy=classified_doc.strategy,
                blocks=new_blocks,
            )

        _notify_progress(self.progress_callback, PipelineStage.EXPORTING, 0.85, "Exportando arquivos")
        md_target, html_target = self._resolve_output_targets(
            source=source_label, output_path=output_path, filename=filename
        )
        md_path, html_path = self._export_results(classified_doc, md_target, html_target)

        elapsed = round(max(0.0, time.perf_counter() - start_time), 4)
        _notify_progress(self.progress_callback, PipelineStage.FINISHED, 1.0, "Processamento concluido")

        return ExtractionResult(
            source_path=source_label,
            markdown_path=md_path,
            html_path=html_path,
            strategy_used=strategy,
            pages_processed=total_pages,
            execution_time_seconds=elapsed,
        )

    def convert(
        self,
        source: pymupdf.Document | str | Path | bytes,
        *,
        output_path: str | Path | None = None,
        filename: str | None = None,
        password: str = "",
    ) -> ExtractionResult:
        start_time = time.perf_counter()
        _notify_progress(self.progress_callback, PipelineStage.OPENING, 0.0, "Abrindo documento")

        if isinstance(source, pymupdf.Document):
            label = source.name or "<memory>"
            return self._process_document(
                doc=source,
                source_label=label,
                output_path=output_path,
                filename=filename,
                password=password,
                start_time=start_time,
            )

        source_label = str(source) if isinstance(source, (str, Path)) else "<memory>"
        with open_pdf(source, password=password) as doc:
            return self._process_document(
                doc=doc,
                source_label=source_label,
                output_path=output_path,
                filename=filename,
                password=password,
                start_time=start_time,
            )

    def convert_document(
        self, doc: pymupdf.Document, *, output_path: str | Path | None = None,
        filename: str | None = None, password: str = "",
    ) -> ExtractionResult:
        return self.convert(source=doc, output_path=output_path, filename=filename, password=password)


Pipeline = ConversionPipeline


def convert_pdf(
    source: pymupdf.Document | str | Path | bytes,
    *,
    output_dir: str | Path | None = None,
    output_path: str | Path | None = None,
    filename: str | None = None,
    force_ocr: bool = False,
    dpi: int = DEFAULT_DPI,
    lang: str = DEFAULT_LANG,
    overwrite: bool = True,
    export_formats: Sequence[str] = ("md", "html"),
    password: str = "",
    check_ocr_environment: bool = True,
    progress_callback: Callable[..., None] | None = None,
) -> ExtractionResult:
    pipeline = ConversionPipeline(
        output_dir=output_dir, force_ocr=force_ocr, dpi=dpi, lang=lang,
        overwrite=overwrite, export_formats=export_formats,
        check_ocr_environment=check_ocr_environment, progress_callback=progress_callback,
    )
    return pipeline.convert(source, output_path=output_path, filename=filename, password=password)
