# Appendix B: How Fichero Is Built


Fichero is built openly with the help of AI coding agents, under review gates and verification steps documented in the repository. The project is transparent about its construction for the same reason the app treats AI as an instrument, not an interlocutor: you should be able to see what the machine actually did.

### Manager and workers

Work is organized around a manager/worker split. A manager agent is the control lane: it reads project state and the roadmap, triages GitHub issues, decides what to do next, and dispatches work — but writes no product code. Worker agents are the implementation lane: each picks up one assigned issue, implements it completely, writes tests, runs verification, commits, and reports back. GitHub Issues and Milestones are the source of truth, and the project works one milestone at a time.

Each worker runs in its own isolated git worktree so parallel work never collides, and the manager partitions work so parallel lanes touch disjoint files. Cheap local models are the default for routine work; more capable models are reserved for keystone changes.

### Review and verification gates

Before a sweep of changes is committed, the project runs a review gate rather than self-certifying: a code-review pass, a simplification pass, and then a build/test integration gate. Two rules are non-negotiable: work is never marked complete without build, test, and lint passing, and nothing is pushed on top of an unverified commit. Workers commit to their own lane branches; only the manager merges a lane, after the full gate runs against it.

### Durable memory

What the agents learn persists: a durable memory index records recurring bug patterns, hard rules (such as “iterate, never replace” existing code), and architectural decisions, so future sessions start informed rather than relearning the same mistakes.

This appendix describes the development workflow, not a feature of the app.
