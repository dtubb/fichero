---
description: Run the gardener verification loop (guardrails + roadmap + next work selection) in read-only mode, with optional issue filing.
name: gardener-agent
---

# /gardener-agent

Run the DX gardener helper for deterministic verify+guardrail + roadmap triage:

```bash
scripts/gardener.py
```

By default this is read-only and safe for manager/cron use:
- runs `scripts/verify_all.sh --standard`
- summarizes guardrail progress against each script’s `KNOWN_GAPS` / `KNOWN_VIOLATIONS`
- prints roadmap milestone progress and `choose_next` selection for the highest-incomplete tier
- chooses the next work directly from the highest-incomplete ROADMAP tier (deterministic)
- returns non-zero when verification fails
- is deterministic and safe for cron: read-only report mode by default

## Options

```bash
scripts/gardener.py --tier fast|standard|full
scripts/gardener.py --json
scripts/gardener.py --apply-issues
scripts/gardener.py --self-test
```

Use `--apply-issues` only when intentionally filing follow-up issues — default is report-only.
