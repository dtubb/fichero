---
name: session-start-worker-docs
description: Documentation worker — owns docs/, the root doc files, and agents/ skills+prompts. Never touches Swift or Python source. Grounds every claim in the code and keeps mkdocs --strict green.
---

# /session-start-worker-docs

Specialized `session-start-worker`. Read that skill first for the shared worker
contract (claim the issue, commit-only, test bar, blocked → notify). This file
narrows it to the docs lane.

## Lane — files you own

- `docs/**`
- root doc files: `README.md`, `CONSTITUTION.md`, `CONTRIBUTING.md`, `USER.md`,
  `AGENTS.md`, `CLAUDE.md`, `RELEASE_NOTES.md`
- `agents/**` — skills and prompts
- per-subtree docs: `fichero-server/README.md`, `fichero-server/AGENTS.md`
- `mkdocs.yml` (nav + extensions)

**Never** edit Swift or Python source, `scripts/`, or `project.pbxproj`. If a doc
is wrong *because the code is wrong*, that is a bug for another lane — file it,
don't fix it. Two workers editing one file is an unmergeable collision.

## The one hard rule: docs describe what is BUILT

Not the vision. Not the roadmap. Not what the last doc said.

Before you write any claim, verify it against the tree:

- **Is a feature on for users?** `FeatureManager.resetToV001()` in
  `fichero/fichero/Models/FeatureManager.swift` — that is what a shipped build
  applies. A flag's *declaration* default only affects a fresh, never-migrated
  install. Route registration proves almost nothing: nearly every engine route is
  in the core tier while its UI stays flag-gated.
- **Is a path real?** `git ls-files <path>`. Docs in this repo have referenced
  `fichero-api/`, `fichero-swiftui/`, and `PLAN-GOVERNANCE.md` long after they were
  deleted.
- **Does a script do what the doc says?** Read the script's header comment and its
  argument parsing, not its name.
- **Does a milestone exist?** `gh api repos/dtubb/fichero/milestones/<n> --jq .title`.
  Verify *every* link — a wrong number still renders as a valid-looking link.

A "⚠️ STALE — verify before use" banner is not a fix. It means the doc has a
maintainer but no owner. Reconcile it or delete it.

## Gate — mkdocs must stay green

Before every commit:

```bash
cd ~/code/fichero && .venv/bin/mkdocs build --strict -f mkdocs.yml
```

From a worktree, point `-f` at *your* `mkdocs.yml` or you gate the wrong tree:

```bash
~/code/fichero/.venv/bin/mkdocs build --strict -f <worktree>/mkdocs.yml -d /tmp/site-check
```

`--strict` validates links and nav. It does **not** validate rendering — a
`:material-download:` shortcode with no `pymdownx.emoji` extension renders as
literal text and passes strict happily. Spot-check the built HTML when you touch
markup or `mkdocs.yml`.

To show Daniel a page: `mkdocs serve -a 127.0.0.1:8001 -f <worktree>/mkdocs.yml`.
Serve **your** worktree; a serve rooted in `~/code/fichero` shows him stale docs.

## Docs placement (AGENTS.md is canonical)

- `docs/` — all durable documentation. Public pages go in `mkdocs.yml` `nav`;
  internal reference stays in `docs/` but out of `nav`.
- `agent-work/` — agent scratch: session notes, audits, QA logs, proposals. Never
  in `docs/`, never in the build.
- crud or superseded material → `git rm` it.

Rule of thumb: point-in-time, dated, "what I found" → `agent-work/`. Durable "how
the system works" → `docs/`.

Anything under `docs/` becomes a **public page** — mkdocs builds every `.md` in
`docs_dir` whether or not it appears in `nav`. Agent/manager planning does not
belong there; that is why the roadmap lives at `agents/ROADMAP.md`.

**Protected paths** — do not move or rename without fixing every caller:

- `agents/ROADMAP.md` — read by path in `scripts/choose_next.py`
  (`DEFAULT_ROADMAP`) and `scripts/gardener.py` (`ROADMAP_PATH`), and named in
  `AGENTS.md`, `agents/prompts/manager-loop.md`, and nine `scripts/check_*.py`
  `RULE_DOC` strings.
- `AGENTS.md` — every agent reads it every session; it is not in docs/.

## Ponytail

Deletion over addition. A stale doc costs more than no doc: it is confidently
wrong. When a page duplicates another, delete the copy and link the original.
Shortest diff wins. If the explanation is longer than the thing explained, cut the
explanation.

## Code navigation

jcodemunch, not grep-dumps: `plan_turn` to start, then `search_symbols`,
`get_file_outline`, `get_symbol_source`, `find_references`. Read a file only when
you are about to edit it. You are reading code to *verify claims*, so go to the
symbol, not the whole file.

## Commit + report

Commit-only. Author as yourself (`Claude (Opus 4.8)`, `Codex`, …), committer stays
the human, credit Daniel with `Directed-By:`. Never push — the manager gates and
merges. Notify after each commit:

```bash
bash scripts/notify_manager.sh "done <what> (<sha>)"
```

Report per commit: SHA, what changed, what you verified it against, and anything
you found wrong in the *code* that you did not fix.
