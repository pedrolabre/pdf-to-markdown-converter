from dataclasses import dataclass
from pathlib import Path
import unicodedata

import pymupdf

from pdf_to_markdown_converter.core.pdf_reader import open_pdf
from pdf_to_markdown_converter.domain.models import ExtractionStrategy

CORRUPTED_CHARS: frozenset[str] = frozenset({"\x00", "\ufffd", "\ufffc"})
MIN_READABLE_CHARS: int = 30
MAX_CORRUPTION_RATIO: float = 0.15
MIN_READABLE_RATIO: float = 0.80
DEFAULT_MAX_SAMPLE_PAGES: int = 5


@dataclass(frozen=True)
class TextQualityReport:
    total_chars: int
    printable_chars: int
    corrupted_chars: int
    readable_ratio: float
    corruption_ratio: float
    has_images: bool
    pages_sampled: tuple[int, ...]
    recommended_strategy: ExtractionStrategy
    reason: str

    def __post_init__(self) -> None:
        if isinstance(self.pages_sampled, list):
            object.__setattr__(self, "pages_sampled", tuple(self.pages_sampled))
        if self.total_chars < 0:
            raise ValueError("total_chars cannot be negative")
        if self.printable_chars < 0:
            raise ValueError("printable_chars cannot be negative")
        if self.corrupted_chars < 0:
            raise ValueError("corrupted_chars cannot be negative")


def is_corrupted_char(char: str) -> bool:
    if char in CORRUPTED_CHARS:
        return True
    category = unicodedata.category(char)
    if category == "Cc" and char not in ("\n", "\r", "\t"):
        return True
    return False


def is_readable_char(char: str) -> bool:
    if char in ("\n", "\r", "\t"):
        return True
    if is_corrupted_char(char):
        return False
    return char.isprintable()


def select_sample_pages(total_pages: int, max_pages: int = DEFAULT_MAX_SAMPLE_PAGES) -> list[int]:
    if total_pages <= 0 or max_pages <= 0:
        return []
    if total_pages <= max_pages:
        return list(range(total_pages))
    if max_pages == 1:
        return [0]
    if max_pages == 2:
        return [0, total_pages - 1]
    if max_pages == 3:
        return [0, total_pages // 2, total_pages - 1]
    if max_pages == 4:
        return [0, 1, total_pages // 2, total_pages - 1]

    indices = {0, 1, total_pages // 2, total_pages - 2, total_pages - 1}
    valid_indices = sorted(idx for idx in indices if 0 <= idx < total_pages)
    return valid_indices[:max_pages]


def _inspect_document(
    doc: pymupdf.Document,
    force_ocr: bool = False,
    max_sample_pages: int = DEFAULT_MAX_SAMPLE_PAGES,
) -> TextQualityReport:
    total_pages = doc.page_count
    sampled_indices = select_sample_pages(total_pages, max_pages=max_sample_pages)

    total_chars = 0
    printable_chars = 0
    corrupted_chars = 0
    non_space_readable = 0
    has_images = False

    for page_idx in sampled_indices:
        page = doc.load_page(page_idx)
        if not has_images and len(page.get_images()) > 0:
            has_images = True

        text = page.get_text()
        total_chars += len(text)
        for char in text:
            if is_corrupted_char(char):
                corrupted_chars += 1
            elif is_readable_char(char):
                printable_chars += 1
                if not char.isspace():
                    non_space_readable += 1

    readable_ratio = round(printable_chars / total_chars, 4) if total_chars > 0 else 0.0
    corruption_ratio = round(corrupted_chars / total_chars, 4) if total_chars > 0 else 0.0

    if force_ocr:
        return TextQualityReport(
            total_chars=total_chars,
            printable_chars=printable_chars,
            corrupted_chars=corrupted_chars,
            readable_ratio=readable_ratio,
            corruption_ratio=corruption_ratio,
            has_images=has_images,
            pages_sampled=tuple(sampled_indices),
            recommended_strategy=ExtractionStrategy.OCR_FALLBACK,
            reason="Extração OCR forçada manualmente via parâmetro force_ocr.",
        )

    if corruption_ratio > MAX_CORRUPTION_RATIO:
        reason = (
            f"Taxa de corrupção textual ({corruption_ratio:.1%}) excede o "
            f"limiar máximo permitido ({MAX_CORRUPTION_RATIO:.1%})."
        )
        strategy = ExtractionStrategy.OCR_FALLBACK
    elif non_space_readable < MIN_READABLE_CHARS:
        if total_chars == 0:
            reason = "Nenhum caractere textual detectado nas páginas amostradas."
        else:
            reason = (
                f"Densidade textual insuficiente ({non_space_readable} caracteres legíveis, "
                f"mínimo {MIN_READABLE_CHARS})."
            )
        strategy = ExtractionStrategy.OCR_FALLBACK
    elif readable_ratio < MIN_READABLE_RATIO:
        reason = (
            f"Taxa de caracteres legíveis ({readable_ratio:.1%}) está abaixo do "
            f"limiar mínimo ({MIN_READABLE_RATIO:.1%})."
        )
        strategy = ExtractionStrategy.OCR_FALLBACK
    else:
        reason = (
            f"Camada textual íntegra detectada ({printable_chars} caracteres legíveis, "
            f"legibilidade de {readable_ratio:.1%})."
        )
        strategy = ExtractionStrategy.NATIVE_TEXT

    return TextQualityReport(
        total_chars=total_chars,
        printable_chars=printable_chars,
        corrupted_chars=corrupted_chars,
        readable_ratio=readable_ratio,
        corruption_ratio=corruption_ratio,
        has_images=has_images,
        pages_sampled=tuple(sampled_indices),
        recommended_strategy=strategy,
        reason=reason,
    )


def analyze_text_quality(
    source: pymupdf.Document | str | Path | bytes,
    force_ocr: bool = False,
    password: str = "",
    max_sample_pages: int = DEFAULT_MAX_SAMPLE_PAGES,
) -> TextQualityReport:
    if isinstance(source, pymupdf.Document):
        return _inspect_document(source, force_ocr=force_ocr, max_sample_pages=max_sample_pages)

    with open_pdf(source, password=password) as doc:
        return _inspect_document(doc, force_ocr=force_ocr, max_sample_pages=max_sample_pages)


def detect_extraction_strategy(
    source: pymupdf.Document | str | Path | bytes,
    force_ocr: bool = False,
    password: str = "",
    max_sample_pages: int = DEFAULT_MAX_SAMPLE_PAGES,
) -> ExtractionStrategy:
    if force_ocr:
        return ExtractionStrategy.OCR_FALLBACK
    report = analyze_text_quality(
        source,
        force_ocr=False,
        password=password,
        max_sample_pages=max_sample_pages,
    )
    return report.recommended_strategy
