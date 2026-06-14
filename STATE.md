# STATE — backend handoff 2026-06-14

Branch `0.0.2` @ `0c2f27c8`, pushed clean. Keep `0.0.2 == origin`.

## Current Focus

Backend-only autonomous work remains allowed; do **not** proceed to Mac/SwiftUI without Daniel. AI Infrastructure #83 / #2056 is drained and closed; remaining work is backend-safe follow-up: guardrails, comparison/evaluation, OCR geometry, observable/change-stream, API contract cleanup, and efficiency.

## Completed This Session

- **#2061** shipped image-editing backend strategy doc: local-first Pillow/PyMuPDF, optional Quartz/Core Image, narrow OpenCV helper, no-cloud posture.
- **#2205** shipped backend Pydantic persistence guardrail; full `verify_all --standard` passed (`4992 passed, 22 skipped, 21 xfailed`).
- **#1644** shipped Apple Vision OCR line/word geometry with text API compatibility; focused backend tests passed.
- **#2206** filed for provider-agnostic OCR/transcription geometry across Apple Vision, VLM JSON, Google, AWS, optional Azure, and local OCR/layout APIs.
- **#2001** shipped observable non-route save guardrail; focused checks passed and issue closed.
- GitHub issue review released stale `status:in-progress` from **#2008**; held lanes left untouched.

## In Progress / Held

- No active autonomous backend worker lanes.
- Held worktrees: `~/code/fichero-worktrees/entitytable-2020` (#2020) and `~/code/fichero-worktrees/lan-tls-2157` (#2157). Do not touch unless Daniel explicitly resumes them.
- `.claude/worktrees/agent-aaf4fec2eced9c821` still exists; leave alone.

## Next Session — Start Here

1. Check `git status`, `git worktree list`, and `tmux list-windows -t fichero-workers`; expect only main + held lanes.
2. If continuing backend, pick one focused issue: **#2206** OCR geometry contract, **#2008** hermeneutics `interpretation.*` emits, **#1715** library-header OpenAPI cleanup, or **#1863** uniform change-stream architecture.
3. Use external codex worktrees under `~/code/fichero-worktrees/`; workers must claim issues, write focused tests, commit, and stop.
4. Batch full `verify_all --standard` after risky/API/DB/god-node batches; focused checks are acceptable for small guardrail/docs slices.
5. Do not touch Mac/SwiftUI, #2157, #2020, or Swift client wiring without Daniel.

## Hard Rules

- Backend edits happen in worker worktrees, then manager cherry-picks atomic commits.
- Push only after verification; never push red.
- New backend API changes require OpenAPI/client sync.
- Pydantic/OpenAPI fields must be declared and typed; no silent `additionalProperties` or dynamic `extra="allow"` persistence.
- Cloud providers, including Google/AWS/Azure OCR, require explicit consent and must be blocked in local-only mode.
