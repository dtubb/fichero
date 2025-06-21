"""
Pytest configuration and shared fixtures for API key sharing tests
"""
import os
import sys
import tempfile
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def clean_environment():
    """Clean environment fixture - removes all API key environment variables"""
    api_key_vars = [
        "OPENAI_API_KEY", 
        "DASHSCOPE_API_KEY", 
        "ANTHROPIC_API_KEY", 
        "CLAUDE_API_KEY",
        "HUGGINGFACE_TOKEN"
    ]
    
    # Store original values
    original_values = {}
    for var in api_key_vars:
        original_values[var] = os.environ.get(var)
        if var in os.environ:
            del os.environ[var]
    
    yield
    
    # Restore original values
    for var, value in original_values.items():
        if value is not None:
            os.environ[var] = value
        elif var in os.environ:
            del os.environ[var]


@pytest.fixture
def mock_shared_data():
    """Mock shared data backend for testing"""
    mock_data = {}
    
    class MockSharedData:
        def __init__(self):
            self.backend_name = "mock_backend"
            
        def get_setting(self, key):
            return mock_data.get(key)
            
        def set_setting(self, key, value, immediate_save=True):
            mock_data[key] = value
            
        def clear(self):
            mock_data.clear()
    
    mock_instance = MockSharedData()
    
    with patch('fichero.shared_data.get_shared_data', return_value=mock_instance):
        yield mock_instance


@pytest.fixture
def test_api_keys():
    """Fixture providing test API key values"""
    return {
        "openai": "test_openai_key_12345",
        "qwen": "test_qwen_key_67890", 
        "claude": "test_claude_key_abcde",
        "huggingface": "test_hf_token_fghij"
    }


@pytest.fixture
def environment_with_keys(clean_environment, test_api_keys):
    """Environment fixture with test API keys set"""
    env_mapping = {
        "openai": "OPENAI_API_KEY",
        "qwen": "DASHSCOPE_API_KEY",
        "claude": "ANTHROPIC_API_KEY", 
        "huggingface": "HUGGINGFACE_TOKEN"
    }
    
    for provider, key in test_api_keys.items():
        env_var = env_mapping[provider]
        os.environ[env_var] = key
    
    yield test_api_keys


@pytest.fixture
def shared_data_with_keys(mock_shared_data, test_api_keys):
    """Shared data fixture with test API keys"""
    for provider, key in test_api_keys.items():
        mock_shared_data.set_setting(f"api_key:{provider}", key)
    
    yield mock_shared_data


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory for testing"""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_dir = Path(temp_dir)
        
        # Create typical project structure
        (project_dir / "documents").mkdir()
        (project_dir / "assets").mkdir()
        (project_dir / "logs").mkdir()
        
        yield project_dir


@pytest.fixture
def mock_celery_task():
    """Mock Celery task for testing director functionality"""
    class MockRequest:
        def __init__(self):
            self.id = "test_task_123"
            self.hostname = "test_worker"
            self.delivery_info = {"routing_key": "cpu_intensive"}
    
    class MockTask:
        def __init__(self):
            self.request = MockRequest()
            
        def update_state(self, state=None, meta=None):
            pass
    
    return MockTask()


@pytest.fixture
def capture_logs():
    """Fixture to capture log messages during tests"""
    import logging
    from io import StringIO
    
    log_capture = StringIO()
    handler = logging.StreamHandler(log_capture)
    
    # Get loggers we want to monitor
    loggers = [
        logging.getLogger("fichero.tools.utils.api_keys"),
        logging.getLogger("fichero_director")
    ]
    
    for logger in loggers:
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    
    yield log_capture
    
    # Cleanup
    for logger in loggers:
        logger.removeHandler(handler) 