# STATE.md — Fichero

## Next Session — Start Here (2026-05-14 morning)

**Latest commit: `798bb940`. Branch: 0.0.2.** Full session log in HISTORY.md (entry: 2026-05-13).

### What to check first

- **#998 graph view crash** — clicking Graph in OntologyBrowser crashes with `brk #0x1` because `applyRepulsion` / `applySprings` / `integrate` re-read `nodes.count` while consuming a `positions` snapshot. Fix sketched in the issue: bound every loop by `min(positions.count, forces.count)`; guard `applySprings` indices against the bound. **Re-run the build after the fix; the bug is reproducible with one catalogued doc.**
- **#999 mermaid header crash** — `/api/workflow-execution/threads/{id}/diagram.png` 500s when mermaid.ink upstream-fails because the fallback puts mermaid source in an HTTP header (UTF-8 + newlines). Fix: base64-encode the header payload, or move the fallback into the response body.
- Daniel was running with a **freshly nuked library** containing one file (his preface) when both bugs surfaced; old library backed up at `~/Library/Application Support/com.fichero.fichero/global.fichero.nuked-20260513-210450/` if it's needed for repro.

### What to do first

1. Fix #998 (small, isolated; revalidate by re-clicking Graph).
2. Fix #999 (also small; base64 the header).
3. Rebuild + re-test catalogue → KG flow on the one-file library.

### Don't break

- The new typed SVO fields on KnowledgeClaim ([[feedback_pydantic_field_must_be_declared]] applies — they're declared, but readers must prefer them and only fall back to metadata).
- `.claude/worktrees/` is now in `.gitignore` — don't accidentally re-add the worktree submodules with `git add -A`.

### Open backlog (12 issues on the 0.0.2 milestone)

#928 PDF loupe (blocked on #783) · #958 structured artifact editors (multi-day) · #961 console hygiene (needs running app) · #998 graph crash · #999 mermaid header · 0.0.2 release chain #659/#660/#661/#662/#665.
