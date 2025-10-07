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

---

## Director Integration Tests

### Test Files

**Unit Tests**: `tests/unit/test_director_integration_updated.py`
- Tests new no-copy, hierarchical output structure
- 5 comprehensive test cases covering DirectorIntegrationService

**End-to-End CLI Tests**: `tests/test_cli_end_to_end.sh`
- 6 bash-based integration tests
- Tests complete processing pipeline from CLI
- Validates hierarchical structure and no-copy behavior

### Running Director Integration Tests

```bash
# Run unit tests (Python)
PYTHONPATH=src python -m pytest tests/unit/test_director_integration_updated.py -v

# Run CLI end-to-end tests (Bash)
chmod +x tests/test_cli_end_to_end.sh
./tests/test_cli_end_to_end.sh
```

### Test Coverage

#### Unit Tests (test_director_integration_updated.py)

1. **TestHierarchicalOutputStructure**
   - `test_generate_output_structure_basic`: Validates Collection/Date/Workflow/Item structure
   - `test_generate_output_structure_sanitization`: Ensures special chars are sanitized
   - `test_generate_output_structure_duplicate_handling`: Verifies duplicate path numbering

2. **TestNoCopyProcessing**
   - `test_process_file_batch_no_copying`: Confirms files are NOT copied during processing

3. **TestLibraryProcessingIntegration**
   - `test_process_folder_item_hierarchical_structure`: End-to-end hierarchical structure validation

**All 5 tests PASSING** ✅

#### CLI End-to-End Tests (test_cli_end_to_end.sh)

1. **Test 1**: CLI help command works
2. **Test 2**: Plans list command works
3. **Test 3**: Library database accessible
4. **Test 4**: Process command (Tiny Test - 2 images)
5. **Test 5**: Hierarchical output structure verification
6. **Test 6**: No file copying verification (in-place processing)

**All 6 tests PASSING** ✅

### Test Philosophy: No-Copy Processing

The new architecture implements **in-place processing**:
- Files are NOT copied into library storage
- Processing happens directly from source locations
- Output stored in hierarchical structure: `Collection/Date/Workflow/Item/`
- Scalable for large collections (tested with 800 folders, 100,000 files)

### Integration Points Tested

1. **DirectorIntegrationService._generate_output_structure()**: Path generation
2. **DirectorIntegrationService._process_file_batch()**: No-copy batch processing
3. **DirectorIntegrationService.process_items()**: Complete workflow orchestration
4. **CLI process command**: End-to-end pipeline from user input to processed output
5. **Hierarchical structure creation**: Filesystem organization validation

### Troubleshooting

**Issue**: Tests fail with "Plan config is None"
**Solution**: Ensure plan files exist in `src/fichero/resources/config_defaults/plans/`

**Issue**: Database errors during tests
**Solution**: Tests use temporary databases - ensure write permissions

**Issue**: CLI tests timeout on Medium Test
**Solution**: Expected behavior for 216 images - use Tiny Test (2 images) for quick validation

### CI/CD Integration

```yaml
# Example GitHub Actions workflow
- name: Run Director Integration Tests
  run: |
    PYTHONPATH=src python -m pytest tests/unit/test_director_integration_updated.py -v
    chmod +x tests/test_cli_end_to_end.sh
    ./tests/test_cli_end_to_end.sh
```

---

## GUI Integration Tests

### Test Files

**Unit Tests**: `tests/unit/test_gui_processing_integration.py`
- Tests GUI Process button workflow
- Tests progress display integration with TaskMonitor
- Tests OutputView loading of hierarchical results
- 7 comprehensive test cases

**Manual GUI Checker**: `tests/manual_gui_test.py`
- Interactive script to verify GUI setup before testing
- Checks database, collections, items, director, and plans
- Provides diagnostic information for debugging

### Running GUI Integration Tests

```bash
# Run automated GUI integration tests
PYTHONPATH=src TOGA_BACKEND=toga_cocoa python -m pytest tests/unit/test_gui_processing_integration.py -v

# Run manual GUI setup checker
PYTHONPATH=src python tests/manual_gui_test.py
```

### Test Coverage (GUI Integration)

1. **TestGUIProcessButton**
   - `test_process_button_with_items`: Verifies DirectorIntegrationService called with correct params
   - `test_process_button_with_folder`: Verifies Director folder processing path

2. **TestProgressDisplayIntegration**
   - `test_progress_display_registers_with_task_monitor`: Verifies ProgressDisplay has director access
   - `test_task_monitor_callback_flow`: Verifies callbacks can be registered

3. **TestOutputViewIntegration**
   - `test_output_view_loads_hierarchical_results`: Verifies OutputsManager loads results
   - `test_output_view_finds_outputs_in_collection_structure`: Verifies hierarchical discovery

4. **TestEndToEndGUIWorkflow**
   - `test_complete_workflow_button_to_output`: Complete workflow from processing to output loading

**All 7 tests PASSING** ✅

### GUI Update Flow

The Process button triggers this flow:

1. **CollectionView._on_process_requested()** → User confirmation
2. **DirectorIntegrationService.process_items()** → Task submission
3. **TaskMonitor callbacks** → Progress updates
4. **NavigationEventBus** → Event publishing ("collection_item_updated")
5. **CollectionView._on_item_progress_updated()** → GUI refresh
6. **DetailedList updates** → Item subtitles show "Processing: XX%"

### Manual Testing Guide

```bash
# 1. Check setup
PYTHONPATH=src python tests/manual_gui_test.py

# 2. Launch GUI
FORCE_MOBILE_UI=false TOGA_BACKEND=toga_cocoa briefcase dev

# 3. Navigate to "Small Test Collection"

# 4. Click Process button

# 5. Verify you see:
#    - Confirmation dialog
#    - "Processing Started" dialog
#    - Item subtitle updates (if processing takes time)
#    - Check logs for detailed progress

# 6. Check outputs
ls ~/Library/Application\ Support/ca.tubb.fichero/processed/
```

### Complete Test Summary

**Total Test Coverage:**
- 5 Director Integration unit tests ✅
- 6 CLI end-to-end tests ✅
- 7 GUI integration tests ✅
- **18 tests total** covering complete workflow

**Test Pyramid:**
```
        GUI Tests (7)
       /              \
  CLI Tests (6)    Unit Tests (5)
       \              /
     Director Integration
```

All tests validate the no-copy, hierarchical processing architecture.