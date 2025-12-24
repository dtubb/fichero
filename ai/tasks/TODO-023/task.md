# TODO-023: Fix Backend Launch Issues

## What to do
Fix backend launch crashes by adding missing dependency and fixing database migration

## Steps
- [x] Step 1: Add python-multipart to pyproject.toml dependencies
- [x] Step 2: Fix database migration to handle missing workflows table gracefully
- [x] Step 3: Test backend launch to ensure it works
- [x] Step 4: Update documentation if needed

## Files
- File to change: pyproject.toml
- File to change: src/fichero/db.py
- File to test: src/fichero/api/main.py

## Questions for Human
- [x] Question 1: Should we add python-multipart to all platforms or just macOS?
    Answer: This is just a macOS app. But, add to pyproject file and install to .venv
- [x] Question 2: Should the database migration create the workflows table if it doesn't exist?
    Answer: Do e need database migrastion, when we're devleping an app? we can just delete and start over. Thoguths? maybe its  good to ahve mgiration, so we can use in futrue if we need it?
    I
## Answers and Implementation
- Added python-multipart>=0.0.5 to pyproject.toml dependencies section
- Modified _migrate_workflow_table() to check if table exists before attempting migration
- Modified _migrate_saved_search_table() to use DuckDB's information_schema instead of sqlite_master
- Changed print statements to logger calls for better logging integration
- Successfully tested database initialization and FastAPI app creation

## Need help?
- Ask if anything is unclear
- Keep it simple