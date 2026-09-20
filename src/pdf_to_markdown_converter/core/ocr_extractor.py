from collections.abc import Sequence
import io
from pathlib import Path
from typing import Any

from PIL import Image
import pymupdf
import pytesseract

from pdf_to_markdown_converter.core.line_normalizer import normalize_line_breaks
from pdf_to_markdown_converter.core.native_extractor import sort_blocks_spatially
from pdf_to_markdown_converter.core.pdf_reader import open_pdf
from pdf_to_markdown_converter.core.tesseract_env import (
    configure_pytesseract,
    ensure_tesseract_available,
)
from pdf_to_markdown_converter.core.text_cleaner import clean_text
from pdf_to_markdown_converter.domain.models import (
    BlockType,
    DocumentStructure,
    ExtractionStrategy,
    TextBlock,
)

DEFAULT_DPI: int = 300
DEFAULT_LANG: str = "por+eng"
DEFAULT_PSM: int = 3
DEFAULT_OEM: int = 3
DEFAULT_IMAGE_FORMAT: str = "png"


def build_tesseract_config(
    psm: int | None = DEFAULT_PSM, oem: int | None = DEFAULT_OEM, extra_config: str = ""
) -> str:
    parts = [f"--psm {psm}"] if psm is not None else []
    if oem is not None:
        parts.append(f"--oem {oem}")
    if extra_config.strip():
        parts.append(extra_config.strip())
    return " ".join(parts)


def render_page_to_bytes(
    page: pymupdf.Page, dpi: int = DEFAULT_DPI, image_format: str = DEFAULT_IMAGE_FORMAT
) -> bytes:
    scale = max(dpi, 1) / 72.0
    return page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).tobytes(image_format)


def render_page_to_image(page: pymupdf.Page, dpi: int = DEFAULT_DPI) -> Image.Image:
    image = Image.open(io.BytesIO(render_page_to_bytes(page, dpi=dpi)))
    image.load()
    return image


def parse_ocr_data_to_blocks(
    data: dict[str, list[Any]],
    page_number: int,
    scale: float = 1.0,
    normalize: bool = True,
    ignore_empty: bool = True,
) -> list[TextBlock]:
    texts = data.get("text", [])
    if not texts:
        return []

    block_nums, par_nums = data.get("block_num", []), data.get("par_num", [])
    line_nums = data.get("line_num", [])
    lefts, tops = data.get("left", []), data.get("top", [])
    widths, heights = data.get("width", []), data.get("height", [])
    confs = data.get("conf", [])

    groups: dict[tuple[int, int], list[tuple[int, str, int, int, int, int]]] = {}
    for i, raw_token in enumerate(texts):
        word = str(raw_token).strip()
        if not word or (confs[i] if i < len(confs) else 0) == -1:
            continue

        b_num = block_nums[i] if i < len(block_nums) else 0
        p_num = par_nums[i] if i < len(par_nums) else 0
        l_num = line_nums[i] if i < len(line_nums) else 0
        left, top = (lefts[i] if i < len(lefts) else 0), (tops[i] if i < len(tops) else 0)
        w, h = (widths[i] if i < len(widths) else 0), (heights[i] if i < len(heights) else 0)

        groups.setdefault((b_num, p_num), []).append((l_num, word, left, top, w, h))

    blocks: list[TextBlock] = []
    eff_scale = scale if scale > 0 else 1.0

    for _key, words_info in groups.items():
        lines_dict: dict[int, list[str]] = {}
        min_x, min_y = float("inf"), float("inf")
        max_x, max_y = float("-inf"), float("-inf")

        for l_num, word, l, t, w, h in words_info:
            lines_dict.setdefault(l_num, []).append(word)
            min_x, min_y = min(min_x, l), min(min_y, t)
            max_x, max_y = max(max_x, l + w), max(max_y, t + h)

        if not lines_dict:
            continue

        raw_text = "\n".join(" ".join(lines_dict[l]) for l in sorted(lines_dict)).strip()
        if ignore_empty and not raw_text:
            continue

        norm_text = (
            normalize_line_breaks(clean_text(raw_text)).strip()
            if normalize
            else raw_text
        )
        bbox = (
            round(min_x / eff_scale, 2),
            round(min_y / eff_scale, 2),
            round(max_x / eff_scale, 2),
            round(max_y / eff_scale, 2),
        )
        blocks.append(
            TextBlock(
                page_number=page_number,
                block_type=BlockType.PARAGRAPH,
                raw_text=raw_text,
                normalized_text=norm_text,
                bbox=bbox,
                heading_level=0,
            )
        )

    return blocks


def parse_ocr_text_to_blocks(
    text: str,
    page_number: int,
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0),
    normalize: bool = True,
    ignore_empty: bool = True,
) -> list[TextBlock]:
    blocks: list[TextBlock] = []
    for chunk in text.split("\n\n"):
        raw_str = chunk.strip()
        if ignore_empty and not raw_str:
            continue
        norm_str = (
            normalize_line_breaks(clean_text(raw_str)).strip()
            if normalize
            else raw_str
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
    return blocks


def extract_page_blocks_ocr(
    page: pymupdf.Page,
    page_number: int | None = None,
    *,
    dpi: int = DEFAULT_DPI,
    lang: str = DEFAULT_LANG,
    psm: int = DEFAULT_PSM,
    oem: int = DEFAULT_OEM,
    extra_config: str = "",
    tesseract_cmd: Path | str | None = None,
    sort_spatial: bool = True,
    normalize: bool = True,
    ignore_empty: bool = True,
    use_data: bool = True,
    check_environment: bool = True,
) -> list[TextBlock]:
    if check_environment:
        langs = [l.strip() for l in lang.split("+") if l.strip()]
        ensure_tesseract_available(custom_cmd=tesseract_cmd, required_languages=langs)
    elif tesseract_cmd:
        configure_pytesseract(tesseract_cmd)

    target_page_num = page.number + 1 if page_number is None else page_number
    image = render_page_to_image(page, dpi=dpi)
    config = build_tesseract_config(psm=psm, oem=oem, extra_config=extra_config)
    scale = max(dpi, 1) / 72.0

    if use_data:
        data = pytesseract.image_to_data(
            image, lang=lang, config=config, output_type=pytesseract.Output.DICT
        )
        blocks = parse_ocr_data_to_blocks(
            data,
            page_number=target_page_num,
            scale=scale,
            normalize=normalize,
            ignore_empty=ignore_empty,
        )
    else:
        text = pytesseract.image_to_string(image, lang=lang, config=config)
        rect = page.rect
        page_bbox = (round(rect.x0, 2), round(rect.y0, 2), round(rect.x1, 2), round(rect.y1, 2))
        blocks = parse_ocr_text_to_blocks(
            text,
            page_number=target_page_num,
            bbox=page_bbox,
            normalize=normalize,
            ignore_empty=ignore_empty,
        )

    if sort_spatial and len(blocks) > 1:
        blocks = sort_blocks_spatially(blocks)

    return blocks


def extract_page_text_ocr(
    page: pymupdf.Page,
    *,
    dpi: int = DEFAULT_DPI,
    lang: str = DEFAULT_LANG,
    psm: int = DEFAULT_PSM,
    oem: int = DEFAULT_OEM,
    extra_config: str = "",
    tesseract_cmd: Path | str | None = None,
    check_environment: bool = True,
) -> str:
    if check_environment:
        langs = [l.strip() for l in lang.split("+") if l.strip()]
        ensure_tesseract_available(custom_cmd=tesseract_cmd, required_languages=langs)
    elif tesseract_cmd:
        configure_pytesseract(tesseract_cmd)

    image = render_page_to_image(page, dpi=dpi)
    config = build_tesseract_config(psm=psm, oem=oem, extra_config=extra_config)
    return pytesseract.image_to_string(image, lang=lang, config=config)


def _extract_from_open_doc_ocr(
    doc: pymupdf.Document, source_path: str, **kwargs: Any
) -> DocumentStructure:
    blocks: list[TextBlock] = []
    for i in range(len(doc)):
        blocks.extend(extract_page_blocks_ocr(doc[i], page_number=i + 1, **kwargs))
    return DocumentStructure(source_path, len(doc), ExtractionStrategy.OCR_FALLBACK, blocks)


def extract_document_structure_ocr(
    source: pymupdf.Document | str | Path | bytes,
    *,
    password: str = "",
    **kwargs: Any,
) -> DocumentStructure:
    if isinstance(source, pymupdf.Document):
        return _extract_from_open_doc_ocr(source, source.name or "<memory>", **kwargs)

    resolved_path = str(source) if isinstance(source, (str, Path)) else "<memory>"
    with open_pdf(source, password=password) as doc:
        return _extract_from_open_doc_ocr(doc, resolved_path, **kwargs)


class OcrExtractor:
    def __init__(self, **kwargs: Any) -> None:
        self.options: dict[str, Any] = {
            "dpi": DEFAULT_DPI, "lang": DEFAULT_LANG, "psm": DEFAULT_PSM,
            "oem": DEFAULT_OEM, "extra_config": "", "tesseract_cmd": None,
            "sort_spatial": True, "normalize": True, "ignore_empty": True,
            "use_data": True, "check_environment": True,
        }
        self.options.update(kwargs)

    @property
    def dpi(self) -> int:
        return int(self.options["dpi"])

    @property
    def lang(self) -> str:
        return str(self.options["lang"])

    def render_page(self, page: pymupdf.Page) -> bytes:
        return render_page_to_bytes(page, dpi=self.dpi)

    def extract_page(
        self, page: pymupdf.Page, page_number: int | None = None
    ) -> list[TextBlock]:
        return extract_page_blocks_ocr(page, page_number=page_number, **self.options)

    def extract_page_text(self, page: pymupdf.Page) -> str:
        keys = ("dpi", "lang", "psm", "oem", "extra_config", "tesseract_cmd", "check_environment")
        return extract_page_text_ocr(page, **{k: self.options[k] for k in keys if k in self.options})

    def extract(
        self, source: pymupdf.Document | str | Path | bytes, password: str = ""
    ) -> DocumentStructure:
        return extract_document_structure_ocr(source, password=password, **self.options)
