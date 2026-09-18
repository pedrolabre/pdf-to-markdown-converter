from dataclasses import dataclass, field
from enum import Enum


class ExtractionStrategy(str, Enum):
    NATIVE_TEXT = "native_text"
    OCR_FALLBACK = "ocr_fallback"


class BlockType(str, Enum):
    PARAGRAPH = "paragraph"
    HEADING = "heading"
    CODE_BLOCK = "code_block"
    LIST_ITEM = "list_item"


@dataclass(frozen=True)
class TextBlock:
    page_number: int
    block_type: BlockType = BlockType.PARAGRAPH
    raw_text: str = ""
    normalized_text: str = ""
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    heading_level: int = 0

    def __post_init__(self) -> None:
        if self.page_number < 1:
            raise ValueError("page_number must be greater than or equal to 1")
        if not (0 <= self.heading_level <= 6):
            raise ValueError("heading_level must be between 0 and 6")
        if len(self.bbox) != 4:
            raise ValueError("bbox must contain exactly 4 coordinates (x0, y0, x1, y1)")


@dataclass
class DocumentStructure:
    source_path: str
    total_pages: int
    strategy: ExtractionStrategy
    blocks: list[TextBlock] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.total_pages < 0:
            raise ValueError("total_pages cannot be negative")

    def to_markdown(self) -> str:
        if not self.blocks:
            return ""

        rendered_blocks: list[str] = []
        for block in self.blocks:
            text = block.normalized_text if block.normalized_text else block.raw_text
            content = text.strip()
            if not content:
                continue

            if block.block_type == BlockType.HEADING and block.heading_level > 0:
                if content.startswith("#"):
                    rendered_blocks.append(content)
                else:
                    rendered_blocks.append(f"{'#' * block.heading_level} {content}")
            elif block.block_type == BlockType.CODE_BLOCK:
                if content.startswith("```") and content.endswith("```"):
                    rendered_blocks.append(content)
                else:
                    rendered_blocks.append(f"```\n{content}\n```")
            elif block.block_type == BlockType.LIST_ITEM:
                if content.startswith(("- ", "* ", "+ ")) or (
                    len(content) > 3
                    and content[0].isdigit()
                    and content[1:3] in (". ", ") ")
                ):
                    rendered_blocks.append(content)
                else:
                    rendered_blocks.append(f"- {content}")
            else:
                rendered_blocks.append(content)

        return "\n\n".join(rendered_blocks)


@dataclass(frozen=True)
class ExtractionResult:
    source_path: str
    markdown_path: str
    html_path: str
    strategy_used: ExtractionStrategy
    pages_processed: int
    execution_time_seconds: float

    def __post_init__(self) -> None:
        if self.pages_processed < 0:
            raise ValueError("pages_processed cannot be negative")
        if self.execution_time_seconds < 0.0:
            raise ValueError("execution_time_seconds cannot be negative")
