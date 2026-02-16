# Backend Development Standards

## Best Practices

### API Design
- **RESTful Conventions**: Follow standard HTTP methods (GET, POST, PUT, DELETE)
- **Pydantic Models**: Use Pydantic for request/response validation
- **Error Handling**: Consistent HTTP error codes (400, 404, 500) with meaningful messages
- **Documentation**: Use docstrings for all endpoints

### Code Quality
- **Type Hints**: Use Python type hints for all functions
- **Async/Await**: Use async/await for I/O operations
- **Dependency Injection**: Pass dependencies explicitly rather than global state
- **Logging**: Use structured logging for debugging and monitoring

### Database Operations
- **DuckDB**: Use for structured metadata queries
- **LanceDB**: Use for vector search and semantic operations
- **Transactions**: Use proper transaction management for data consistency

## Testing Standards

### Unit Testing
- **Isolation**: Test individual components in isolation
- **Mocking**: Use unittest.mock or pytest-mock for dependencies
- **Coverage**: Aim for 100%+ test coverage on critical paths

### Integration Testing
- **End-to-End**: Test complete API flows
- **Real Dependencies**: Use real database connections where possible
- **Test Client**: Use FastAPI TestClient for API testing

### Test Organization
```
tests/
├── unit/                # Isolated component tests
│   ├── test_api.py       # API endpoint tests
│   ├── test_db.py        # Database operation tests
│   └── test_models.py    # Data model tests
└── integration/         # End-to-end tests
    ├── test_workflows.py # Workflow execution tests
    └── test_search.py    # Search functionality tests
```

### Running Tests
```bash
# Run all tests
pytest tests/

# Run specific test type
pytest tests/unit/
pytest tests/integration/

# Run with coverage
pytest --cov=src/fichero tests/
```

