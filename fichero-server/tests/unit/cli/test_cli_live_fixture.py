from tests.integration._cli_live import fill_path


def test_fill_path_uses_seeded_ids_and_fallback():
    summary = {
        "keys": {
            "artifact": "art-1",
            "doc_letter": "doc-1",
            "entity_person": "ent-1",
            "collection": "folder-1",
            "page": "page-1",
            "workflow": "wf-1",
        },
        "ids": {"claims": ["claim-1"]},
    }

    assert fill_path("/api/documents/{document_id}/claims/{claim_id}", summary) == "/api/documents/doc-1/claims/claim-1"
    assert fill_path("/api/missing/{unknown_id}", summary) == "/api/missing/contract-walk-nonexistent"
