## 2026-06-28

- Extended `fichero-engine/tests/unit/test_node_model_action_audit.py` to cover
  the broader mutation surface requested for #1848 audit coverage.
- Passing audited-action coverage now exists for:
  `savedsearch.save`,
  `note.create`,
  `claim.create`,
  `claim.patch`,
  `claim.delete`,
  `document.create`,
  `document.move`,
  `document.delete`,
  and folder creation through `document.create` with `doc_type="folder"`.
- Strict `xfail` gaps surfaced in the current public mutation surface:
  `POST /api/search/saved` bypasses the registry;
  `POST /api/notes` bypasses the registry;
  `POST /api/bookmarks` bypasses the registry and no `bookmark.create` action exists;
  milestone creation folds through direct `db.save(Milestone(...))` and no audited milestone create surface exists;
  `POST /api/claims` bypasses the registry;
  `PATCH /api/claims/{claim_id}` bypasses the registry;
  `DELETE /api/claims/{claim_id}` bypasses the registry;
  `POST /api/documents` bypasses the registry;
  `POST /api/documents` with `doc_type="folder"` bypasses the registry;
  `PUT /api/documents/{doc_id}/move` bypasses the registry;
  `DELETE /api/documents/{doc_id}` bypasses the registry;
  `POST /api/entities` bypasses the registry and no `entity.create` action exists;
  `PATCH /api/entities/{entity_id}` bypasses the registry and no `entity.update` action exists;
  `DELETE /api/entities/{entity_id}` bypasses the registry and no `entity.delete` action exists.
- Ran:
  `PYTHONPATH=fichero-engine/src pytest fichero-engine/tests/unit/test_node_model_action_audit.py -q`
  -> `9 passed, 14 xfailed`.
