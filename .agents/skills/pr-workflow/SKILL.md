---
description: Create a pull request — runs quality checks, formats PR from conventions in AGENTS.md, creates it via gh. Works for any project.
name: pr-workflow
---

# /pr-workflow

Create a pull request the right way. Reads conventions from `AGENTS.md`. Runs `/build-and-test` first.

## Step 1 — Check prerequisites

```bash
git status          # must be clean
git branch          # confirm on a feature branch, not main
git log --oneline main..HEAD   # commits going into this PR
```

If working tree is dirty or on main — stop and flag it.

## Step 2 — Run quality checks

Run `/build-and-test`. If anything fails — stop. Fix first, PR second.

## Step 3 — Read conventions

From `AGENTS.md` or `.Codex/AGENTS.md`, find:
- Commit message format
- Branch naming conventions
- Any PR checklist or requirements
- Base branch (usually `main`)

## Step 4 — Write PR description

```markdown
## Summary
[2-4 bullet points: what changed and why]

## What was tested
[How you verified this works]

## Checklist
- [ ] Build passes
- [ ] Tests pass
- [ ] Lint passes
- [ ] No generated files edited manually
- [ ] Commit messages follow conventions

Closes #[issue number if applicable]
```

## Step 5 — Create the PR

```bash
gh pr create \
  --title "[conventional type]: [concise description]" \
  --body "[description from step 4]" \
  --base main
```

## Step 6 — Report

Print the PR URL. Note it in `STATE.md` In Progress section.

Do NOT merge. Do NOT push to main. Daniel approves merges.
