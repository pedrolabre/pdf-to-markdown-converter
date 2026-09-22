from collections.abc import Sequence
import os
from pathlib import Path
import tempfile

import markdown

from pdf_to_markdown_converter.core.markdown_builder import build_markdown
from pdf_to_markdown_converter.domain.models import DocumentStructure, TextBlock
from pdf_to_markdown_converter.exporters.markdown_exporter import (
    DestinationExistsError as _BaseDestinationExistsError,
)
from pdf_to_markdown_converter.exporters.styles import render_html_document

DEFAULT_MARKDOWN_EXTENSIONS: tuple[str, ...] = ("tables", "fenced_code")


class HtmlExporterError(Exception):
    pass


class DestinationExistsError(HtmlExporterError, _BaseDestinationExistsError):
    pass


HtmlExportError = HtmlExporterError
HtmlDestinationExistsError = DestinationExistsError


def compile_markdown_to_html(
    markdown_text: str,
    extensions: Sequence[str] | None = None,
) -> str:
    exts = list(DEFAULT_MARKDOWN_EXTENSIONS if extensions is None else extensions)
    return markdown.markdown(markdown_text, extensions=exts, output_format="html5")


def _coerce_markdown_text(
    content: str | DocumentStructure | Sequence[TextBlock],
) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, (DocumentStructure, Sequence)):
        return build_markdown(content)
    raise TypeError(
        f"Tipo de conteudo nao suportado: {type(content).__name__}. "
        "Esperado str, DocumentStructure ou Sequence[TextBlock]."
    )


def _resolve_target_path(
    content: str | DocumentStructure | Sequence[TextBlock],
    output_path: str | Path | None,
    default_dir: Path | None = None,
    filename: str | None = None,
) -> Path:
    if output_path is not None:
        target = Path(output_path)
        if default_dir is not None and not target.is_absolute():
            target = default_dir / target
        if target.is_dir():
            if filename:
                target = target / filename
            elif isinstance(content, DocumentStructure) and content.source_path:
                target = target / f"{Path(content.source_path).stem}.html"
            else:
                target = target / "output.html"
    else:
        base_dir = default_dir if default_dir is not None else Path.cwd()
        if filename:
            target = base_dir / filename
        elif isinstance(content, DocumentStructure) and content.source_path:
            target = base_dir / f"{Path(content.source_path).stem}.html"
        else:
            raise ValueError(
                "Caminho de destino ou nome de arquivo deve ser especificado "
                "quando o conteudo nao possui source_path."
            )

    return target.with_suffix(".html") if target.suffix == "" else target


def _write_atomic(
    target_path: Path,
    text: str,
    overwrite: bool = True,
    ensure_newline: bool = True,
) -> Path:
    resolved = target_path.resolve()
    if resolved.exists() and not overwrite:
        raise DestinationExistsError(f"Arquivo de destino ja existe: {resolved}")

    resolved.parent.mkdir(parents=True, exist_ok=True)
    body = f"{text}\n" if (ensure_newline and not text.endswith("\n")) else text

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=resolved.parent,
            prefix=f".{resolved.name}_",
            suffix=".tmp",
            mode="w",
            encoding="utf-8",
            newline="",
            delete=False,
        ) as tmp:
            temp_path = Path(tmp.name)
            tmp.write(body)
            tmp.flush()
            os.fsync(tmp.fileno())

        os.replace(temp_path, resolved)
        temp_path = None
        return resolved
    except Exception as exc:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        if isinstance(exc, HtmlExporterError):
            raise
        raise HtmlExporterError(
            f"Falha ao exportar arquivo HTML para '{resolved}': {exc}"
        ) from exc


def render_html(
    content: str | DocumentStructure | Sequence[TextBlock],
    title: str | None = None,
    lang: str = "pt-BR",
    extra_css: str = "",
    extensions: Sequence[str] | None = None,
) -> str:
    md_text = _coerce_markdown_text(content)
    body_html = compile_markdown_to_html(md_text, extensions=extensions)

    if title is not None:
        doc_title = title
    elif isinstance(content, DocumentStructure) and content.source_path:
        doc_title = Path(content.source_path).stem
    else:
        doc_title = "Documento"

    return render_html_document(
        content=body_html,
        title=doc_title,
        lang=lang,
        extra_css=extra_css,
    )


def export_html(
    content: str | DocumentStructure | Sequence[TextBlock],
    output_path: str | Path,
    overwrite: bool = True,
    title: str | None = None,
    lang: str = "pt-BR",
    extra_css: str = "",
    extensions: Sequence[str] | None = None,
    ensure_newline: bool = True,
) -> Path:
    target = _resolve_target_path(content=content, output_path=output_path)
    full_html = render_html(
        content=content,
        title=title,
        lang=lang,
        extra_css=extra_css,
        extensions=extensions,
    )
    return _write_atomic(
        target_path=target,
        text=full_html,
        overwrite=overwrite,
        ensure_newline=ensure_newline,
    )


class HtmlExporter:
    def __init__(
        self,
        output_dir: str | Path | None = None,
        overwrite: bool = True,
        title: str | None = None,
        lang: str = "pt-BR",
        extra_css: str = "",
        extensions: Sequence[str] | None = None,
        ensure_newline: bool = True,
    ) -> None:
        self.output_dir = Path(output_dir) if output_dir is not None else None
        self.overwrite = overwrite
        self.title = title
        self.lang = lang
        self.extra_css = extra_css
        self.extensions = (
            tuple(extensions)
            if extensions is not None
            else DEFAULT_MARKDOWN_EXTENSIONS
        )
        self.ensure_newline = ensure_newline

    def compile_body(
        self,
        content: str | DocumentStructure | Sequence[TextBlock],
    ) -> str:
        md_text = _coerce_markdown_text(content)
        return compile_markdown_to_html(md_text, extensions=self.extensions)

    def compile(
        self,
        content: str | DocumentStructure | Sequence[TextBlock],
        title: str | None = None,
        lang: str | None = None,
        extra_css: str | None = None,
    ) -> str:
        return render_html(
            content=content,
            title=self.title if title is None else title,
            lang=self.lang if lang is None else lang,
            extra_css=self.extra_css if extra_css is None else extra_css,
            extensions=self.extensions,
        )

    def export(
        self,
        content: str | DocumentStructure | Sequence[TextBlock],
        output_path: str | Path | None = None,
        filename: str | None = None,
        title: str | None = None,
        lang: str | None = None,
        extra_css: str | None = None,
    ) -> Path:
        target = _resolve_target_path(
            content=content,
            output_path=output_path,
            default_dir=self.output_dir,
            filename=filename,
        )
        full_html = self.compile(
            content=content,
            title=title,
            lang=lang,
            extra_css=extra_css,
        )
        return _write_atomic(
            target_path=target,
            text=full_html,
            overwrite=self.overwrite,
            ensure_newline=self.ensure_newline,
        )

    def export_document(
        self,
        document: DocumentStructure,
        output_path: str | Path | None = None,
        filename: str | None = None,
        title: str | None = None,
        lang: str | None = None,
        extra_css: str | None = None,
    ) -> Path:
        return self.export(
            content=document,
            output_path=output_path,
            filename=filename,
            title=title,
            lang=lang,
            extra_css=extra_css,
        )
