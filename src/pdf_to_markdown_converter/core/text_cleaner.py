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

    if not (remove_nulls or remove_replacements or remove_controls or remove_invisible or normalize_space_chars):
        result = text
    else:
        out: list[str] = []
        for ch in text:
            if remove_nulls and ch == "\x00":
                continue

            if remove_replacements and ch in _REPLACEMENT_CHARS:
                continue

            if ch == "\n" or ch == "\r":
                if remove_controls and not keep_newlines:
                    continue
                out.append(ch)
                continue

            if ch == "\t":
                if remove_controls and not keep_tabs:
                    continue
                out.append(ch)
                continue

            if ch == " ":
                out.append(" ")
                continue

            code = ord(ch)
            if 33 <= code <= 126:
                out.append(ch)
                continue

            if code < 32:
                if remove_controls:
                    continue
                out.append(ch)
                continue

            cat = unicodedata.category(ch)
            if remove_controls and cat == "Cc":
                continue

            if remove_invisible and cat == "Cf":
                if not remove_soft_hyphens and ch == "\u00ad":
                    out.append(ch)
                continue

            if normalize_space_chars and cat == "Zs":
                out.append(" ")
                continue

            out.append(ch)

        result = "".join(out)

    if collapse_spaces:
        result = collapse_consecutive_spaces(result)

    if unicode_form:
        result = normalize_unicode(result, form=unicode_form)

    return result
