"""A run's failed page is named as the Reader names it, never by its storage name (#4416, #5290).

WHY: Activity details show `failures[].page`. A PDF's page children are stored under the upload's temp name
(`fichero_upload_<random>.pdf`), so the file's basename put a storage artifact in front of the person;
DocumentTitleTests (app) flags it. The engine's one title rule is `views.page_title`.
"""
from __future__ import annotations

from fichero_server.models import DocType, Document, FileType
from fichero_server.workflows.run_account import PageFailure, _title_failed_pages


def test_a_failed_pdf_page_is_named_by_its_pdf_and_number_never_its_storage_name(db):
    pdf = Document(name="18590129.pdf", doc_type=DocType.file, file_type=FileType.pdf)
    db.save(pdf)
    page = Document(name="fichero_upload_c84fgjke.pdf", doc_type=DocType.page, parent_id=pdf.id, sequence=3)
    image = Document(name="c01_012.jpg", doc_type=DocType.file, file_type=FileType.image)
    for d in (page, image):
        db.save(d)
    failures = [PageFailure(page="fichero_upload_c84fgjke.pdf", document_id=page.id, reason="x"),
                PageFailure(page="c01_012.jpg", document_id=image.id, reason="x"),
                PageFailure(page="gone.jpg", document_id="no-such-page", reason="x")]

    _title_failed_pages(db, failures)

    assert [f.page for f in failures] == ["18590129.pdf › Page 3", "c01_012.jpg", "gone.jpg"]
    assert not any("fichero_upload_" in f.page for f in failures)
