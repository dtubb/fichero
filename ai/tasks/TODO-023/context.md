# Context for TODO-023: Fix Backend Launch Issues

## Background
Backend crashes when trying to launch due to missing dependency and database migration failure

## What you need to know
- python-multipart is required by FastAPI for file uploads (UploadFile parameter)
- Database migration tries to check workflows table schema but table doesn't exist
- This prevents the backend from starting, blocking development and testing

## Ask if unclear
- Request human input if needed