## 2026-06-28

- Added append-only P5 prototype inheritance tests in
  `fichero-engine/tests/unit/test_node_prototypes.py` and
  `fichero-engine/tests/unit/test_routes_documents.py`.
- Verified builtin `folder -> room` and `folder -> research_workspace`
  inheritance, leaf override precedence for a user-defined child of `room`,
  assignment through `PUT /api/documents/{doc_id}/prototype`, and resolver
  behavior for builtin-parent chains.
- Ran:
  `PYTHONPATH=fichero-engine/src pytest fichero-engine/tests/unit/test_node_prototypes.py -q`
  and
  `PYTHONPATH=fichero-engine/src pytest fichero-engine/tests/unit/test_routes_documents.py -q`
  — both passed.
