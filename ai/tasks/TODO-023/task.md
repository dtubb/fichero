# TODO-023: Fix Backend Launch Issues

## What to do
Fix backend launch crashes by adding missing dependency and fixing database migration

## Steps
- [ ] Step 1: Add python-multipart to pyproject.toml dependencies
- [ ] Step 2: Fix database migration to handle missing workflows table gracefully
- [ ] Step 3: Test backend launch to ensure it works
- [ ] Step 4: Update documentation if needed

## Files
- File to change: pyproject.toml
- File to change: src/fichero/db.py
- File to test: src/fichero/api/main.py

## Questions for Human
- [ ] Question 1: Should we add python-multipart to all platforms or just macOS?
    Answer: [Space for answer]
- [ ] Question 2: Should the database migration create the workflows table if it doesn't exist?
    Answer: [Space for answer]

## Answers and Implementation
- [Summary of decisions made]
- [Implementation approach chosen]

## Need help?
- Ask if anything is unclear
- Keep it simple