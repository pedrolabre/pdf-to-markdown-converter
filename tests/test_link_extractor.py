from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pymupdf
import pytest

from pdf_to_markdown_converter.core.link_extractor import (
    apply_links_to_block,
    find_page_uri_links,
    map_page_words_to_links,
)
from pdf_to_markdown_converter.core.native_extractor import extract_page_blocks


def test_find_page_uri_links_no_links() -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    assert find_page_uri_links(page) == []
    doc.close()


def test_find_page_uri_links_with_uri() -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    rect = pymupdf.Rect(50, 50, 150, 80)
    page.insert_link({
        "kind": pymupdf.LINK_URI,
        "from": rect,
        "uri": "https://example.com",
    })
    reloaded_doc = pymupdf.open(stream=doc.tobytes(), filetype="pdf")
    links = find_page_uri_links(reloaded_doc[0])
    assert len(links) == 1
    assert links[0]["uri"] == "https://example.com"
    doc.close()
    reloaded_doc.close()


def test_map_page_words_to_links_empty() -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    assert map_page_words_to_links(page) is None
    doc.close()


def test_apply_links_to_block_empty() -> None:
    assert apply_links_to_block(None, "Texto normal", "Texto normal") == ("Texto normal", "Texto normal")
    assert apply_links_to_block([], "Texto normal", "Texto normal") == ("Texto normal", "Texto normal")
    unlinked = [("palavra", None)]
    assert apply_links_to_block(unlinked, "palavra", "palavra") == ("palavra", "palavra")


def test_apply_links_to_block_entire_block() -> None:
    words = [("app.gestacare.tech", "https://app.gestacare.tech/"), ("➔", "https://app.gestacare.tech/")]
    norm, raw = apply_links_to_block(words, "app.gestacare.tech ➔", "app.gestacare.tech\n➔")
    assert norm == "[app.gestacare.tech ➔](https://app.gestacare.tech/)"
    assert raw == "[app.gestacare.tech\n➔](https://app.gestacare.tech/)"


def test_apply_links_to_block_inline_sequence() -> None:
    words = [
        ("Acesse", None),
        ("o", None),
        ("Portal", "https://portal.com"),
        ("UBS", "https://portal.com"),
        ("aqui.", None),
    ]
    norm, raw = apply_links_to_block(
        words,
        "Acesse o Portal UBS aqui.",
        "Acesse o Portal UBS aqui.",
    )
    assert norm == "Acesse o [Portal UBS](https://portal.com) aqui."
    assert raw == "Acesse o [Portal UBS](https://portal.com) aqui."


def test_extract_page_blocks_integrates_links(tmp_path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=500, height=500)
    page.insert_text((50, 100), "Clique no link aqui para acessar.")
    link_rect = pymupdf.Rect(45, 85, 250, 115)
    page.insert_link({
        "kind": pymupdf.LINK_URI,
        "from": link_rect,
        "uri": "https://sistema.saude.gov.br",
    })
    pdf_bytes = doc.tobytes()
    doc.close()

    reloaded_doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    blocks = extract_page_blocks(reloaded_doc[0])
    assert len(blocks) >= 1
    assert "https://sistema.saude.gov.br" in blocks[0].normalized_text
    assert blocks[0].normalized_text.startswith("[Clique no link")
    reloaded_doc.close()
