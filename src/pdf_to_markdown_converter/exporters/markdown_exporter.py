from collections.abc import Sequence
import os
from pathlib import Path
import tempfile

from pdf_to_markdown_converter.core.markdown_builder import build_markdown
from pdf_to_markdown_converter.domain.models import DocumentStructure, TextBlock


class MarkdownExporterError(Exception):
    pass


class DestinationExistsError(MarkdownExporterError, FileExistsError):
    pass


MarkdownExportError = MarkdownExporterError


def _coerce_markdown_text(
    content: str | DocumentStructure | Sequence[TextBlock],
) -> str:
    if isinstance(content, str):
        return content
    elif isinstance(content, DocumentStructure):
        return build_markdown(content)
    elif isinstance(content, Sequence):
        return build_markdown(content)
    else:
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
                stem = Path(content.source_path).stem
                target = target / f"{stem}.md"
            else:
                target = target / "output.md"
    else:
        base_dir = default_dir if default_dir is not None else Path.cwd()
        if filename:
            target = base_dir / filename
        elif isinstance(content, DocumentStructure) and content.source_path:
            stem = Path(content.source_path).stem
            target = base_dir / f"{stem}.md"
        else:
            raise ValueError(
                "Caminho de destino ou nome de arquivo deve ser especificado "
                "quando o conteudo nao possui source_path."
            )

    if target.suffix == "":
        target = target.with_suffix(".md")

    return target


def _write_atomic(
    target_path: Path,
    text: str,
    overwrite: bool = True,
    ensure_newline: bool = True,
) -> Path:
    resolved_path = target_path.resolve()
    if resolved_path.exists() and not overwrite:
        raise DestinationExistsError(
            f"Arquivo de destino ja existe: {resolved_path}"
        )

    parent_dir = resolved_path.parent
    parent_dir.mkdir(parents=True, exist_ok=True)

    content_to_write = text
    if ensure_newline and not content_to_write.endswith("\n"):
        content_to_write = f"{content_to_write}\n"

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=parent_dir,
            prefix=f".{resolved_path.name}_",
            suffix=".tmp",
            mode="w",
            encoding="utf-8",
            newline="",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(content_to_write)
            temp_file.flush()
            os.fsync(temp_file.fileno())

        os.replace(temp_path, resolved_path)
        temp_path = None
        return resolved_path
    except Exception as exc:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        if isinstance(exc, MarkdownExporterError):
            raise
        raise MarkdownExporterError(
            f"Falha ao exportar arquivo Markdown para '{resolved_path}': {exc}"
        ) from exc


def export_markdown(
    content: str | DocumentStructure | Sequence[TextBlock],
    output_path: str | Path,
    overwrite: bool = True,
    ensure_newline: bool = True,
) -> Path:
    text = _coerce_markdown_text(content)
    target = _resolve_target_path(content=content, output_path=output_path)
    return _write_atomic(
        target_path=target,
        text=text,
        overwrite=overwrite,
        ensure_newline=ensure_newline,
    )


class MarkdownExporter:
    def __init__(
        self,
        output_dir: str | Path | None = None,
        overwrite: bool = True,
        ensure_newline: bool = True,
    ) -> None:
        self.output_dir = Path(output_dir) if output_dir is not None else None
        self.overwrite = overwrite
        self.ensure_newline = ensure_newline

    def export(
        self,
        content: str | DocumentStructure | Sequence[TextBlock],
        output_path: str | Path | None = None,
        filename: str | None = None,
    ) -> Path:
        target = _resolve_target_path(
            content=content,
            output_path=output_path,
            default_dir=self.output_dir,
            filename=filename,
        )
        text = _coerce_markdown_text(content)
        return _write_atomic(
            target_path=target,
            text=text,
            overwrite=self.overwrite,
            ensure_newline=self.ensure_newline,
        )

    def export_document(
        self,
        document: DocumentStructure,
        output_path: str | Path | None = None,
        filename: str | None = None,
    ) -> Path:
        return self.export(
            content=document,
            output_path=output_path,
            filename=filename,
        )
