from collections.abc import Sequence
import re
import textwrap

from pdf_to_markdown_converter.domain.models import (
    BlockType,
    DocumentStructure,
    TextBlock,
)

_UNORDERED_BULLET_PATTERN: re.Pattern[str] = re.compile(
    r"^(\s*)([-*+•◦▪▫–—])\s+(.+)$",
    re.DOTALL,
)

_ORDERED_BULLET_PATTERN: re.Pattern[str] = re.compile(
    r"^(\s*)(\d+)[\.\)]\s+(.+)$",
    re.DOTALL,
)

_ORDERED_PAREN_PATTERN: re.Pattern[str] = re.compile(
    r"^(\s*)\((\d+)\)\s+(.+)$",
    re.DOTALL,
)

_ALPHA_ORDERED_PATTERN: re.Pattern[str] = re.compile(
    r"^(\s*)([a-zA-Z]|[ivxlcdmIVXLCDM]+)[\.\)]\s+(.+)$",
    re.DOTALL,
)

_HEADING_HASH_PATTERN: re.Pattern[str] = re.compile(r"^#{1,6}\s*")


def format_heading(text: str, heading_level: int = 1) -> str:
    content = text.strip()
    if not content:
        return ""

    level = max(1, min(6, heading_level if heading_level > 0 else 1))
    cleaned = _HEADING_HASH_PATTERN.sub("", content).strip()
    if not cleaned:
        return f"{'#' * level}"

    normalized = " ".join(line.strip() for line in cleaned.splitlines() if line.strip())
    return f"{'#' * level} {normalized}"


def is_code_fenced(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    lines = stripped.splitlines()
    if len(lines) < 2:
        return False
    first = lines[0].strip()
    last = lines[-1].strip()
    return (
        (first.startswith("```") and last == "```")
        or (first.startswith("~~~") and last == "~~~")
    )


def format_code_block(text: str, default_language: str = "") -> str:
    stripped = text.strip()
    if not stripped:
        return ""

    if is_code_fenced(stripped):
        return stripped

    dedented = textwrap.dedent(text).strip()
    lang = default_language.strip()
    if lang:
        return f"```{lang}\n{dedented}\n```"
    return f"```\n{dedented}\n```"


def format_list_item(text: str, preserve_ordered: bool = True) -> str:
    stripped = text.strip()
    if not stripped:
        return ""

    lines = text.splitlines()
    formatted_lines: list[str] = []

    for i, line in enumerate(lines):
        line_stripped = line.strip()
        if not line_stripped:
            continue

        m_un = _UNORDERED_BULLET_PATTERN.match(line)
        if m_un:
            indent = m_un.group(1)
            body = m_un.group(3).strip()
            formatted_lines.append(f"{indent}- {body}")
            continue

        m_ord = _ORDERED_BULLET_PATTERN.match(line)
        if m_ord:
            indent = m_ord.group(1)
            num = m_ord.group(2)
            body = m_ord.group(3).strip()
            if preserve_ordered:
                formatted_lines.append(f"{indent}{num}. {body}")
            else:
                formatted_lines.append(f"{indent}- {body}")
            continue

        m_paren = _ORDERED_PAREN_PATTERN.match(line)
        if m_paren:
            indent = m_paren.group(1)
            num = m_paren.group(2)
            body = m_paren.group(3).strip()
            if preserve_ordered:
                formatted_lines.append(f"{indent}{num}. {body}")
            else:
                formatted_lines.append(f"{indent}- {body}")
            continue

        m_alpha = _ALPHA_ORDERED_PATTERN.match(line)
        if m_alpha:
            indent = m_alpha.group(1)
            marker = m_alpha.group(2)
            body = m_alpha.group(3).strip()
            if preserve_ordered:
                formatted_lines.append(f"{indent}{marker}. {body}")
            else:
                formatted_lines.append(f"{indent}- {body}")
            continue

        if i == 0:
            indent_len = len(line) - len(line.lstrip())
            indent = line[:indent_len]
            formatted_lines.append(f"{indent}- {line_stripped}")
        else:
            indent_len = len(line) - len(line.lstrip())
            if indent_len >= 2:
                formatted_lines.append(line.rstrip())
            else:
                formatted_lines.append(f"  {line_stripped}")

    return "\n".join(formatted_lines)


def format_paragraph(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    return "\n".join(lines)


def format_block(
    block: TextBlock,
    preserve_ordered_lists: bool = True,
    default_code_language: str = "",
) -> str:
    text = block.normalized_text if block.normalized_text else block.raw_text
    if not text.strip():
        return ""

    if block.block_type == BlockType.HEADING:
        return format_heading(text, heading_level=block.heading_level)
    elif block.block_type == BlockType.CODE_BLOCK:
        return format_code_block(text, default_language=default_code_language)
    elif block.block_type == BlockType.LIST_ITEM:
        return format_list_item(text, preserve_ordered=preserve_ordered_lists)
    else:
        return format_paragraph(text)


def build_markdown(
    content: Sequence[TextBlock] | DocumentStructure,
    separator: str = "\n\n",
    preserve_ordered_lists: bool = True,
    default_code_language: str = "",
) -> str:
    if isinstance(content, DocumentStructure):
        blocks = content.blocks
    else:
        blocks = content

    if not blocks:
        return ""

    rendered: list[str] = []
    for block in blocks:
        formatted = format_block(
            block,
            preserve_ordered_lists=preserve_ordered_lists,
            default_code_language=default_code_language,
        )
        if formatted:
            rendered.append(formatted)

    return separator.join(rendered)


class MarkdownBuilder:
    def __init__(
        self,
        separator: str = "\n\n",
        preserve_ordered_lists: bool = True,
        default_code_language: str = "",
    ) -> None:
        self.separator = separator
        self.preserve_ordered_lists = preserve_ordered_lists
        self.default_code_language = default_code_language

    def format_block(self, block: TextBlock) -> str:
        return format_block(
            block,
            preserve_ordered_lists=self.preserve_ordered_lists,
            default_code_language=self.default_code_language,
        )

    def build_blocks(self, blocks: Sequence[TextBlock]) -> str:
        return build_markdown(
            blocks,
            separator=self.separator,
            preserve_ordered_lists=self.preserve_ordered_lists,
            default_code_language=self.default_code_language,
        )

    def build_document(self, doc: DocumentStructure) -> str:
        return build_markdown(
            doc,
            separator=self.separator,
            preserve_ordered_lists=self.preserve_ordered_lists,
            default_code_language=self.default_code_language,
        )

    def build(self, content: Sequence[TextBlock] | DocumentStructure) -> str:
        return build_markdown(
            content,
            separator=self.separator,
            preserve_ordered_lists=self.preserve_ordered_lists,
            default_code_language=self.default_code_language,
        )
