# Adversarial review — #2430 per-page artifact pass-through (46766c23..5ed566d2)

Verdict: APPROVE to close #2430 (core race fixed, complete, real-DB regression test).
Two non-blocking follow-ups (P1 user-edit staleness; P1 swallowed ValidationError).

## Verified
- All 4 per-page save_artifact sites in vision_base forward document=_preloaded_doc (grep: 4/4). No other save paths.
- _preloaded_doc always non-None on the per-page branch (line 1579 guard `continue`s before save when _page_doc_id falsy).
- Production passes full model_dump(mode="json") dicts (sources.py 270/463/501/674/842); Document.model_validate() accepts json-mode (ISO datetime str, enum value) — confirmed by exec.
- Removing orphan-save is safe: every per-page path passes document=; non-per-page paths still resolve by id or file_path-when-no-id.
- 31 changed/new tests green. Deterministic race repro (test_explicit_id_survives_transient_invisibility) uses an uncommitted second connection — valid MVCC-invisibility proof; goes red without the fix (db.get→None→return None).

## Findings
- P1 (#672 staleness): pass-through doc is a snapshot from the SOURCE node; user_edited guard (llm_base.py ~535) now reads stale metadata. User editing page_content DURING a per-page run → flag absent in snapshot → save_artifact clobbers the edit. Old db.get read the live row. Narrow but a real #672-class regression. Not #2430-class (no misrouting). Fix: re-check user_edited against a fresh read before promoting page_content.
- P1 (swallowed ValidationError): model_validate at llm_base.py ~473 runs INSIDE the broad try; a partial/malformed dict raises → caught by `except Exception: return artifact_id` (None) → silent loss, and db.get fallback never runs. Prod dicts validate, so defensive. Fix: try/except around model_validate → log + fall back to db.get(document_id).
- P2: `if doc is not None:` (llm_base ~530) is dead after the early `if doc is None: return None`; comment describes an impossible "artifact saved, doc update deferred" scenario. Stale/misleading.
- P2 (test fidelity): test_workflow_tools uses model_dump() (python mode); prod uses mode="json". Concurrency test covers json-style strings, so covered overall — align for clarity.
