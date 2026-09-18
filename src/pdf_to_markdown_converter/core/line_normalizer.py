from collections.abc import Sequence
import re

_WORD_CHARS = r"[a-zA-Z0-9À-ÖØ-öø-ÿ]"
_HYPHEN_CHARS = frozenset(("-", "‐", "‑", "\u00ad"))

_HYPHEN_BREAK_RE = re.compile(
    rf"(?P<prefix>{_WORD_CHARS}+)[-‐‑\u00ad][^\S\r\n]*\r?\n[^\S\r\n]*(?P<repeat>-?)[^\S\r\n]*(?P<suffix>{_WORD_CHARS}+)"
)

_ALWAYS_HYPHENATED_PREFIXES: frozenset[str] = frozenset({
    "ex", "vice", "vizo", "soto",
    "pré", "pre", "pós", "pos", "pró", "pro",
    "recém", "recem", "além", "alem", "aquém", "aquem",
    "sem",
    "self", "all", "well", "cross", "half",
})

_VOWEL_PREFIXES: frozenset[str] = frozenset({
    "auto", "anti", "contra", "micro", "macro", "mini",
    "multi", "neo", "proto", "pseudo", "semi", "infra",
    "supra", "ultra", "extra", "intra",
})

_PORTUGUESE_ENCLITICS: frozenset[str] = frozenset({
    "me", "te", "se", "nos", "vos",
    "o", "a", "os", "as",
    "lhe", "lhes",
    "lo", "la", "los", "las",
    "no", "na", "nos", "nas",
    "mo", "ma", "mos", "mas",
    "to", "ta", "tos", "tas",
    "lho", "lha", "lhos", "lhas",
})

_KNOWN_COMPOUND_WORDS: frozenset[str] = frozenset({
    "guarda-chuva", "guarda-roupa", "guarda-noturno", "guarda-sol",
    "guarda-costas", "guarda-po", "guarda-pó", "guarda-florestal",
    "arco-iris", "arco-íris", "beija-flor", "couve-flor",
    "segunda-feira", "terca-feira", "terça-feira", "quarta-feira",
    "quinta-feira", "sexta-feira", "fim-de-semana", "fim-de-tarde",
    "bem-vindo", "bem-estar", "bem-sucedido", "bem-nascido", "bem-criado",
    "mal-estar", "mal-humorado", "mal-intencionado",
    "porta-malas", "porta-voz", "porta-bandeira", "porta-retrato",
    "porta-avioes", "porta-aviões", "porta-joias",
    "medico-cirurgiao", "médico-cirurgião", "historico-geografico",
    "histórico-geográfico", "politico-economico", "político-econômico",
    "fisico-quimico", "físico-químico", "social-democrata",
    "norte-americano", "sul-americano", "centro-americano",
    "afro-brasileiro", "luso-brasileiro", "bate-papo", "quebra-cabeca",
    "quebra-cabeça", "para-raios", "pára-raios", "pingue-pongue", "tique-taque",
    "state-of-the-art", "high-level", "low-level", "well-known",
    "real-time", "open-source", "built-in", "first-class",
    "end-to-end", "user-facing", "read-only", "set-up", "clean-up",
    "front-end", "back-end",
})


def normalize_line_endings(text: str) -> str:
    if not text:
        return ""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def is_morphological_hyphen(
    prefix: str,
    suffix: str,
    *,
    custom_compound_words: set[str] | Sequence[str] | None = None,
) -> bool:
    if not prefix or not suffix:
        return False

    if any(c.isdigit() for c in prefix) or any(c.isdigit() for c in suffix):
        return True

    if prefix[0].isupper() and suffix[0].isupper():
        return True

    clean_prefix = prefix.lower()
    clean_suffix = suffix.lower()
    candidate = f"{clean_prefix}-{clean_suffix}"

    if candidate in _KNOWN_COMPOUND_WORDS:
        return True

    if custom_compound_words is not None and candidate in custom_compound_words:
        return True

    if clean_suffix in _PORTUGUESE_ENCLITICS:
        return True

    if clean_prefix in _ALWAYS_HYPHENATED_PREFIXES:
        return True

    if clean_suffix.startswith("h") and clean_prefix in _VOWEL_PREFIXES:
        return True

    if clean_prefix in _VOWEL_PREFIXES and clean_suffix.startswith(clean_prefix[-1]):
        return True

    if clean_prefix == "sub" and clean_suffix[0] in ("b", "r", "h"):
        return True

    if clean_prefix in ("super", "hiper", "inter") and clean_suffix[0] in ("r", "h"):
        return True

    return False


def dehyphenate_text(
    text: str,
    *,
    custom_compound_words: set[str] | Sequence[str] | None = None,
) -> str:
    if not text:
        return ""

    custom_set: set[str] | None = None
    if custom_compound_words is not None:
        custom_set = {w.lower() for w in custom_compound_words}

    def _replace_match(match: re.Match[str]) -> str:
        prefix = match.group("prefix")
        repeat = match.group("repeat")
        suffix = match.group("suffix")

        start = match.start()
        end = match.end()

        is_preceded_by_hyphen = (
            start > 1
            and match.string[start - 1] in _HYPHEN_CHARS
            and match.string[start - 2] not in ("\r", "\n", " ", "\t")
        )
        is_followed_by_hyphen = (
            end < len(match.string) - 1
            and match.string[end] in _HYPHEN_CHARS
            and match.string[end + 1] not in ("\r", "\n", " ", "\t")
        )

        if repeat == "-" or is_preceded_by_hyphen or is_followed_by_hyphen:
            return f"{prefix}-{suffix}"

        if is_morphological_hyphen(prefix, suffix, custom_compound_words=custom_set):
            return f"{prefix}-{suffix}"

        return f"{prefix}{suffix}"

    current = normalize_line_endings(text)
    while True:
        updated = _HYPHEN_BREAK_RE.sub(_replace_match, current)
        if updated == current:
            break
        current = updated

    return current


def consolidate_paragraphs(
    text: str,
    *,
    preserve_double_newlines: bool = True,
    strip_lines: bool = True,
) -> str:
    if not text:
        return ""

    normalized = normalize_line_endings(text)
    raw_paragraphs = re.split(r"\n\s*\n+", normalized)

    processed_paragraphs: list[str] = []
    for para in raw_paragraphs:
        lines = para.split("\n")
        if strip_lines:
            cleaned = [line.strip() for line in lines if line.strip()]
        else:
            cleaned = [line for line in lines if line]

        if cleaned:
            processed_paragraphs.append(" ".join(cleaned))

    separator = "\n\n" if preserve_double_newlines else " "
    return separator.join(processed_paragraphs)


def normalize_line_breaks(
    text: str,
    *,
    dehyphenate: bool = True,
    unwrap_paragraphs: bool = True,
    preserve_double_newlines: bool = True,
    custom_compound_words: set[str] | Sequence[str] | None = None,
) -> str:
    if not text:
        return ""

    result = normalize_line_endings(text)

    if dehyphenate:
        result = dehyphenate_text(
            result,
            custom_compound_words=custom_compound_words,
        )

    if unwrap_paragraphs:
        result = consolidate_paragraphs(
            result,
            preserve_double_newlines=preserve_double_newlines,
        )

    return result
