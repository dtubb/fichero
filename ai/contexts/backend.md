# Backend Development Context

## Overview

Python/FastAPI backend development patterns and best practices for Fichero.

## Key Components

- **FastAPI Application**: `src/fichero/api/main.py`
- **API Routes**: `src/fichero/api/routes/`
- **Data Layer**: `src/fichero/db.py`, `src/fichero/models.py`
- **AI Integration**: `src/fichero/llm.py`, `src/fichero/workflows/`

## Development Patterns

### API Endpoint Structure

```python
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/v1/resource", tags=["resource"])

class ResourceCreate(BaseModel):
    name: str
    description: Optional[str] = None

class ResourceResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    created_at: datetime

@router.post("/", response_model=ResourceResponse, status_code=status.HTTP_201_CREATED)
async def create_resource(resource: ResourceCreate):
    """Create a new resource"""
    try:
        result = await service.create_resource(resource)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")
```

### Error Handling

- **400 Bad Request**: Client errors and validation failures
- **404 Not Found**: Resource not found
- **500 Internal Server Error**: Server errors
- Provide meaningful error messages
- Log errors for debugging

### Database Operations

```python
# DuckDB for structured data
async def get_document(document_id: str):
    query = "SELECT * FROM documents WHERE id = ?"
    result = await db.execute(query, (document_id,))
    return result.fetchone()

# LanceDB for vector search
async def semantic_search(query: str, limit: int = 10):
    embeddings = await get_embeddings(query)
    results = await lancedb.search(embeddings, limit=limit)
    return results
```

## Testing

### Unit Testing
```python
def test_create_document():
    mock_db = MagicMock()
    service = DocumentService(db=mock_db)
    result = service.create_document({"name": "test"})
    assert result["name"] == "test"
```

### Integration Testing
```python
def test_document_endpoint():
    from fastapi.testclient import TestClient
    from fichero.api.main import app
    
    client = TestClient(app)
    response = client.post("/api/v1/documents/", json={"name": "test"})
    assert response.status_code == 201
```

## Best Practices

- Use Pydantic models for request/response validation
- Implement proper error handling and logging
- Follow REST conventions for API design
- Write comprehensive tests for all functionality
- Document API endpoints with docstrings
- Use async/await for I/O operations
- Implement proper authentication and authorization