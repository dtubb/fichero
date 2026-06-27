# Contributing

Fichero is written by AI coding agents that Daniel directs. He is an
anthropologist, not a software engineer, so he does not write Swift or Python from
scratch. He decides what to build, what is broken, and what ships; the agents do
the typing.

## How the work runs

- A **manager** agent (`session-start-manager`) holds the control lane. It triages
  GitHub issues, picks the next batch, and dispatches it. It does not write source
  code.
- Each **worker** agent runs in its own git worktree under
  `~/code/fichero-worktrees/<name>`, in a separate tmux window (an interactive
  `claude` or `codex` session). A worker grinds one milestone's GitHub issues and
  commits as itself (Claude or Codex), crediting Daniel with a `Co-Authored-By`
  trailer.
- The manager **reviews** each worker's output, **build-gates** it, runs
  `verify_all`, then **merges via PR**, closes the issues, and dispatches the next
  batch. Daniel reviews the result and judges every release by using the app.

GitHub Issues plus Milestones is the source of truth for the backlog. Work lands on
the milestone branch; there are no per-task branches.

## More detail

See [AGENTS.md](AGENTS.md) for the operational manual (hard rules, commit
attribution, docs placement, worker orchestration), and the folder-specific
guidance in [fichero/AGENTS.md](fichero/AGENTS.md) and
[fichero-engine/AGENTS.md](fichero-engine/AGENTS.md). For the fuller repo
conventions, see
[site/docs/contributor/setup-and-contributing.md](site/docs/contributor/setup-and-contributing.md).
