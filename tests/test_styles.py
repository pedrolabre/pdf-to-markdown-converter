from pdf_to_markdown_converter.exporters.styles import (
    DEFAULT_CSS,
    HTML_TEMPLATE,
    build_html_document,
    render_html_document,
)


def test_default_css_has_css_variables_and_dark_mode():
    assert ":root" in DEFAULT_CSS
    assert "@media (prefers-color-scheme: dark)" in DEFAULT_CSS
    assert "--bg-color" in DEFAULT_CSS
    assert "--text-color" in DEFAULT_CSS
    assert "--border-color" in DEFAULT_CSS
    assert "--code-bg" in DEFAULT_CSS
    assert "--link-color" in DEFAULT_CSS
    assert "--quote-color" in DEFAULT_CSS
    assert "--table-stripe" in DEFAULT_CSS


def test_default_css_has_system_font_stacks_without_external_dependencies():
    assert "-apple-system" in DEFAULT_CSS
    assert "BlinkMacSystemFont" in DEFAULT_CSS
    assert "Segoe UI" in DEFAULT_CSS
    assert "ui-monospace" in DEFAULT_CSS
    assert "SFMono-Regular" in DEFAULT_CSS
    assert "Consolas" in DEFAULT_CSS

    assert "http://" not in DEFAULT_CSS
    assert "https://" not in DEFAULT_CSS
    assert "@import" not in DEFAULT_CSS
    assert "url(" not in DEFAULT_CSS


def test_default_css_styles_tables():
    assert "table {" in DEFAULT_CSS
    assert "border-collapse: collapse" in DEFAULT_CSS
    assert "th, td {" in DEFAULT_CSS
    assert "tr:nth-child(2n) td {" in DEFAULT_CSS
    assert "overflow-x: auto" in DEFAULT_CSS


def test_default_css_styles_code_blocks():
    assert "code, pre {" in DEFAULT_CSS
    assert "code {" in DEFAULT_CSS
    assert "pre {" in DEFAULT_CSS
    assert "pre code {" in DEFAULT_CSS
    assert "border-radius" in DEFAULT_CSS


def test_default_css_styles_semantic_elements():
    assert "h1, h2, h3, h4, h5, h6 {" in DEFAULT_CSS
    assert "h1 {" in DEFAULT_CSS
    assert "h2 {" in DEFAULT_CSS
    assert "blockquote {" in DEFAULT_CSS
    assert "hr {" in DEFAULT_CSS
    assert "a {" in DEFAULT_CSS
    assert "a:hover {" in DEFAULT_CSS
    assert "img {" in DEFAULT_CSS
    assert "max-width: 100%" in DEFAULT_CSS
    assert ".markdown-body {" in DEFAULT_CSS
    assert "max-width: 850px" in DEFAULT_CSS


def test_html_template_structure():
    assert HTML_TEMPLATE.startswith("<!DOCTYPE html>")
    assert '<html lang="{lang}">' in HTML_TEMPLATE
    assert '<meta charset="utf-8">' in HTML_TEMPLATE
    assert '<meta name="viewport" content="width=device-width, initial-scale=1.0">' in HTML_TEMPLATE
    assert "<title>{title}</title>" in HTML_TEMPLATE
    assert "<style>\n{css}\n  </style>" in HTML_TEMPLATE
    assert '<main class="markdown-body">\n{content}\n  </main>' in HTML_TEMPLATE
    assert "</body>" in HTML_TEMPLATE
    assert "</html>" in HTML_TEMPLATE


def test_render_html_document_with_defaults():
    html_output = render_html_document("<p>Ola Mundo</p>")
    assert html_output.startswith("<!DOCTYPE html>")
    assert '<html lang="pt-BR">' in html_output
    assert "<title>Documento</title>" in html_output
    assert "<style>\n" + DEFAULT_CSS + "\n  </style>" in html_output
    assert '<main class="markdown-body">\n<p>Ola Mundo</p>\n  </main>' in html_output


def test_render_html_document_with_custom_metadata():
    content = "<h1>Titulo</h1>\n<p>Conteudo em ingles</p>"
    html_output = render_html_document(
        content=content,
        title="Custom Report",
        lang="en-US",
    )
    assert '<html lang="en-US">' in html_output
    assert "<title>Custom Report</title>" in html_output
    assert content in html_output


def test_render_html_document_escapes_special_characters_in_title():
    special_title = 'Relatorio & Analise <2026> "Final"'
    html_output = render_html_document("<p>Corpo</p>", title=special_title)
    assert "<title>Relatorio &amp; Analise &lt;2026&gt; &quot;Final&quot;</title>" in html_output
    assert "<2026>" not in html_output


def test_render_html_document_with_extra_css():
    extra = ".custom-class { color: red; font-size: 14px; }"
    html_output = render_html_document("<p>Teste</p>", extra_css=extra)
    assert extra in html_output
    assert f"{DEFAULT_CSS}\n{extra}" in html_output


def test_render_html_document_with_empty_or_whitespace_extra_css():
    output_none = render_html_document("<p>Teste</p>", extra_css="")
    output_spaces = render_html_document("<p>Teste</p>", extra_css="   \n  ")
    assert "<style>\n" + DEFAULT_CSS + "\n  </style>" in output_none
    assert output_none == output_spaces


def test_render_html_document_preserves_unicode_and_portuguese_accents():
    accented_content = (
        "<h1>Especificação de Extração & Reconstrução</h1>\n"
        "<p>Configuração, validação, acentuação: á, é, í, ó, ú, ã, õ, ç, ê, ô.</p>\n"
        "<table><tr><th>Seção</th><th>Métrica</th></tr><tr><td>Início</td><td>100%</td></tr></table>"
    )
    title = "Documentação Técnica — Relatório de Extração"
    html_output = render_html_document(content=accented_content, title=title)
    assert f"<title>{title}</title>" in html_output
    assert accented_content in html_output


def test_render_html_document_with_empty_content():
    html_output = render_html_document("")
    assert '<main class="markdown-body">\n\n  </main>' in html_output


def test_render_html_document_determinism():
    content = "<p>Conteudo deterministico</p>"
    run1 = render_html_document(content, title="Determinismo", lang="pt-BR")
    run2 = render_html_document(content, title="Determinismo", lang="pt-BR")
    assert run1 == run2


def test_build_html_document_alias_matches_render():
    assert build_html_document is render_html_document
    result1 = build_html_document("<p>Texto</p>", title="Alias Test")
    result2 = render_html_document("<p>Texto</p>", title="Alias Test")
    assert result1 == result2
