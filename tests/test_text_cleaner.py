import unicodedata

from pdf_to_markdown_converter.core.text_cleaner import (
    clean_text,
    collapse_consecutive_spaces,
    normalize_spaces,
    normalize_unicode,
    remove_control_characters,
    remove_invisible_characters,
    remove_null_bytes,
    remove_replacement_characters,
)


def test_remove_null_bytes() -> None:
    assert remove_null_bytes("") == ""
    assert remove_null_bytes("texto limpo") == "texto limpo"
    assert remove_null_bytes("\x00inicio\x00meio\x00fim\x00") == "iniciomeiofim"
    assert remove_null_bytes("\x00\x00\x00") == ""


def test_remove_replacement_characters() -> None:
    assert remove_replacement_characters("") == ""
    assert remove_replacement_characters("texto sem substituicao") == "texto sem substituicao"
    assert remove_replacement_characters("erro \ufffd detectado \ufffc aqui") == "erro  detectado  aqui"
    assert remove_replacement_characters("\ufffd\ufffc") == ""


def test_remove_control_characters_default() -> None:
    assert remove_control_characters("") == ""
    assert remove_control_characters("texto limpo") == "texto limpo"

    c0_sample = "linha 1\x01\x02\x07\x08\x0b\x0c\x0e\x1f\x7f final"
    assert remove_control_characters(c0_sample) == "linha 1 final"

    c1_sample = "antes\x80\x85\x9fdepois"
    assert remove_control_characters(c1_sample) == "antesdepois"

    mixed_preserved = "linha 1\nlinha 2\r\tcoluna com tabs\x00\x03"
    assert remove_control_characters(mixed_preserved) == "linha 1\nlinha 2\r\tcoluna com tabs"


def test_remove_control_characters_flags() -> None:
    text = "linha 1\nlinha 2\r\tcoluna"
    assert remove_control_characters(text, keep_newlines=False, keep_tabs=True) == "linha 1linha 2\tcoluna"
    assert remove_control_characters(text, keep_newlines=True, keep_tabs=False) == "linha 1\nlinha 2\rcoluna"
    assert remove_control_characters(text, keep_newlines=False, keep_tabs=False) == "linha 1linha 2coluna"


def test_remove_invisible_characters() -> None:
    assert remove_invisible_characters("") == ""
    assert remove_invisible_characters("texto normal") == "texto normal"

    invisibles = (
        "zero\u200bwidth"
        "\ufeffbom"
        "joiner\u200dtest"
        "non\u200cjoiner"
        "dir\u200emark"
        "rtl\u200fmark"
        "word\u2060joiner"
    )
    assert remove_invisible_characters(invisibles) == "zerowidthbomjoinertestnonjoinerdirmarkrtlmarkwordjoiner"


def test_remove_invisible_characters_soft_hyphen() -> None:
    text_with_shy = "desen\u00advolvimento"
    assert remove_invisible_characters(text_with_shy, remove_soft_hyphens=True) == "desenvolvimento"
    assert remove_invisible_characters(text_with_shy, remove_soft_hyphens=False) == "desen\u00advolvimento"


def test_normalize_spaces() -> None:
    assert normalize_spaces("") == ""
    assert normalize_spaces("espaco comum") == "espaco comum"

    exotic = "palavra\u00a0com\u202fespacos\u2002en\u2003em\u3000ideografico"
    assert normalize_spaces(exotic) == "palavra com espacos en em ideografico"


def test_collapse_consecutive_spaces() -> None:
    assert collapse_consecutive_spaces("") == ""
    assert collapse_consecutive_spaces("texto   com     muitos   espacos") == "texto com muitos espacos"
    assert collapse_consecutive_spaces("linha 1   aqui\nlinha 2     ali\n\nlinha 3") == "linha 1 aqui\nlinha 2 ali\n\nlinha 3"
    assert collapse_consecutive_spaces("sem_espacos_extras") == "sem_espacos_extras"


def test_normalize_unicode() -> None:
    assert normalize_unicode("") == ""

    decomposed = "c\u0327a\u0303o"
    assert len(decomposed) == 5
    composed = normalize_unicode(decomposed, form="NFC")
    assert composed == "ção"
    assert len(composed) == 3


def test_clean_text_full_pipeline() -> None:
    corrupted = (
        "\x00Relat\u00f3rio\x01 de \ufffdInova\u00e7\u00e3o\u200b\n"
        "Se\u00e7\u00e3o\u00a01:\u202fTecnologia\ufeff\x7f\r\n"
        "Desen\u00advolvimento e c\u0327a\u0303o."
    )
    expected = (
        "Relatório de Inovação\n"
        "Seção 1: Tecnologia\r\n"
        "Desenvolvimento e ção."
    )
    cleaned = clean_text(corrupted)
    assert cleaned == expected
    assert unicodedata.is_normalized("NFC", cleaned)


def test_clean_text_collapse_spaces_option() -> None:
    text = "Palavra1    Palavra2     Palavra3\nLinha   2"
    without_collapse = clean_text(text, collapse_spaces=False)
    assert without_collapse == text

    with_collapse = clean_text(text, collapse_spaces=True)
    assert with_collapse == "Palavra1 Palavra2 Palavra3\nLinha 2"


def test_clean_text_preserves_portuguese_characters() -> None:
    pt_lower = "á à â ã é ê í ó ô õ ú ü ç"
    pt_upper = "Á À Â Ã É Ê Í Ó Ô Õ Ú Ü Ç"

    assert clean_text(pt_lower) == pt_lower
    assert clean_text(pt_upper) == pt_upper

    decomposed_pt = unicodedata.normalize("NFD", "Ação, coração, café, saúde, vovô, órgão e água.")
    assert clean_text(decomposed_pt) == "Ação, coração, café, saúde, vovô, órgão e água."


def test_clean_text_preserves_punctuation_and_symbols() -> None:
    punctuation = "«Citação em português», com traço—em e en–dash: “aspas” e ‘simples’. Art. 5º, § 1ª. R$ 1.500,00 (10%)."
    assert clean_text(punctuation) == punctuation


def test_clean_text_idempotence() -> None:
    dirty = "\x00\ufffdTexto\u200b com\u00a0acentua\u00e7\u00e3o e \x02controle\nSegunda linha\r"
    first_pass = clean_text(dirty)
    second_pass = clean_text(first_pass)
    assert first_pass == second_pass


def test_clean_text_edge_cases() -> None:
    assert clean_text("") == ""
    assert clean_text("\x00\x00\x00") == ""
    assert clean_text("\ufffd\ufffc") == ""
    assert clean_text("\u200b\ufeff\u200d\u200c") == ""
    assert clean_text("\x01\x02\x03\x04\x05") == ""
    assert clean_text("   ") == "   "
    assert clean_text("   ", collapse_spaces=True) == " "
