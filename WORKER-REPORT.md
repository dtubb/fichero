## 2026-06-28

- Added `fichero-engine/tests/unit/test_node_model_action_audit.py` to broaden
  audit coverage for node-model fold create mutations.
- Green coverage:
  `savedsearch.save` and `note.create` both write `ActionAudit` rows with the
  expected actor, action name, and target id when invoked through the action
  registry.
- Strict `xfail` findings for manager follow-up:
  `POST /api/search/saved` writes directly through `save_search_impl` and
  leaves no `ActionAudit`;
  `POST /api/notes` writes directly through `create_note_impl` and leaves no
  `ActionAudit`;
  `POST /api/bookmarks` creates alias-backed bookmark nodes directly and no
  `bookmark.create` audited action exists;
  milestone creation still folds through direct `db.save(Milestone(...))` and
  no audited milestone create surface exists yet.
- Ran:
  `PYTHONPATH=fichero-engine/src pytest fichero-engine/tests/unit/test_node_model_action_audit.py -q`
  -> `2 passed, 4 xfailed`.
