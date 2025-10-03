# Fichero Test Suite

This directory contains the new modular test structure for Fichero, built around the ViewModel/NavigationController architecture.

## Test Structure

```
tests/
├── unit/                    # Unit tests (components in isolation)
│   ├── test_navigation_controller.py
│   ├── test_library_viewmodel.py
│   └── test_collection_viewmodel.py
├── integration/             # Integration tests (component interactions)
│   ├── test_console_interface.py
│   └── test_service_integration.py
├── ui/                     # GUI-specific tests (when needed)
│   └── test_view_integration.py
└── run_tests.py            # Test runner
```

## Key Features

- **No GUI Dependencies**: Core tests run without requiring Toga/GUI initialization
- **Fast Execution**: Tests use mock services and in-memory databases
- **Modular Design**: Each component can be tested independently
- **Console Interface**: Provides scriptable testing of library operations
- **Comprehensive Coverage**: Tests both unit-level and integration scenarios

## Running Tests

### Run All Tests
```bash
python tests/run_tests.py all
```

### Run Specific Categories
```bash
python tests/run_tests.py unit           # Unit tests only
python tests/run_tests.py integration    # Integration tests only
python tests/run_tests.py console       # Console interface tests only
```

### Run Specific Test File
```bash
python tests/run_tests.py --file unit.test_navigation_controller
```

### Verbose Output
```bash
python tests/run_tests.py all --verbose
```

## Console Interface Testing

The console interface provides a powerful way to test library functionality without the GUI:

```bash
# Run console interface directly
python -m fichero.interfaces.console_interface

# Example console commands
fichero> library add "Test Collection" local
fichero> library list
fichero> nav collection col-123
fichero> collection list
fichero> nav back
fichero> test all
```

## Architecture Benefits

1. **Separation of Concerns**: Business logic is tested independently of UI
2. **Reliability**: Tests don't depend on GUI state or timing issues
3. **Speed**: Fast test execution without GUI initialization overhead
4. **Debugging**: Console interface allows manual testing and debugging
5. **CI/CD Friendly**: Tests can run in headless environments

## Test Philosophy

- **Test the Logic, Not the UI**: Focus on testing navigation, data management, and business rules
- **Use Real Services**: Integration tests use actual LibraryService and NavigationController
- **Mock External Dependencies**: Database operations use temporary files
- **Comprehensive Workflows**: Test complete user workflows through console interface

## Adding New Tests

### Unit Tests
Add to `unit/` directory for testing individual components:
```python
class TestNewComponent(unittest.TestCase):
    def setUp(self):
        # Create component with mocked dependencies
        pass

    def test_component_behavior(self):
        # Test component logic
        pass
```

### Integration Tests
Add to `integration/` directory for testing component interactions:
```python
class TestComponentIntegration(unittest.TestCase):
    def setUp(self):
        # Create real components with test database
        pass

    def test_workflow(self):
        # Test complete workflows
        pass
```

This test structure ensures that the refactored architecture maintains reliability while being much easier to test and debug.