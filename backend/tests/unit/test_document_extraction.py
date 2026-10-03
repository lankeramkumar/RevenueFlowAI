import pytest

from revenueflowai.documents import MAX_BYTES, DocumentRejected, extract


def _minimal_pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    body = b"%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(body))
        body += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_at = len(body)
    xref = f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        xref += f"{off:010d} 00000 n \n".encode()
    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return body + xref + trailer


def test_text_file_is_extracted_and_hashed():
    doc = extract("note.txt", "text/plain", b"Customer confirmed the payment on 2026-09-30.")
    assert doc.content_type == "text/plain"
    assert doc.text.startswith("Customer confirmed")
    assert len(doc.sha256) == 64


def test_pdf_text_is_extracted():
    doc = extract("remittance.pdf", "application/pdf", _minimal_pdf("Invoice S01-INV-1000 paid in part"))
    assert doc.content_type == "application/pdf"
    assert "S01-INV-1000" in doc.text


def test_unsupported_type_is_rejected():
    with pytest.raises(DocumentRejected) as err:
        extract("payload.exe", "application/octet-stream", b"MZ\x90\x00")
    assert err.value.code == "unsupported_type"


def test_oversized_file_is_rejected():
    with pytest.raises(DocumentRejected) as err:
        extract("big.txt", "text/plain", b"a" * (MAX_BYTES + 1))
    assert err.value.code == "file_too_large"


def test_pdf_extension_without_pdf_header_is_rejected():
    with pytest.raises(DocumentRejected) as err:
        extract("fake.pdf", "application/pdf", b"not a pdf")
    assert err.value.code == "type_mismatch"


def test_empty_text_is_rejected():
    with pytest.raises(DocumentRejected) as err:
        extract("blank.txt", "text/plain", b"   \n  ")
    assert err.value.code == "no_text"
