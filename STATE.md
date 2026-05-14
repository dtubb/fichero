# STATE.md — Fichero

## Next Session — Start Here (2026-05-14 morning)

**Latest commit: `7129193e`. Branch: 0.0.2.** Full bug ledger in HISTORY.md (entry: 2026-05-13 evening). 19 issues filed in this evening's testing pass: #998–#1016.

### What to do first — fix in this order

1. **#998 graph crash** — root cause now confirmed: an `AppKitProgressView` somewhere in the OntologyBrowser path has `min == max == 32.142857` (likely a 225/7 division for chip widths) and the float-equality fails, looping AppKit's constraint solver until `NSGenericException` fires. Find the ProgressView with the bad float frame and round to int. **One-file fix; unblocks Graph view entirely.**
2. **#1000 + #1004 + #1008 backend lock-up cluster** — every long-running backend operation freezes the UI because it runs sync inside an `async def` handler. One sweep with `asyncio.to_thread` across `/workflow-execution`, `/semantic/embed`, `/claims/embed` fixes the whole cluster.
3. **#1001 extraction quality** — Apple Intelligence guardrail trips on the extraction prompt → silent OpenRouter Sonnet fallback → SVO never written, descriptions degenerate, entities mistyped. Either (a) re-prompt to dodge the guardrail, or (b) make the fallback path use the same `with_structured_output()` schema. This is the upstream cause of #1003/#1006/#1009/#1011/#1016.
4. Then the UI-cleanup batch: #1005, #1007, #1010, #1012, #1013, #1014, #1015 — most are small.

### Don't break

- The rebuilt one-file library lives at `~/Library/Application Support/com.fichero.fichero/global.fichero/` — Daniel will quit + restart for a fresh test session.
- `.claude/worktrees/` is in `.gitignore`; do not add worktree submodules.

### Open backlog beyond today's filings

12 pre-existing 0.0.2 issues remain (#928 PDF loupe, #958 structured artifact editors, #961 console hygiene, plus the release chain #659/#660/#661/#662/#665).
