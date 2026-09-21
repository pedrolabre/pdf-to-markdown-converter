from pathlib import Path
import pytest

from pdf_to_markdown_converter.domain.models import (
    BlockType,
    DocumentStructure,
    ExtractionStrategy,
    TextBlock,
)
from pdf_to_markdown_converter.exporters import (
    DestinationExistsError,
    MarkdownExportError,
    MarkdownExporter,
    MarkdownExporterError,
    export_markdown,
)


def test_package_exports():
    import pdf_to_markdown_converter.exporters as pkg

    assert hasattr(pkg, "export_markdown")
    assert hasattr(pkg, "MarkdownExporter")
    assert hasattr(pkg, "MarkdownExporterError")
    assert hasattr(pkg, "DestinationExistsError")
    assert hasattr(pkg, "MarkdownExportError")
    assert issubclass(DestinationExistsError, MarkdownExporterError)
    assert issubclass(DestinationExistsError, FileExistsError)
    assert MarkdownExportError is MarkdownExporterError


def test_export_markdown_basic_string(tmp_path: Path):
    target = tmp_path / "sample.md"
    content = "# Titulo Principal\n\nEste e um paragrafo de teste."

    result = export_markdown(content, target)

    assert result == target.resolve()
    assert target.exists()
    assert target.read_text(encoding="utf-8") == f"{content}\n"


def test_export_markdown_utf8_portuguese(tmp_path: Path):
    target = tmp_path / "portugues.md"
    content = (
        "# Relatório de Avaliação Técnica 📊\n\n"
        "Configuração dos parâmetros de extração: acentuação, cedilha (ç), "
        "não-quebravel, e símbolos matemáticos (∑, ∏, √).\n"
    )

    export_markdown(content, target)

    raw_bytes = target.read_bytes()
    decoded = raw_bytes.decode("utf-8")
    assert decoded == content
    assert "Relatório de Avaliação Técnica 📊" in decoded
    assert "Configuração" in decoded


def test_export_markdown_from_document_structure(tmp_path: Path):
    blocks = [
        TextBlock(page_number=1, block_type=BlockType.HEADING, raw_text="Auditoria", heading_level=1),
        TextBlock(page_number=1, block_type=BlockType.PARAGRAPH, raw_text="Paragrafo introdutorio."),
        TextBlock(page_number=1, block_type=BlockType.LIST_ITEM, raw_text="• Item verificado"),
        TextBlock(page_number=1, block_type=BlockType.CODE_BLOCK, raw_text="print('audit passed')"),
    ]
    doc = DocumentStructure(
        source_path="caminho/para/auditoria.pdf",
        total_pages=1,
        strategy=ExtractionStrategy.NATIVE_TEXT,
        blocks=blocks,
    )

    target = tmp_path / "auditoria.md"
    result = export_markdown(doc, target)

    assert result.exists()
    content = target.read_text(encoding="utf-8")
    assert "# Auditoria" in content
    assert "Paragrafo introdutorio." in content
    assert "- Item verificado" in content
    assert "```" in content
    assert "print('audit passed')" in content


def test_export_markdown_from_text_blocks_sequence(tmp_path: Path):
    blocks = [
        TextBlock(page_number=1, block_type=BlockType.HEADING, raw_text="Secao Unica", heading_level=2),
        TextBlock(page_number=1, block_type=BlockType.PARAGRAPH, raw_text="Texto do bloco isolado."),
    ]

    target = tmp_path / "blocos.md"
    export_markdown(blocks, target)

    content = target.read_text(encoding="utf-8")
    assert "## Secao Unica" in content
    assert "Texto do bloco isolado." in content


def test_export_markdown_creates_parent_directories(tmp_path: Path):
    nested_target = tmp_path / "sub1" / "sub2" / "sub3" / "resultado.md"
    assert not nested_target.parent.exists()

    export_markdown("Conteudo em pasta profunda", nested_target)

    assert nested_target.exists()
    assert nested_target.read_text(encoding="utf-8") == "Conteudo em pasta profunda\n"


def test_export_markdown_overwrite_true(tmp_path: Path):
    target = tmp_path / "sobreposta.md"
    target.write_text("Versao inicial", encoding="utf-8")

    export_markdown("Versao final atualizada", target, overwrite=True)

    assert target.read_text(encoding="utf-8") == "Versao final atualizada\n"


def test_export_markdown_overwrite_false_raises_error(tmp_path: Path):
    target = tmp_path / "imutavel.md"
    target.write_text("Conteudo original protegido", encoding="utf-8")

    with pytest.raises(DestinationExistsError) as exc_info:
        export_markdown("Tentativa de sobrescrita", target, overwrite=False)

    assert str(target.resolve()) in str(exc_info.value)
    assert target.read_text(encoding="utf-8") == "Conteudo original protegido"


def test_export_markdown_ensure_newline_flag(tmp_path: Path):
    target1 = tmp_path / "sem_newline.md"
    export_markdown("Linha sem quebra", target1, ensure_newline=False)
    assert target1.read_text(encoding="utf-8") == "Linha sem quebra"

    target2 = tmp_path / "com_newline_duplo.md"
    export_markdown("Linha com quebra\n", target2, ensure_newline=True)
    assert target2.read_text(encoding="utf-8") == "Linha com quebra\n"


def test_export_markdown_atomic_cleanup_on_failure(tmp_path: Path, monkeypatch):
    import os

    target = tmp_path / "falha_atomica.md"

    def mock_replace(src, dst):
        raise OSError("Falha simulada de disco no replace")

    monkeypatch.setattr(os, "replace", mock_replace)

    with pytest.raises(MarkdownExporterError) as exc_info:
        export_markdown("Conteudo nao gravado", target)

    assert "Falha ao exportar arquivo Markdown" in str(exc_info.value)
    assert not target.exists()
    assert len(list(tmp_path.glob("*.tmp"))) == 0


def test_export_markdown_invalid_content_type(tmp_path: Path):
    target = tmp_path / "invalido.md"
    with pytest.raises(TypeError) as exc_info:
        export_markdown(12345, target)  # type: ignore

    assert "Tipo de conteudo nao suportado" in str(exc_info.value)
    assert not target.exists()


def test_export_markdown_target_as_directory_with_document(tmp_path: Path):
    doc = DocumentStructure(
        source_path="relatorios/financeiro_2026.pdf",
        total_pages=2,
        strategy=ExtractionStrategy.NATIVE_TEXT,
        blocks=[TextBlock(page_number=1, block_type=BlockType.PARAGRAPH, raw_text="Balanco anual")],
    )

    result = export_markdown(doc, tmp_path)

    expected = tmp_path / "financeiro_2026.md"
    assert result == expected.resolve()
    assert expected.exists()
    assert "Balanco anual" in expected.read_text(encoding="utf-8")


def test_export_markdown_target_as_directory_with_string(tmp_path: Path):
    result = export_markdown("Texto avulso", tmp_path)

    expected = tmp_path / "output.md"
    assert result == expected.resolve()
    assert expected.exists()


def test_export_markdown_without_extension_appends_md(tmp_path: Path):
    target_no_ext = tmp_path / "sem_extensao"
    result = export_markdown("Texto qualquer", target_no_ext)

    assert result.suffix == ".md"
    assert result.name == "sem_extensao.md"
    assert result.exists()


def test_markdown_exporter_class_basic(tmp_path: Path):
    exporter = MarkdownExporter(output_dir=tmp_path)
    assert exporter.output_dir == tmp_path
    assert exporter.overwrite is True
    assert exporter.ensure_newline is True

    result = exporter.export("# Titulo", filename="nota.md")
    assert result == (tmp_path / "nota.md").resolve()
    assert result.exists()


def test_markdown_exporter_class_relative_output_path(tmp_path: Path):
    exporter = MarkdownExporter(output_dir=tmp_path)
    result = exporter.export("Conteudo relativo", output_path="subpasta/doc.md")

    assert result == (tmp_path / "subpasta" / "doc.md").resolve()
    assert result.exists()


def test_markdown_exporter_class_export_document(tmp_path: Path):
    exporter = MarkdownExporter(output_dir=tmp_path)
    doc = DocumentStructure(
        source_path="origem/manual_usuario.pdf",
        total_pages=5,
        strategy=ExtractionStrategy.NATIVE_TEXT,
        blocks=[
            TextBlock(
                page_number=1,
                block_type=BlockType.HEADING,
                raw_text="Instrucoes de Uso",
                heading_level=1,
            )
        ],
    )

    result = exporter.export_document(doc)

    assert result == (tmp_path / "manual_usuario.md").resolve()
    assert result.exists()
    assert "# Instrucoes de Uso" in result.read_text(encoding="utf-8")


def test_markdown_exporter_class_export_document_custom_filename(tmp_path: Path):
    exporter = MarkdownExporter(output_dir=tmp_path)
    doc = DocumentStructure(
        source_path="origem/manual_usuario.pdf",
        total_pages=1,
        strategy=ExtractionStrategy.NATIVE_TEXT,
        blocks=[],
    )

    result = exporter.export_document(doc, filename="guia_rapido.md")

    assert result == (tmp_path / "guia_rapido.md").resolve()
    assert result.exists()


def test_markdown_exporter_class_missing_destination_error():
    exporter = MarkdownExporter(output_dir=None)

    with pytest.raises(ValueError) as exc_info:
        exporter.export("Texto sem destino definido")

    assert "Caminho de destino ou nome de arquivo deve ser especificado" in str(
        exc_info.value
    )
