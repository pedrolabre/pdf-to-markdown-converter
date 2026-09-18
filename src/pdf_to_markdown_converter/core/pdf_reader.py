from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Generator

import pymupdf


class PdfReaderError(Exception):
    pass


class PdfNotFoundError(PdfReaderError, FileNotFoundError):
    pass


class EmptyPdfError(PdfReaderError, ValueError):
    pass


class CorruptedPdfError(PdfReaderError, ValueError):
    pass


class EncryptedPdfError(PdfReaderError, PermissionError):
    pass


@dataclass(frozen=True)
class PdfDocumentInfo:
    page_count: int
    is_encrypted: bool
    needs_password: bool
    is_repaired: bool
    permissions: int
    can_print: bool
    can_copy: bool
    title: str = ""
    author: str = ""
    format: str = ""


def _open_pymupdf_document(
    source: str | Path | bytes,
    password: str = "",
) -> pymupdf.Document:
    if isinstance(source, (str, Path)):
        file_path = Path(source)
        if not file_path.exists():
            raise PdfNotFoundError(f"Arquivo PDF não encontrado: {file_path}")
        if not file_path.is_file():
            raise PdfNotFoundError(f"O caminho informado não é um arquivo: {file_path}")
        if file_path.stat().st_size == 0:
            raise EmptyPdfError(f"O arquivo PDF está vazio (0 bytes): {file_path}")
        try:
            doc = pymupdf.open(str(file_path))
        except (pymupdf.EmptyFileError, ValueError) as err:
            raise EmptyPdfError(f"O arquivo PDF está vazio: {file_path}") from err
        except pymupdf.FileDataError as err:
            raise CorruptedPdfError(
                f"O arquivo informado não é um PDF válido ou está corrompido: {file_path}"
            ) from err
        except pymupdf.FileNotFoundError as err:
            raise PdfNotFoundError(f"Arquivo PDF não encontrado: {file_path}") from err
        except Exception as err:
            raise CorruptedPdfError(f"Falha ao abrir arquivo PDF: {file_path}") from err
    elif isinstance(source, (bytes, bytearray)):
        if len(source) == 0:
            raise EmptyPdfError("O buffer de dados do PDF está vazio (0 bytes).")
        try:
            doc = pymupdf.open(stream=source, filetype="pdf")
        except (pymupdf.EmptyFileError, ValueError) as err:
            raise EmptyPdfError("O buffer de dados do PDF está vazio.") from err
        except pymupdf.FileDataError as err:
            raise CorruptedPdfError(
                "O buffer de dados não corresponde a um PDF válido ou está corrompido."
            ) from err
        except Exception as err:
            raise CorruptedPdfError("Falha ao abrir buffer de dados do PDF.") from err
    else:
        raise TypeError(
            f"Tipo de fonte inválido para PDF. Esperado str, Path ou bytes, recebido {type(source).__name__}."
        )

    if doc.needs_pass or doc.is_encrypted:
        if password:
            auth_result = doc.authenticate(password)
            if auth_result == 0:
                doc.close()
                raise EncryptedPdfError("A senha informada para o documento PDF é inválida.")
        else:
            auth_result = doc.authenticate("")
            if doc.needs_pass and auth_result == 0:
                doc.close()
                raise EncryptedPdfError(
                    "O documento PDF está protegido por senha e requer autenticação."
                )

    return doc


@contextmanager
def open_pdf(
    source: str | Path | bytes,
    password: str = "",
) -> Generator[pymupdf.Document, None, None]:
    doc = _open_pymupdf_document(source, password)
    try:
        yield doc
    finally:
        if doc is not None and not doc.is_closed:
            doc.close()


def validate_pdf(source: str | Path | bytes, password: str = "") -> bool:
    with open_pdf(source, password):
        return True


def is_pdf_valid(source: str | Path | bytes, password: str = "") -> bool:
    try:
        with open_pdf(source, password):
            return True
    except PdfReaderError:
        return False


def inspect_pdf(source: str | Path | bytes, password: str = "") -> PdfDocumentInfo:
    with open_pdf(source, password) as doc:
        metadata = doc.metadata or {}
        permissions = doc.permissions
        can_print = bool(permissions & pymupdf.PDF_PERM_PRINT)
        can_copy = bool(permissions & pymupdf.PDF_PERM_COPY)
        return PdfDocumentInfo(
            page_count=doc.page_count,
            is_encrypted=bool(doc.is_encrypted),
            needs_password=bool(doc.needs_pass),
            is_repaired=bool(getattr(doc, "is_repaired", False)),
            permissions=permissions,
            can_print=can_print,
            can_copy=can_copy,
            title=str(metadata.get("title") or ""),
            author=str(metadata.get("author") or ""),
            format=str(metadata.get("format") or ""),
        )


class PdfReader:
    def __init__(self, source: str | Path | bytes, password: str = "") -> None:
        self._source = source
        self._password = password
        self._doc: pymupdf.Document | None = None

    def __enter__(self) -> pymupdf.Document:
        self._doc = _open_pymupdf_document(self._source, self._password)
        return self._doc

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def close(self) -> None:
        if self._doc is not None and not self._doc.is_closed:
            self._doc.close()

    @property
    def document(self) -> pymupdf.Document | None:
        return self._doc

    @property
    def is_closed(self) -> bool:
        return self._doc is None or self._doc.is_closed

    @classmethod
    def open(cls, source: str | Path | bytes, password: str = "") -> "PdfReader":
        return cls(source, password)

    @classmethod
    def inspect(cls, source: str | Path | bytes, password: str = "") -> PdfDocumentInfo:
        return inspect_pdf(source, password)

    @classmethod
    def is_valid(cls, source: str | Path | bytes, password: str = "") -> bool:
        return is_pdf_valid(source, password)
