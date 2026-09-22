from pathlib import Path
from unittest.mock import patch

import pytest

from pdf_to_markdown_converter.domain.models import (
    BlockType,
    DocumentStructure,
    ExtractionStrategy,
    TextBlock,
)
from pdf_to_markdown_converter.exporters import (
    DestinationExistsError,
    HtmlExportError,
    HtmlExporter,
    HtmlExporterError,
    compile_markdown_to_html,
    export_html,
    render_html,
)
from pdf_to_markdown_converter.exporters.html_exporter import (
    HtmlDestinationExistsError,
    _coerce_markdown_text,
    _resolve_target_path,
)


def test_compile_markdown_headings_and_paragraphs():
    md = "# Titulo 1\n\n## Titulo 2\n\nEste e um paragrafo comum."
    html = compile_markdown_to_html(md)
    assert "<h1>Titulo 1</h1>" in html
    assert "<h2>Titulo 2</h2>" in html
    assert "<p>Este e um paragrafo comum.</p>" in html


def test_compile_markdown_tables():
    md = "| Nome | Idade |\n| --- | --- |\n| Alice | 30 |\n| Bob | 25 |"
    html = compile_markdown_to_html(md)
    assert "<table>" in html
    assert "<thead>" in html
    assert "<th>Nome</th>" in html
    assert "<tbody>" in html
    assert "<td>Alice</td>" in html


def test_compile_markdown_fenced_code():
    md = "```python\ndef saudacao():\n    return 'ola'\n```"
    html = compile_markdown_to_html(md)
    assert "<pre><code" in html
    assert "def saudacao():" in html
    assert "language-python" in html


def test_compile_markdown_lists():
    ul_md = "- Item A\n- Item B"
    ul_html = compile_markdown_to_html(ul_md)
    assert "<ul>" in ul_html
    assert "<li>Item A</li>" in ul_html
    assert "<li>Item B</li>" in ul_html

    ol_md = "1. Primeiro\n2. Segundo"
    ol_html = compile_markdown_to_html(ol_md)
    assert "<ol>" in ol_html
    assert "<li>Primeiro</li>" in ol_html
    assert "<li>Segundo</li>" in ol_html


def test_compile_markdown_empty_and_whitespace():
    assert compile_markdown_to_html("") == ""
    assert compile_markdown_to_html("   ").strip() == ""


def test_coerce_markdown_text_types():
    assert _coerce_markdown_text("# Texto puro") == "# Texto puro"

    block = TextBlock(
        page_number=1,
        block_type=BlockType.HEADING,
        raw_text="Meu Cabecalho",
        heading_level=1,
    )
    doc = DocumentStructure(
        source_path="/docs/manual.pdf",
        total_pages=1,
        strategy=ExtractionStrategy.NATIVE_TEXT,
        blocks=[block],
    )
    assert "# Meu Cabecalho" in _coerce_markdown_text(doc)
    assert "# Meu Cabecalho" in _coerce_markdown_text([block])

    with pytest.raises(TypeError, match="Tipo de conteudo nao suportado"):
        _coerce_markdown_text(12345)  # type: ignore


def test_render_html_structure_and_defaults():
    doc_html = render_html("# Ola Mundo")
    assert "<!DOCTYPE html>" in doc_html
    assert '<html lang="pt-BR">' in doc_html
    assert '<meta charset="utf-8">' in doc_html
    assert "<title>Documento</title>" in doc_html
    assert '<main class="markdown-body">' in doc_html
    assert "<h1>Ola Mundo</h1>" in doc_html


def test_render_html_custom_metadata_and_escaping():
    doc_html = render_html(
        content="Texto com acentuacao: acao, configuracao, cafe.",
        title="Relatorio <Tecnico> & 'Seguro'",
        lang="en-US",
        extra_css=".custom-box { display: block; }",
    )
    assert '<html lang="en-US">' in doc_html
    assert "<title>Relatorio &lt;Tecnico&gt; &amp; &#x27;Seguro&#x27;</title>" in doc_html
    assert ".custom-box { display: block; }" in doc_html
    assert "Texto com acentuacao: acao, configuracao, cafe." in doc_html


def test_render_html_inferred_title_from_document():
    doc = DocumentStructure(
        source_path="meu_relatorio_anual.pdf",
        total_pages=1,
        strategy=ExtractionStrategy.NATIVE_TEXT,
        blocks=[TextBlock(1, BlockType.PARAGRAPH, "Conteudo")],
    )
    doc_html = render_html(doc)
    assert "<title>meu_relatorio_anual</title>" in doc_html


def test_resolve_target_path():
    doc = DocumentStructure(
        source_path="artigo.pdf",
        total_pages=1,
        strategy=ExtractionStrategy.NATIVE_TEXT,
        blocks=[],
    )
    resolved = _resolve_target_path("teste", "saida")
    assert resolved.name == "saida.html"

    resolved_dir = _resolve_target_path(doc, Path("."), filename=None)
    assert resolved_dir.name == "artigo.html"

    with pytest.raises(ValueError, match="Caminho de destino ou nome de arquivo"):
        _resolve_target_path("sem_origem", None, default_dir=Path.cwd())


def test_export_html_atomic_write_and_utf8(tmp_path: Path):
    dest = tmp_path / "sub" / "relatorio.html"
    content = "# Titulo Principal\n\nAcentuacao plena: maçã, café, ênfase, ação."

    out_path = export_html(content, dest, title="Relatorio de Teste")
    assert out_path.is_file()
    assert out_path == dest.resolve()

    raw_bytes = out_path.read_bytes()
    decoded = raw_bytes.decode("utf-8")
    assert "maçã, café, ênfase, ação." in decoded
    assert "<title>Relatorio de Teste</title>" in decoded
    assert decoded.endswith("\n")


def test_export_html_overwrite_flag(tmp_path: Path):
    dest = tmp_path / "arquivo.html"
    dest.write_text("conteudo original", encoding="utf-8")

    with pytest.raises(DestinationExistsError, match="Arquivo de destino ja existe"):
        export_html("novo conteudo", dest, overwrite=False)

    assert dest.read_text(encoding="utf-8") == "conteudo original"

    export_html("novo conteudo sobrescrito", dest, overwrite=True)
    assert "novo conteudo sobrescrito" in dest.read_text(encoding="utf-8")


def test_export_html_cleanup_on_failure(tmp_path: Path):
    dest = tmp_path / "falha.html"

    with patch("os.replace", side_effect=OSError("Erro de gravacao simulado")):
        with pytest.raises(HtmlExporterError, match="Falha ao exportar arquivo HTML"):
            export_html("teste", dest)

    assert not dest.exists()
    tmp_files = list(tmp_path.glob(".*.tmp"))
    assert len(tmp_files) == 0


def test_export_html_from_document_structure(tmp_path: Path):
    dest = tmp_path / "doc.html"
    block1 = TextBlock(1, BlockType.HEADING, "Sumario", heading_level=1)
    block2 = TextBlock(1, BlockType.PARAGRAPH, "Primeiro paragrafo de teste.")
    doc = DocumentStructure(
        source_path="meu_doc.pdf",
        total_pages=1,
        strategy=ExtractionStrategy.NATIVE_TEXT,
        blocks=[block1, block2],
    )

    out = export_html(doc, dest)
    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert "<h1>Sumario</h1>" in text
    assert "<p>Primeiro paragrafo de teste.</p>" in text
    assert "<title>meu_doc</title>" in text


def test_html_exporter_class_usage(tmp_path: Path):
    exporter = HtmlExporter(
        output_dir=tmp_path,
        overwrite=True,
        title="Padrao",
        lang="pt-BR",
        extra_css="body { font-size: 16px; }",
    )

    body = exporter.compile_body("# Fragmento")
    assert "<h1>Fragmento</h1>" in body
    assert "<!DOCTYPE html>" not in body

    full = exporter.compile("# Documento Completo")
    assert "<!DOCTYPE html>" in full
    assert "<title>Padrao</title>" in full
    assert "body { font-size: 16px; }" in full

    path = exporter.export("# Ola Exporter", filename="saida_exp.html")
    assert path.is_file()
    assert path.parent == tmp_path.resolve()
    assert "<h1>Ola Exporter</h1>" in path.read_text(encoding="utf-8")

    doc = DocumentStructure(
        source_path="guia.pdf",
        total_pages=1,
        strategy=ExtractionStrategy.NATIVE_TEXT,
        blocks=[TextBlock(1, BlockType.HEADING, "Guia Rapido", heading_level=2)],
    )
    doc_path = exporter.export_document(doc, filename="guia_renderizado.html")
    assert "<h2>Guia Rapido</h2>" in doc_path.read_text(encoding="utf-8")


def test_html_exporter_error_aliases():
    assert issubclass(HtmlDestinationExistsError, HtmlExporterError)
    assert issubclass(HtmlDestinationExistsError, FileExistsError)
    assert issubclass(HtmlDestinationExistsError, DestinationExistsError)
    assert HtmlExportError is HtmlExporterError
