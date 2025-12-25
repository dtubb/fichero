# Context for TODO-049: Fix API pytest issues and ensure background tests run properly

## Background
API tests are failing due to database lock issues, provider naming inconsistencies, and timeout problems. The backend API server was running and holding a lock on the database, preventing tests from running properly.

## What you need to know
- Database lock: The backend API server (uvicorn) was running on port 8765 and holding a lock on the DuckDB database
- Provider naming: Tests expect "apple_vision" provider type but the actual implementation uses "apple"
- Timeouts: Some tests are timing out when trying to connect to API endpoints
- The provider catalog is defined in src/fichero/providers.py with ProviderType enum
- API routes are in src/fichero/api/routes/providers.py

## No not Ask if unclear
- Do not request human input if needed