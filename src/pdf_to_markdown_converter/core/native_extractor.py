from collections import deque
from collections.abc import Sequence
from functools import cmp_to_key
from pathlib import Path
from typing import Any

import pymupdf

from pdf_to_markdown_converter.core.line_normalizer import normalize_line_breaks
from pdf_to_markdown_converter.core.link_extractor import (
    apply_links_to_block,
    map_page_words_to_links,
)
from pdf_to_markdown_converter.core.pdf_reader import open_pdf
from pdf_to_markdown_converter.core.text_cleaner import clean_text
from pdf_to_markdown_converter.domain.models import (
    BlockType,
    DocumentStructure,
    ExtractionStrategy,
    TextBlock,
)

DEFAULT_Y_TOLERANCE: float = 3.0
DEFAULT_X_TOLERANCE: float = 3.0


def sort_blocks_spatially(
    blocks: Sequence[TextBlock],
    y_tolerance: float = DEFAULT_Y_TOLERANCE,
    x_tolerance: float = DEFAULT_X_TOLERANCE,
) -> list[TextBlock]:
    if len(blocks) <= 1:
        return list(blocks)

    y_tol = max(y_tolerance, 0.0)

    def can_merge(b1: TextBlock, b2: TextBlock) -> bool:
        top, bottom = (b1, b2) if b1.bbox[1] <= b2.bbox[1] else (b2, b1)
        if top.bbox[3] > bottom.bbox[1] + y_tol:
            return False
        w1 = top.bbox[2] - top.bbox[0]
        w2 = bottom.bbox[2] - bottom.bbox[0]
        if max(w1, w2) <= 0:
            return False
        if min(w1, w2) / max(w1, w2) < 0.6:
            return False
        x_overlap = min(top.bbox[2], bottom.bbox[2]) - max(top.bbox[0], bottom.bbox[0])
        if x_overlap / min(w1, w2) < 0.6:
            return False
        y_min = top.bbox[3] - y_tol
        y_max = bottom.bbox[1] + y_tol
        top_left = min(top.bbox[0], bottom.bbox[0])
        top_right = max(top.bbox[2], bottom.bbox[2])
        for other in blocks:
            if other is top or other is bottom:
                continue
            if other.bbox[1] >= y_min and other.bbox[3] <= y_max:
                oth_x_ov = min(top_right, other.bbox[2]) - max(top_left, other.bbox[0])
                if oth_x_ov > 0:
                    return False
        return True

    n = len(blocks)
    adj: dict[int, set[int]] = {i: set() for i in range(n)}
    for i in range(n):
        b1 = blocks[i]
        for j in range(i + 1, n):
            b2 = blocks[j]
            top, bottom = (b1, b2) if b1.bbox[1] <= b2.bbox[1] else (b2, b1)
            if top.bbox[3] > bottom.bbox[1] + y_tol:
                continue
            if can_merge(top, bottom):
                adj[i].add(j)
                adj[j].add(i)

    visited: set[int] = set()
    groups: list[dict[str, Any]] = []
    for i in range(n):
        if i not in visited:
            comp: list[int] = []
            queue: deque[int] = deque([i])
            visited.add(i)
            while queue:
                curr = queue.popleft()
                comp.append(curr)
                for neighbor in adj[curr]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)

            group_blocks = [blocks[idx] for idx in comp]
            group_blocks.sort(key=lambda b: (b.bbox[1], b.bbox[0]))
            min_x = min(b.bbox[0] for b in group_blocks)
            min_y = min(b.bbox[1] for b in group_blocks)
            max_x = max(b.bbox[2] for b in group_blocks)
            max_y = max(b.bbox[3] for b in group_blocks)
            groups.append(
                {
                    "blocks": group_blocks,
                    "bbox": (min_x, min_y, max_x, max_y),
                }
            )

    def compare_groups(g1: dict[str, Any], g2: dict[str, Any]) -> int:
        b1, b2 = g1["bbox"], g2["bbox"]
        if b1[3] <= b2[1] + y_tol:
            return -1
        if b2[3] <= b1[1] + y_tol:
            return 1
        if b1[0] < b2[0]:
            return -1
        if b1[0] > b2[0]:
            return 1
        return -1 if b1[1] < b2[1] else 1

    sorted_groups = sorted(groups, key=cmp_to_key(compare_groups))

    result: list[TextBlock] = []
    for g in sorted_groups:
        result.extend(g["blocks"])
    return result


def extract_page_blocks(
    page: pymupdf.Page,
    page_number: int | None = None,
    *,
    sort_spatial: bool = True,
    y_tolerance: float = DEFAULT_Y_TOLERANCE,
    x_tolerance: float = DEFAULT_X_TOLERANCE,
    normalize: bool = True,
    ignore_empty: bool = True,
) -> list[TextBlock]:
    if page_number is None:
        page_number = page.number + 1

    raw_blocks = page.get_text("blocks")
    words_by_block = map_page_words_to_links(page)
    blocks: list[TextBlock] = []

    for b_idx, raw_block in enumerate(raw_blocks):
        x0, y0, x1, y1, text, _block_no, block_type = raw_block[:7]
        if block_type != 0:
            continue

        raw_str = str(text)
        if ignore_empty and not raw_str.strip():
            continue

        if normalize:
            cleaned = clean_text(raw_str)
            norm_str = normalize_line_breaks(cleaned).strip()
        else:
            norm_str = raw_str.strip()

        if words_by_block and b_idx in words_by_block:
            norm_str, raw_str = apply_links_to_block(words_by_block[b_idx], norm_str, raw_str)

        bbox = (
            round(float(x0), 2),
            round(float(y0), 2),
            round(float(x1), 2),
            round(float(y1), 2),
        )

        blocks.append(
            TextBlock(
                page_number=page_number,
                block_type=BlockType.PARAGRAPH,
                raw_text=raw_str,
                normalized_text=norm_str,
                bbox=bbox,
                heading_level=0,
            )
        )

    if sort_spatial and len(blocks) > 1:
        blocks = sort_blocks_spatially(
            blocks,
            y_tolerance=y_tolerance,
            x_tolerance=x_tolerance,
        )

    return blocks


def _extract_from_open_doc(
    doc: pymupdf.Document,
    source_path: str,
    sort_spatial: bool,
    y_tolerance: float,
    x_tolerance: float,
    normalize: bool,
    ignore_empty: bool,
) -> DocumentStructure:
    all_blocks: list[TextBlock] = []
    for page_idx in range(len(doc)):
        page = doc[page_idx]
        page_blocks = extract_page_blocks(
            page=page,
            page_number=page_idx + 1,
            sort_spatial=sort_spatial,
            y_tolerance=y_tolerance,
            x_tolerance=x_tolerance,
            normalize=normalize,
            ignore_empty=ignore_empty,
        )
        all_blocks.extend(page_blocks)

    return DocumentStructure(
        source_path=source_path,
        total_pages=len(doc),
        strategy=ExtractionStrategy.NATIVE_TEXT,
        blocks=all_blocks,
    )


def extract_document_structure(
    source: pymupdf.Document | str | Path | bytes,
    *,
    password: str = "",
    sort_spatial: bool = True,
    y_tolerance: float = DEFAULT_Y_TOLERANCE,
    x_tolerance: float = DEFAULT_X_TOLERANCE,
    normalize: bool = True,
    ignore_empty: bool = True,
) -> DocumentStructure:
    if isinstance(source, pymupdf.Document):
        return _extract_from_open_doc(
            doc=source,
            source_path=source.name or "<memory>",
            sort_spatial=sort_spatial,
            y_tolerance=y_tolerance,
            x_tolerance=x_tolerance,
            normalize=normalize,
            ignore_empty=ignore_empty,
        )

    resolved_path = str(source) if isinstance(source, (str, Path)) else "<memory>"
    with open_pdf(source, password=password) as doc:
        return _extract_from_open_doc(
            doc=doc,
            source_path=resolved_path,
            sort_spatial=sort_spatial,
            y_tolerance=y_tolerance,
            x_tolerance=x_tolerance,
            normalize=normalize,
            ignore_empty=ignore_empty,
        )


class NativeExtractor:
    def __init__(
        self,
        *,
        y_tolerance: float = DEFAULT_Y_TOLERANCE,
        x_tolerance: float = DEFAULT_X_TOLERANCE,
        sort_spatial: bool = True,
        normalize: bool = True,
        ignore_empty: bool = True,
    ) -> None:
        self.y_tolerance = y_tolerance
        self.x_tolerance = x_tolerance
        self.sort_spatial = sort_spatial
        self.normalize = normalize
        self.ignore_empty = ignore_empty

    def extract_page(
        self,
        page: pymupdf.Page,
        page_number: int | None = None,
    ) -> list[TextBlock]:
        return extract_page_blocks(
            page=page,
            page_number=page_number,
            sort_spatial=self.sort_spatial,
            y_tolerance=self.y_tolerance,
            x_tolerance=self.x_tolerance,
            normalize=self.normalize,
            ignore_empty=self.ignore_empty,
        )

    def extract(
        self,
        source: pymupdf.Document | str | Path | bytes,
        password: str = "",
    ) -> DocumentStructure:
        return extract_document_structure(
            source=source,
            password=password,
            sort_spatial=self.sort_spatial,
            y_tolerance=self.y_tolerance,
            x_tolerance=self.x_tolerance,
            normalize=self.normalize,
            ignore_empty=self.ignore_empty,
        )
