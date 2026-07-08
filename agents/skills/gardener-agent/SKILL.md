---
description: Run the gardener verification loop (guardrails + roadmap + next work selection) in read-only mode, with optional issue filing.
name: gardener-agent
---

# /gardener-agent

Run the DX gardener helper for deterministic verify + guardrail + roadmap triage:

```bash
scripts/gardener.py
```

**Manager / cron lane.** It invokes `scripts/verify_all.sh`, so the rules in
`/fichero-test` apply: run it from the repo root, one at a time, and never at
`--tier full` on Daniel's active desktop — the platform legs launch GUI windows.
Workers never run this.

Read-only by default:

- runs `scripts/verify_all.sh --standard` and returns non-zero when it fails
- summarizes guardrail progress against each script's `KNOWN_GAPS` / `KNOWN_VIOLATIONS`
- prints roadmap milestone progress and the deterministic `choose_next` selection for
  the highest-incomplete tier of `agents/ROADMAP.md`

## Options

```bash
scripts/gardener.py --tier fast|standard|full
scripts/gardener.py --json
scripts/gardener.py --apply-issues
scripts/gardener.py --self-test
```

Use `--apply-issues` only when intentionally filing follow-up issues — default is report-only.
