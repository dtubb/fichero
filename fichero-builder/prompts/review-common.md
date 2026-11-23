COMMON RULES for a review session (Fichero, a macOS/iOS archive app; Python engine fichero-server/, Swift app fichero/, specs docs/contributor_manual/specs/**):
- Work ONLY in your own git worktree (named in the brief). Edit only docs/contributor_manual/specs/** (and mkdocs.yml nav if you add a page) and your report file. Do NOT change code. Commit spec changes on your branch; the harness lands them. You never push.
- Commit trailers: exactly the ones the brief names. No Co-Authored-By.
- Public repo: no secrets, no absolute home paths, no hostnames, no archive/collection/person names from the owner's sources, never quote the owner verbatim.
- Spec style: read AGENTS.md and an existing spec; spec lines have ids and [OK]/[PARTIAL]/[GAP]/[BROKEN] tags; tag by CHECKING THE CODE (cite file/function); every [GAP]/[BROKEN] cites an issue #N. Reuse an existing issue (search the open issues) or tag the line `→ #NEW-n` (n = the number in your Issues list; a search spec may use `#NEW-Sn`). Never a bare `#NEW`. Do not create issues yourself: `builder review approve` files them.
- The spec's `## Build order` is yours to write: one `#### Step N.M — title` per ranked fix, each with Behaviours, Tests and Size (see an existing spec). The harness adds the issue numbers to the headings.
- TEST, don't just read: run the existing unit tests for your area, and where useful measure on a SCRATCH engine/library only: set FICHERO_BASE_PATH to a fresh dir under $TMPDIR and use a new scratch library there; NEVER open the owner's libraries or anything *.fichero you did not create. Use at most ~20 real page images, read-only, from the sources folder the brief names. Heavier runs only where the brief says; clean up after.
- No paid API spend. Local models only.
- Deliver: (1) the report `review-<area>.md` in the worktree root (it is excluded from commits), with these `##` headings, in this order:
  1. What exists
  2. Measured (numbers; what was run, on what, how long)
  3. What is broken, slow or missing (ranked)
  4. Ranked fixes: a numbered list, each item sized for one builder step (25 files or fewer), with the tests to write. Each item cites the issue it belongs to as `NEW-n` (from your Issues list) or `#N` (an existing issue), and its spec step as `[N.M]`.
  5. Issues to file: a list, one line per issue: `NEW-n title (behaviour ids in backticks)`. Number them 1..k with no gap (`NEW-S1..` for a second run of numbers).
  6. Open questions: a numbered list of what only the owner can decide, or the word "none". Each also goes in the spec as a question.
  7. Existing issues that gained evidence (optional): a list, `#N what you measured or found for it`.
  The harness refuses a report missing a heading, with an empty Issues list, or with a ranked fix that cites no issue.
  (2) spec commits on your branch making the specs say what should be, tagged honestly.
- End with `DONE <sha of the branch head>` and a 12-line summary: the branch, the commit shas, the top 5 fixes.
