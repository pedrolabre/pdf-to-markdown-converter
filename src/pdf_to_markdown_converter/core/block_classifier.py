from collections.abc import Sequence
from dataclasses import replace
import re

from pdf_to_markdown_converter.domain.models import (
    BlockType,
    DocumentStructure,
    TextBlock,
)

MAX_HEADING_LENGTH: int = 150
MAX_HEADING_LINES: int = 2

_CODE_KEYWORD_PATTERNS: tuple[str, ...] = (
    r"^(def\s+\w+\s*\(|class\s+\w+[:\(]|import\s+[a-zA-Z_]\w*|from\s+[a-zA-Z_]\w*\s+import\s+)",
    r"^(function\s+\w+\s*\(|const\s+\w+\s*=|let\s+\w+\s*=|var\s+\w+\s*=)",
    r"^(return(\s+[^.!?]+)?(;)?$|return\s+.*;$|console\.log\(|print\()",
    r"^(public\s+(static\s+)?(void|class|int|String|boolean)|#include\s+<)",
    r"^(SELECT\s+.+\s+FROM\s+|INSERT\s+INTO\s+|CREATE\s+TABLE\s+)",
    r"^[{}\[\]();]+$",
    r".*[{};]\s*$",
)

_UNORDERED_LIST_PATTERN: re.Pattern[str] = re.compile(
    r"^([-*+•◦▪▫–—])\s+"
)

_ORDERED_LIST_PATTERN: re.Pattern[str] = re.compile(
    r"^(\d+[\.\)]|\([0-9]+\)|[a-zA-Z][\.\)]|[ivxlcdmIVXLCDM]+[\.\)])\s+"
)

_CHAPTER_KEYWORD_PATTERN: re.Pattern[str] = re.compile(
    r"^(Capítulo|Capitulo|Chapter|Parte|Part)\b",
    re.IGNORECASE,
)

_SECTION_KEYWORD_PATTERN: re.Pattern[str] = re.compile(
    r"^(Seção|Secao|Section|Anexo|Apêndice|Apendice|Appendix)\b",
    re.IGNORECASE,
)


def is_code_block(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False

    if stripped.startswith("```") or stripped.startswith("~~~"):
        return True

    lines = [line for line in text.split("\n") if line.strip()]
    if lines and all(line.startswith("    ") or line.startswith("\t") for line in lines):
        return True

    if all(
        _UNORDERED_LIST_PATTERN.match(line.strip())
        or _ORDERED_LIST_PATTERN.match(line.strip())
        for line in lines
    ):
        return False

    matching_lines = sum(
        1
        for line in lines
        if any(
            re.search(pattern, line.strip(), re.IGNORECASE)
            for pattern in _CODE_KEYWORD_PATTERNS
        )
    )
    if matching_lines > 0 and (len(lines) == 1 or matching_lines >= len(lines) / 2):
        return True

    return False


def detect_heading(
    text: str, max_length: int = MAX_HEADING_LENGTH
) -> tuple[bool, int]:
    stripped = text.strip()
    if not stripped or len(stripped) > max_length:
        return False, 0

    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    if len(lines) > MAX_HEADING_LINES:
        return False, 0

    md_match = re.match(r"^(#{1,})\s+(.+)$", stripped)
    if md_match:
        level = min(6, max(1, len(md_match.group(1))))
        return True, level

    hier_match = re.match(r"^(\d+(?:\.\d+)+)\.?\s+(.+)$", stripped)
    if hier_match:
        depth = len(hier_match.group(1).split("."))
        level = min(6, max(1, depth))
        return True, level

    single_match = re.match(r"^(\d+)(?:\.|\s+-|\s+–)\s+(.+)$", stripped)
    if single_match and len(lines) == 1:
        title_body = single_match.group(2).strip()
        if not title_body.endswith((";", ",")) and not (
            title_body.endswith(".") and len(title_body.split()) > 6
        ):
            if title_body and (title_body[0].isupper() or title_body.isupper()):
                return True, 1

    if _CHAPTER_KEYWORD_PATTERN.search(stripped) and not stripped.endswith((".", ";")):
        return True, 1

    if _SECTION_KEYWORD_PATTERN.search(stripped) and not stripped.endswith((".", ";")):
        return True, 2

    alpha_chars = [char for char in stripped if char.isalpha()]
    if len(alpha_chars) >= 4 and all(char.isupper() for char in alpha_chars):
        if not stripped.endswith((".", ";", "!", "?", ",")):
            if not any(stripped.startswith(marker) for marker in ("- ", "* ", "+ ", "• ")):
                return True, 1

    return False, 0


def is_heading(text: str, max_length: int = MAX_HEADING_LENGTH) -> bool:
    return detect_heading(text, max_length=max_length)[0]


def infer_heading_level(text: str, max_length: int = MAX_HEADING_LENGTH) -> int:
    return detect_heading(text, max_length=max_length)[1]


def is_list_item(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False

    if _UNORDERED_LIST_PATTERN.match(stripped):
        return True

    if _ORDERED_LIST_PATTERN.match(stripped):
        return True

    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    if len(lines) > 1:
        list_count = sum(
            1
            for line in lines
            if _UNORDERED_LIST_PATTERN.match(line) or _ORDERED_LIST_PATTERN.match(line)
        )
        if list_count >= len(lines) / 2:
            return True

    return False


def classify_text(
    text: str, max_heading_length: int = MAX_HEADING_LENGTH
) -> tuple[BlockType, int]:
    stripped = text.strip()
    if not stripped:
        return BlockType.PARAGRAPH, 0

    if is_code_block(text):
        return BlockType.CODE_BLOCK, 0

    heading_detected, level = detect_heading(text, max_length=max_heading_length)
    if heading_detected:
        return BlockType.HEADING, level

    if is_list_item(text):
        return BlockType.LIST_ITEM, 0

    return BlockType.PARAGRAPH, 0


def classify_block(
    block: TextBlock, max_heading_length: int = MAX_HEADING_LENGTH
) -> TextBlock:
    text = block.normalized_text if block.normalized_text else block.raw_text
    block_type, heading_level = classify_text(
        text, max_heading_length=max_heading_length
    )
    return replace(block, block_type=block_type, heading_level=heading_level)


def classify_blocks(
    blocks: Sequence[TextBlock], max_heading_length: int = MAX_HEADING_LENGTH
) -> list[TextBlock]:
    return [
        classify_block(block, max_heading_length=max_heading_length)
        for block in blocks
    ]


def classify_document_structure(
    doc: DocumentStructure, max_heading_length: int = MAX_HEADING_LENGTH
) -> DocumentStructure:
    classified_blocks = classify_blocks(
        doc.blocks, max_heading_length=max_heading_length
    )
    return DocumentStructure(
        source_path=doc.source_path,
        total_pages=doc.total_pages,
        strategy=doc.strategy,
        blocks=classified_blocks,
    )


class BlockClassifier:
    def __init__(self, max_heading_length: int = MAX_HEADING_LENGTH) -> None:
        self.max_heading_length = max_heading_length

    def classify(self, block: TextBlock) -> TextBlock:
        return classify_block(block, max_heading_length=self.max_heading_length)

    def classify_all(self, blocks: Sequence[TextBlock]) -> list[TextBlock]:
        return classify_blocks(blocks, max_heading_length=self.max_heading_length)

    def classify_document(self, doc: DocumentStructure) -> DocumentStructure:
        return classify_document_structure(
            doc, max_heading_length=self.max_heading_length
        )
