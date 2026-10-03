"""Document intake: validate the upload's type and size, then extract text.
Only plain text and PDF are accepted. Extraction is deterministic; no model
is involved in reading a document.
"""

import hashlib
import io
from dataclasses import dataclass

from pypdf import PdfReader

MAX_BYTES = 10 * 1024 * 1024
ALLOWED_TYPES = ("text/plain", "application/pdf")


class DocumentRejected(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class ExtractedDocument:
    content_type: str
    byte_size: int
    sha256: str
    text: str


def extract(filename: str, declared_type: str, data: bytes) -> ExtractedDocument:
    if len(data) == 0:
        raise DocumentRejected("empty_file", "The file is empty.")
    if len(data) > MAX_BYTES:
        raise DocumentRejected("file_too_large", f"Files are limited to {MAX_BYTES // (1024 * 1024)} MB.")

    lower = filename.lower()
    if lower.endswith(".pdf") or data[:5] == b"%PDF-":
        if data[:5] != b"%PDF-":
            raise DocumentRejected("type_mismatch", "A .pdf file must start with a PDF header.")
        content_type = "application/pdf"
        try:
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        except Exception as exc:
            raise DocumentRejected("unreadable_pdf", "The PDF could not be read.") from exc
    elif lower.endswith(".txt") or declared_type == "text/plain":
        content_type = "text/plain"
        try:
            text = data.decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            raise DocumentRejected("not_utf8", "Text files must be UTF-8 encoded.") from exc
    else:
        raise DocumentRejected("unsupported_type", "Only .txt and .pdf files are accepted.")

    if not text:
        raise DocumentRejected("no_text", "No extractable text was found in the document.")

    return ExtractedDocument(
        content_type=content_type,
        byte_size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        text=text,
    )
