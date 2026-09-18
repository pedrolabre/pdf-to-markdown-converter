import pytest

from pdf_to_markdown_converter.core.line_normalizer import (
    consolidate_paragraphs,
    dehyphenate_text,
    is_morphological_hyphen,
    normalize_line_breaks,
    normalize_line_endings,
)


def test_normalize_line_endings_empty_and_variations() -> None:
    assert normalize_line_endings("") == ""
    assert normalize_line_endings("linha 1\r\nlinha 2\rlinha 3\n") == "linha 1\nlinha 2\nlinha 3\n"
    assert normalize_line_endings("apenas uma linha") == "apenas uma linha"


def test_is_morphological_hyphen_empty() -> None:
    assert not is_morphological_hyphen("", "")
    assert not is_morphological_hyphen("palavra", "")
    assert not is_morphological_hyphen("", "palavra")


def test_is_morphological_hyphen_alphanumerics() -> None:
    assert is_morphological_hyphen("ISO", "9001")
    assert is_morphological_hyphen("UTF", "8")
    assert is_morphological_hyphen("model", "4b")
    assert is_morphological_hyphen("10", "minute")


def test_is_morphological_hyphen_proper_nouns() -> None:
    assert is_morphological_hyphen("Anglo", "Americano")
    assert is_morphological_hyphen("Porto", "Alegrense")
    assert not is_morphological_hyphen("Exem", "plo")
    assert not is_morphological_hyphen("Cons", "trucao")


def test_is_morphological_hyphen_known_compounds_and_custom() -> None:
    assert is_morphological_hyphen("guarda", "chuva")
    assert is_morphological_hyphen("segunda", "feira")
    assert is_morphological_hyphen("arco", "íris")
    assert is_morphological_hyphen("bem", "estar")
    assert is_morphological_hyphen("porta", "malas")
    assert is_morphological_hyphen("state", "of-the-art")
    assert not is_morphological_hyphen("palavra", "desconhecida")
    assert is_morphological_hyphen(
        "termo",
        "customizado",
        custom_compound_words={"termo-customizado"},
    )


def test_is_morphological_hyphen_portuguese_enclitics() -> None:
    assert is_morphological_hyphen("disse", "me")
    assert is_morphological_hyphen("amou", "o")
    assert is_morphological_hyphen("viu", "a")
    assert is_morphological_hyphen("entregou", "lhe")
    assert is_morphological_hyphen("tornar", "se")
    assert is_morphological_hyphen("fazê", "lo")
    assert is_morphological_hyphen("ajudar", "nos")
    assert is_morphological_hyphen("disseram", "lhes")
    assert not is_morphological_hyphen("exem", "plo")


def test_is_morphological_hyphen_universal_prefixes() -> None:
    assert is_morphological_hyphen("ex", "presidente")
    assert is_morphological_hyphen("vice", "diretor")
    assert is_morphological_hyphen("pré", "requisito")
    assert is_morphological_hyphen("pós", "graduação")
    assert is_morphological_hyphen("recém", "nascido")
    assert is_morphological_hyphen("sem", "teto")
    assert is_morphological_hyphen("self", "esteem")
    assert is_morphological_hyphen("well", "known")


def test_is_morphological_hyphen_orthographic_rules() -> None:
    assert is_morphological_hyphen("micro", "ondas")
    assert not is_morphological_hyphen("micro", "computador")
    assert is_morphological_hyphen("anti", "inflamatório")
    assert not is_morphological_hyphen("anti", "corpo")
    assert is_morphological_hyphen("auto", "observação")
    assert is_morphological_hyphen("auto", "hipnose")
    assert not is_morphological_hyphen("auto", "estima")
    assert is_morphological_hyphen("super", "homem")
    assert is_morphological_hyphen("super", "resistente")
    assert not is_morphological_hyphen("super", "mercado")
    assert is_morphological_hyphen("sub", "bloco")
    assert is_morphological_hyphen("sub", "região")
    assert not is_morphological_hyphen("sub", "marino")
    assert not is_morphological_hyphen("inter", "nacional")
    assert is_morphological_hyphen("inter", "racial")


def test_dehyphenate_text_margin_breaks() -> None:
    assert dehyphenate_text("exem-\nplo") == "exemplo"
    assert dehyphenate_text("desenvolvi- \n mento") == "desenvolvimento"
    assert dehyphenate_text("informa-\r\nção") == "informação"
    assert dehyphenate_text("ar- \n quivo") == "arquivo"
    assert dehyphenate_text("subs-\ntituição") == "substituição"


def test_dehyphenate_text_preserves_morphological_hyphens() -> None:
    assert dehyphenate_text("Ele comprou um guarda-\nchuva novo.") == "Ele comprou um guarda-chuva novo."
    assert dehyphenate_text("O ex-\npresidente discursou.") == "O ex-presidente discursou."
    assert dehyphenate_text("Ele disse-\nme tudo.") == "Ele disse-me tudo."
    assert dehyphenate_text("Micro-\nondas em promoção.") == "Micro-ondas em promoção."
    assert dehyphenate_text("Padrão ISO-\n9001 certificado.") == "Padrão ISO-9001 certificado."


def test_dehyphenate_text_typographic_repeat_hyphen() -> None:
    assert dehyphenate_text("guarda-\n-chuva") == "guarda-chuva"
    assert dehyphenate_text("porta-\n -bandeira") == "porta-bandeira"


def test_dehyphenate_text_multi_hyphen_expressions() -> None:
    assert dehyphenate_text("fim-de-\nsemana") == "fim-de-semana"
    assert dehyphenate_text("face-\nto-face") == "face-to-face"
    assert dehyphenate_text("state-of-\nthe-art") == "state-of-the-art"


def test_dehyphenate_text_intra_line_untouched() -> None:
    text = "guarda-chuva e arco-íris na mesma linha sem quebra"
    assert dehyphenate_text(text) == text


def test_dehyphenate_text_consecutive_margin_breaks() -> None:
    assert dehyphenate_text("pa-\nra-\nque-\ndas") == "paraquedas"


def test_consolidate_paragraphs_single_paragraph() -> None:
    text = "Linha 1 do parágrafo\nLinha 2 do parágrafo\nLinha 3 do parágrafo"
    expected = "Linha 1 do parágrafo Linha 2 do parágrafo Linha 3 do parágrafo"
    assert consolidate_paragraphs(text) == expected

    ragged = "  Linha 1  \n   Linha 2   \n  Linha 3  "
    assert consolidate_paragraphs(ragged) == "Linha 1 Linha 2 Linha 3"


def test_consolidate_paragraphs_multiple_paragraphs() -> None:
    text = "P1 Linha 1\nP1 Linha 2\n\nP2 Linha 1\nP2 Linha 2"
    expected = "P1 Linha 1 P1 Linha 2\n\nP2 Linha 1 P2 Linha 2"
    assert consolidate_paragraphs(text) == expected

    excessive_newlines = "P1 Linha 1\nP1 Linha 2\n\n\n\nP2 Linha 1\nP2 Linha 2"
    assert consolidate_paragraphs(excessive_newlines) == expected

    whitespace_blank_lines = "P1 Linha 1\n   \n\t  \nP2 Linha 1"
    assert consolidate_paragraphs(whitespace_blank_lines) == "P1 Linha 1\n\nP2 Linha 1"


def test_consolidate_paragraphs_without_preserve_double_newlines() -> None:
    text = "P1 Linha 1\n\nP2 Linha 1"
    assert consolidate_paragraphs(text, preserve_double_newlines=False) == "P1 Linha 1 P2 Linha 1"


def test_consolidate_paragraphs_empty_and_whitespace() -> None:
    assert consolidate_paragraphs("") == ""
    assert consolidate_paragraphs("   \n\n   \t  \n  ") == ""


def test_normalize_line_breaks_pipeline() -> None:
    raw = (
        "O desen-\n"
        "volvimento deste sis-\n"
        "tema segue arqui-\n"
        "tetura limpa.\n"
        "\n"
        "É necessário usar guarda-\n"
        "chuva e seguir o ISO-\n"
        "9001 com disci-\n"
        "plina."
    )
    expected = (
        "O desenvolvimento deste sistema segue arquitetura limpa.\n\n"
        "É necessário usar guarda-chuva e seguir o ISO-9001 com disciplina."
    )
    assert normalize_line_breaks(raw) == expected


def test_normalize_line_breaks_options() -> None:
    text = "exem-\nplo de texto\ncontinua aqui"
    without_unwrap = normalize_line_breaks(text, unwrap_paragraphs=False)
    assert without_unwrap == "exemplo de texto\ncontinua aqui"

    without_dehyphen = normalize_line_breaks(text, dehyphenate=False)
    assert without_dehyphen == "exem- plo de texto continua aqui"


def test_normalize_line_breaks_idempotence_and_edge_cases() -> None:
    assert normalize_line_breaks("") == ""
    text = "Um parágrafo já devidamente normalizado.\n\nOutro parágrafo."
    assert normalize_line_breaks(text) == text
    assert normalize_line_breaks(normalize_line_breaks(text)) == normalize_line_breaks(text)
