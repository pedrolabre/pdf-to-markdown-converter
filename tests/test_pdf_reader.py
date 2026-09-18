from pathlib import Path

import pymupdf
import pytest

from pdf_to_markdown_converter.core.pdf_reader import (
    CorruptedPdfError,
    EmptyPdfError,
    EncryptedPdfError,
    PdfNotFoundError,
    PdfReader,
    inspect_pdf,
    is_pdf_valid,
    open_pdf,
    validate_pdf,
)


def _create_sample_pdf_bytes(
    text: str = "Hello World",
    title: str = "",
    author: str = "",
    user_pw: str = "",
    owner_pw: str = "",
    permissions: int | None = None,
) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), text)
    if title or author:
        doc.set_metadata({"title": title, "author": author})

    save_kwargs = {}
    if user_pw or owner_pw or permissions is not None:
        save_kwargs["encryption"] = pymupdf.PDF_ENCRYPT_AES_256
        save_kwargs["user_pw"] = user_pw
        save_kwargs["owner_pw"] = owner_pw or "owner_default"
        if permissions is not None:
            save_kwargs["permissions"] = permissions

    pdf_bytes = doc.tobytes(**save_kwargs)
    doc.close()
    return pdf_bytes


def test_open_pdf_from_path(tmp_path: Path):
    pdf_bytes = _create_sample_pdf_bytes("Conteúdo de Teste")
    file_path = tmp_path / "documento.pdf"
    file_path.write_bytes(pdf_bytes)

    with open_pdf(file_path) as doc:
        assert doc.page_count == 1
        page = doc.load_page(0)
        assert "Conteúdo de Teste" in page.get_text()
        assert not doc.is_closed

    assert doc.is_closed


def test_open_pdf_from_str_path(tmp_path: Path):
    pdf_bytes = _create_sample_pdf_bytes("Texto via String")
    file_path = tmp_path / "str_doc.pdf"
    file_path.write_bytes(pdf_bytes)

    with open_pdf(str(file_path)) as doc:
        assert doc.page_count == 1
        assert "Texto via String" in doc.load_page(0).get_text()

    assert doc.is_closed


def test_open_pdf_from_bytes():
    pdf_bytes = _create_sample_pdf_bytes("Texto em Memória")

    with open_pdf(pdf_bytes) as doc:
        assert doc.page_count == 1
        assert "Texto em Memória" in doc.load_page(0).get_text()

    assert doc.is_closed


def test_open_pdf_guarantees_closing_on_exception(tmp_path: Path):
    pdf_bytes = _create_sample_pdf_bytes("Exceção Teste")
    file_path = tmp_path / "exc.pdf"
    file_path.write_bytes(pdf_bytes)

    doc_ref = None
    with pytest.raises(RuntimeError, match="Simulando erro interno"):
        with open_pdf(file_path) as doc:
            doc_ref = doc
            raise RuntimeError("Simulando erro interno")

    assert doc_ref is not None
    assert doc_ref.is_closed


def test_pdf_not_found_error(tmp_path: Path):
    non_existent = tmp_path / "inexistente.pdf"

    with pytest.raises(PdfNotFoundError) as exc_info:
        with open_pdf(non_existent):
            pass

    assert "Arquivo PDF não encontrado" in str(exc_info.value)


def test_pdf_not_a_file_error(tmp_path: Path):
    directory_path = tmp_path / "subdiretorio"
    directory_path.mkdir()

    with pytest.raises(PdfNotFoundError) as exc_info:
        with open_pdf(directory_path):
            pass

    assert "não é um arquivo" in str(exc_info.value)


def test_empty_pdf_error_file(tmp_path: Path):
    empty_file = tmp_path / "vazio.pdf"
    empty_file.write_bytes(b"")

    with pytest.raises(EmptyPdfError) as exc_info:
        with open_pdf(empty_file):
            pass

    assert "vazio (0 bytes)" in str(exc_info.value)


def test_empty_pdf_error_bytes():
    with pytest.raises(EmptyPdfError) as exc_info:
        with open_pdf(b""):
            pass

    assert "vazio (0 bytes)" in str(exc_info.value)


def test_corrupted_pdf_error_file(tmp_path: Path):
    corrupt_file = tmp_path / "corrompido.pdf"
    corrupt_file.write_text("Isso definitivamente não é um PDF válido.")

    with pytest.raises(CorruptedPdfError) as exc_info:
        with open_pdf(corrupt_file):
            pass

    assert "não é um PDF válido ou está corrompido" in str(exc_info.value)


def test_corrupted_pdf_error_bytes():
    with pytest.raises(CorruptedPdfError) as exc_info:
        with open_pdf(b"%PDF-1.4 header mas conteudo invalido corrompido"):
            pass

    assert "não corresponde a um PDF válido ou está corrompido" in str(exc_info.value)


def test_invalid_source_type():
    with pytest.raises(TypeError, match="Tipo de fonte inválido para PDF"):
        with open_pdf(12345):  # type: ignore
            pass


def test_encrypted_pdf_with_empty_user_password_auto_unlocks():
    pdf_bytes = _create_sample_pdf_bytes(
        text="Documento com Restrição de Navegador",
        user_pw="",
        owner_pw="master123",
        permissions=int(pymupdf.PDF_PERM_ACCESSIBILITY),
    )

    with open_pdf(pdf_bytes) as doc:
        assert doc.page_count == 1
        assert "Documento com Restrição de Navegador" in doc.load_page(0).get_text()


def test_encrypted_pdf_with_user_password_success():
    pdf_bytes = _create_sample_pdf_bytes(
        text="Documento Confidencial",
        user_pw="senha_secreta_123",
        owner_pw="master123",
    )

    with open_pdf(pdf_bytes, password="senha_secreta_123") as doc:
        assert doc.page_count == 1
        assert "Documento Confidencial" in doc.load_page(0).get_text()


def test_encrypted_pdf_with_invalid_password_raises():
    pdf_bytes = _create_sample_pdf_bytes(
        text="Documento Confidencial",
        user_pw="senha_correta",
        owner_pw="master123",
    )

    with pytest.raises(EncryptedPdfError, match="A senha informada para o documento PDF é inválida"):
        with open_pdf(pdf_bytes, password="senha_errada"):
            pass


def test_encrypted_pdf_without_password_raises():
    pdf_bytes = _create_sample_pdf_bytes(
        text="Documento Fechado",
        user_pw="senha_obrigatoria",
        owner_pw="master123",
    )

    with pytest.raises(EncryptedPdfError, match="protegido por senha e requer autenticação"):
        with open_pdf(pdf_bytes):
            pass


def test_inspect_pdf_metadata():
    pdf_bytes = _create_sample_pdf_bytes(
        text="Texto de Amostra",
        title="Especificação Técnica",
        author="Engenharia de Software",
    )

    info = inspect_pdf(pdf_bytes)
    assert info.page_count == 1
    assert info.title == "Especificação Técnica"
    assert info.author == "Engenharia de Software"
    assert not info.is_encrypted
    assert not info.needs_password
    assert info.can_print
    assert info.can_copy


def test_inspect_pdf_restricted_permissions():
    pdf_bytes = _create_sample_pdf_bytes(
        text="Restrito",
        user_pw="",
        owner_pw="owner123",
        permissions=int(pymupdf.PDF_PERM_ACCESSIBILITY),
    )

    info = inspect_pdf(pdf_bytes)
    assert info.page_count == 1
    assert not info.can_print
    assert not info.can_copy


def test_validate_pdf_and_is_pdf_valid():
    valid_bytes = _create_sample_pdf_bytes("PDF Íntegro")
    invalid_bytes = b"conteudo lixo"

    assert validate_pdf(valid_bytes) is True
    assert is_pdf_valid(valid_bytes) is True
    assert is_pdf_valid(invalid_bytes) is False

    with pytest.raises(CorruptedPdfError):
        validate_pdf(invalid_bytes)


def test_pdf_reader_class_context_manager_and_methods():
    pdf_bytes = _create_sample_pdf_bytes("Via Classe PdfReader")

    reader = PdfReader(pdf_bytes)
    assert reader.is_closed

    with reader as doc:
        assert reader.document is doc
        assert not reader.is_closed
        assert doc.page_count == 1

    assert reader.is_closed

    reader_open = PdfReader.open(pdf_bytes)
    with reader_open as doc2:
        assert doc2.page_count == 1

    reader_open.close()
    assert reader_open.is_closed

    info = PdfReader.inspect(pdf_bytes)
    assert info.page_count == 1
    assert PdfReader.is_valid(pdf_bytes) is True
    assert PdfReader.is_valid(b"dados_invalidos") is False
