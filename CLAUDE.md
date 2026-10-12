# CLAUDE.md

The single canonical agent/operational doc is **`AGENTS.md`** (operational manual,
hard rules, key paths, code-navigation policy, Xcode notes). Read it first.

The detailed architecture & development guide is `AGENTS.md`; the product
north-star is `CONSTITUTION.md`. Architecture context docs are in `docs/contributor_manual/architecture/`.

**Start here:** `STATE.md` (gitignored, in the repo root checkout) holds the current state and "Next Session — Start Here". Code navigation: jcodemunch to find and read, the pyright and swift LSP plugins for definitions and references. Workers and subagents use the cheapest model that will do (haiku); the manager does the integrating, testing and pushing.
