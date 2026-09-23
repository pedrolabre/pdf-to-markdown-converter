from __future__ import annotations

import re
from typing import Any

import pymupdf


def find_page_uri_links(page: pymupdf.Page) -> list[dict[str, Any]]:
    """Extrai todas as anotações de links interativos com URI válida da página."""
    try:
        links = page.get_links()
    except Exception:
        return []
    return [l for l in links if l.get("uri") and l.get("from")]


def map_page_words_to_links(
    page: pymupdf.Page,
) -> dict[int, list[tuple[str, str | None]]] | None:
    """Mapeia palavras de cada bloco da página para seus respectivos links interativos (URIs)."""
    uri_links = find_page_uri_links(page)
    if not uri_links:
        return None

    try:
        words = page.get_text("words")
    except Exception:
        return None

    words_by_block: dict[int, list[tuple[str, str | None]]] = {}

    for w in words:
        x0, y0, x1, y1, w_text, b_no, _l_no, _w_no = w[:8]
        w_rect = pymupdf.Rect(x0, y0, x1, y1)
        w_center = pymupdf.Point((x0 + x1) / 2.0, (y0 + y1) / 2.0)

        matched_uri: str | None = None
        for l in uri_links:
            l_rect = pymupdf.Rect(l["from"])
            if w_center in l_rect or w_rect.intersects(l_rect):
                uri_val = l.get("uri")
                if uri_val:
                    matched_uri = str(uri_val).strip()
                    break

        if b_no not in words_by_block:
            words_by_block[b_no] = []
        words_by_block[b_no].append((str(w_text), matched_uri))

    return words_by_block


def _inject_markdown_link(text: str, phrase: str, uri: str) -> str:
    """Envolve a primeira ocorrência segura da frase com formatação de link Markdown."""
    if not phrase or not uri:
        return text
    escaped = re.escape(phrase)
    pattern = rf"(?<!\[)\b{escaped}\b(?!\])"
    return re.sub(pattern, f"[{phrase}]({uri})", text, count=1)


def apply_links_to_block(
    words_info: list[tuple[str, str | None]] | None,
    norm_str: str,
    raw_str: str,
) -> tuple[str, str]:
    """Aplica formatação Markdown de hiperlinks a blocos ou trechos de texto vinculados."""
    if not words_info or not norm_str.strip():
        return norm_str, raw_str

    linked_words = [w for w in words_info if w[1] is not None]
    if not linked_words:
        return norm_str, raw_str

    uris = {w[1] for w in linked_words if w[1]}

    # Caso 1: Bloco integral ou maioria significativa (>= 70%) vinculada ao mesmo link
    if len(uris) == 1 and len(linked_words) >= max(1, int(len(words_info) * 0.7)):
        uri = next(iter(uris))
        if not norm_str.startswith("[") or not norm_str.endswith(f"]({uri})"):
            norm_str = f"[{norm_str}]({uri})"
        if not raw_str.startswith("[") or not raw_str.endswith(f"]({uri})"):
            raw_str = f"[{raw_str}]({uri})"
        return norm_str, raw_str

    # Caso 2: Links parciais em sequência contínua de palavras
    curr_seq: list[str] = []
    curr_uri: str | None = None

    for w_text, w_uri in words_info:
        if w_uri == curr_uri and curr_uri is not None:
            curr_seq.append(w_text)
        else:
            if curr_seq and curr_uri:
                phrase = " ".join(curr_seq)
                norm_str = _inject_markdown_link(norm_str, phrase, curr_uri)
                raw_str = _inject_markdown_link(raw_str, phrase, curr_uri)
            curr_seq = [w_text] if w_uri else []
            curr_uri = w_uri

    if curr_seq and curr_uri:
        phrase = " ".join(curr_seq)
        norm_str = _inject_markdown_link(norm_str, phrase, curr_uri)
        raw_str = _inject_markdown_link(raw_str, phrase, curr_uri)

    return norm_str, raw_str
