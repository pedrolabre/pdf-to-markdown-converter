import html

DEFAULT_CSS = """\
:root {
  --bg-color: #ffffff;
  --text-color: #24292f;
  --border-color: #d0d7de;
  --code-bg: #f6f8fa;
  --link-color: #0969da;
  --quote-color: #57609a;
  --table-stripe: #f6f8fa;
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg-color: #0d1117;
    --text-color: #c9d1d9;
    --border-color: #30363d;
    --code-bg: #161b22;
    --link-color: #58a6ff;
    --quote-color: #8b949e;
    --table-stripe: #161b22;
  }
}

* { box-sizing: border-box; }

body {
  margin: 0;
  padding: 2rem 1rem;
  background-color: var(--bg-color);
  color: var(--text-color);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.6;
}

.markdown-body { max-width: 850px; margin: 0 auto; word-wrap: break-word; }
h1, h2, h3, h4, h5, h6 { margin-top: 1.5rem; margin-bottom: 0.75rem; font-weight: 600; line-height: 1.25; }
h1 { font-size: 2rem; border-bottom: 1px solid var(--border-color); padding-bottom: 0.3rem; }
h2 { font-size: 1.5rem; border-bottom: 1px solid var(--border-color); padding-bottom: 0.3rem; }
h3 { font-size: 1.25rem; }
p, ul, ol, blockquote { margin-top: 0; margin-bottom: 1rem; }
ul, ol { padding-left: 2rem; }
li + li { margin-top: 0.25rem; }
blockquote { padding: 0.5rem 1rem; border-left: 4px solid var(--border-color); color: var(--quote-color); }
hr { height: 0.25rem; padding: 0; margin: 1.5rem 0; background-color: var(--border-color); border: 0; }
a { color: var(--link-color); text-decoration: none; }
a:hover { text-decoration: underline; }
img { max-width: 100%; height: auto; }
code, pre { font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace; font-size: 85%; }
code { padding: 0.2em 0.4em; background-color: var(--code-bg); border-radius: 4px; }
pre { padding: 1rem; overflow-x: auto; background-color: var(--code-bg); border: 1px solid var(--border-color); border-radius: 6px; line-height: 1.45; }
pre code { padding: 0; background-color: transparent; }
table { border-collapse: collapse; width: 100%; margin-bottom: 1rem; overflow-x: auto; display: block; }
th, td { padding: 0.5rem 0.75rem; border: 1px solid var(--border-color); }
th { background-color: var(--code-bg); font-weight: 600; }
tr:nth-child(2n) td { background-color: var(--table-stripe); }"""

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="{lang}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
{css}
  </style>
</head>
<body>
  <main class="markdown-body">
{content}
  </main>
</body>
</html>"""


def render_html_document(
    content: str,
    title: str = "Documento",
    lang: str = "pt-BR",
    extra_css: str = "",
) -> str:
    escaped_title = html.escape(title)
    css = DEFAULT_CSS
    if extra_css and extra_css.strip():
        css = f"{css}\n{extra_css.strip()}"
    return HTML_TEMPLATE.format(
        lang=lang,
        title=escaped_title,
        css=css,
        content=content,
    )


build_html_document = render_html_document

__all__ = [
    "DEFAULT_CSS",
    "HTML_TEMPLATE",
    "build_html_document",
    "render_html_document",
]
