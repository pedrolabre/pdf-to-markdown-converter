import re
import unicodedata

_REPLACEMENT_CHARS = frozenset(("\ufffd", "\ufffc"))
_HORIZONTAL_SPACES_RE = re.compile(r"[^\S\r\n]{2,}")


def remove_null_bytes(text: str) -> str:
    if not text:
        return ""
    return text.replace("\x00", "")


def remove_replacement_characters(text: str) -> str:
    if not text:
        return ""
    return "".join(ch for ch in text if ch not in _REPLACEMENT_CHARS)


def remove_control_characters(
    text: str,
    *,
    keep_newlines: bool = True,
    keep_tabs: bool = True,
) -> str:
    if not text:
        return ""

    preserved: set[str] = set()
    if keep_newlines:
        preserved.update(("\n", "\r"))
    if keep_tabs:
        preserved.add("\t")

    return "".join(
        ch
        for ch in text
        if ch in preserved or unicodedata.category(ch) != "Cc"
    )


def remove_invisible_characters(
    text: str,
    *,
    remove_soft_hyphens: bool = True,
) -> str:
    if not text:
        return ""

    if remove_soft_hyphens:
        return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")

    return "".join(
        ch
        for ch in text
        if unicodedata.category(ch) != "Cf" or ch == "\u00ad"
    )


def normalize_spaces(text: str) -> str:
    if not text:
        return ""

    return "".join(
        " " if unicodedata.category(ch) == "Zs" and ch != " " else ch
        for ch in text
    )


def collapse_consecutive_spaces(text: str) -> str:
    if not text:
        return ""

    return _HORIZONTAL_SPACES_RE.sub(" ", text)


def normalize_unicode(text: str, form: str = "NFC") -> str:
    if not text:
        return ""

    return unicodedata.normalize(form, text)


def clean_text(
    text: str,
    *,
    unicode_form: str = "NFC",
    remove_nulls: bool = True,
    remove_replacements: bool = True,
    remove_controls: bool = True,
    remove_invisible: bool = True,
    normalize_space_chars: bool = True,
    collapse_spaces: bool = False,
    keep_newlines: bool = True,
    keep_tabs: bool = True,
    remove_soft_hyphens: bool = True,
) -> str:
    if not text:
        return ""

    result = text

    if remove_nulls:
        result = remove_null_bytes(result)

    if remove_replacements:
        result = remove_replacement_characters(result)

    if remove_controls:
        result = remove_control_characters(
            result,
            keep_newlines=keep_newlines,
            keep_tabs=keep_tabs,
        )

    if remove_invisible:
        result = remove_invisible_characters(
            result,
            remove_soft_hyphens=remove_soft_hyphens,
        )

    if normalize_space_chars:
        result = normalize_spaces(result)

    if collapse_spaces:
        result = collapse_consecutive_spaces(result)

    if unicode_form:
        result = normalize_unicode(result, form=unicode_form)

    return result
