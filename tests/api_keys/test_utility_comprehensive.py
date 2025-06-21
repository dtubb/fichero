"""
Comprehensive API Key Utility Tests

Extended test suite covering:
- Edge cases and boundary conditions
- Security aspects and key exposure
- Performance and caching scenarios  
- Integration with real tool workflows
- Cross-process and concurrent access
- Provider mapping exhaustive testing
"""
import pytest
import threading
import time
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from concurrent.futures import ThreadPoolExecutor

import sys
sys.path.append('src')

from fichero.tools.utils.api_keys import (
    get_api_key, get_openai_key, get_qwen_key, get_claude_key, get_huggingface_token,
    ensure_api_key, ensure_openai_key, debug_api_key_sources
)
from fichero.shared_data.manager import SharedDataManager


class TestEdgeCasesAndBoundaryConditions:
    """Test edge cases and boundary conditions"""
    
    def test_very_long_api_keys(self, mock_shared_data):
        """Should handle very long API keys correctly"""
        # Create extremely long API key (10KB)
        long_key = "sk-" + "x" * 10000
        mock_shared_data.set_setting("api_key:openai", long_key)
        
        result = get_openai_key()
        assert result == long_key
        assert len(result) > 10000
    
    def test_unicode_and_special_characters(self, mock_shared_data):
        """Should handle Unicode and special characters in API keys"""
        special_keys = [
            "sk-测试key123",  # Unicode characters
            "sk-key_with-dashes.dots",  # Common special chars
            "sk-key with spaces",  # Spaces
            "sk-key\"with'quotes",  # Quotes
        ]
        
        for i, special_key in enumerate(special_keys):
            provider = f"test_provider_{i}"
            mock_shared_data.set_setting(f"api_key:{provider}", special_key)
            
            result = get_api_key(provider)
            assert result == special_key
    
    def test_whitespace_handling(self, mock_shared_data, clean_environment):
        """Should handle whitespace in API keys appropriately"""
        # Test leading/trailing whitespace
        mock_shared_data.set_setting("api_key:openai", "  sk-test123  ")
        result = get_openai_key()
        assert result == "  sk-test123  "  # Should preserve whitespace
        
        # Test empty strings - should fall back to environment (which is clean)
        mock_shared_data.set_setting("api_key:qwen", "")
        result = get_qwen_key()
        assert result is None  # Empty string falls back, no env var = None
        
        # Test whitespace-only - should preserve whitespace (truthy string)
        mock_shared_data.set_setting("api_key:claude", "   ")
        result = get_claude_key()  
        assert result == "   "  # Whitespace-only is preserved as valid key
    
    def test_case_sensitivity(self, mock_shared_data):
        """Provider names should be case sensitive"""
        mock_shared_data.set_setting("api_key:openai", "sk-lower")
        mock_shared_data.set_setting("api_key:OpenAI", "sk-upper") 
        
        # Should get exact case match - both exist as separate keys
        assert get_api_key("openai") == "sk-lower"
        assert get_api_key("OpenAI") == "sk-upper"  # Different case key exists


class TestAllProvidersExhaustive:
    """Exhaustive testing of all provider mappings"""
    
    def test_all_supported_providers(self, environment_with_all_providers, mock_shared_data):
        """Test all currently supported providers work correctly"""
        # Clear shared data to force environment fallback
        mock_shared_data.clear()
        
        providers_and_env_vars = {
            "openai": "OPENAI_API_KEY",
            "qwen": "DASHSCOPE_API_KEY", 
            "claude": "ANTHROPIC_API_KEY",
            "huggingface": "HUGGINGFACE_TOKEN"
        }
        
        for provider, env_var in providers_and_env_vars.items():
            # Test environment fallback - should get the fixture env var values  
            result = get_api_key(provider)
            expected_key = environment_with_all_providers[env_var]
            assert result == expected_key
            
            # Test debug function shows correct mapping
            debug_info = debug_api_key_sources(provider)
            assert debug_info["sources"]["environment"]["variable"] == env_var
    
    def test_unsupported_provider_graceful_handling(self, clean_environment, mock_shared_data):
        """Unsupported providers should be handled gracefully"""
        mock_shared_data.clear()
        
        unsupported_providers = [
            "google", "microsoft", "aws", "azure", 
            "unknown", "invalid", "new_provider"
        ]
        
        for provider in unsupported_providers:
            result = get_api_key(provider)
            assert result is None
            
            # Debug should show no environment mapping
            debug_info = debug_api_key_sources(provider)
            assert "No environment variable mapping" in debug_info["sources"]["environment"]["error"]


class TestConcurrentAccess:
    """Test concurrent access scenarios"""
    
    def test_concurrent_access_same_key(self, mock_shared_data):
        """Multiple threads accessing same key should work correctly"""
        mock_shared_data.set_setting("api_key:openai", "sk-concurrent-test")
        
        results = []
        errors = []
        
        def get_key():
            try:
                result = get_openai_key()
                results.append(result)
            except Exception as e:
                errors.append(e)
        
        # Run 20 concurrent requests
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(get_key) for _ in range(20)]
            for future in futures:
                future.result()  # Wait for completion
        
        # All should succeed
        assert len(errors) == 0
        assert len(results) == 20
        assert all(r == "sk-concurrent-test" for r in results)


class TestPerformanceAndCaching:
    """Test performance characteristics"""
    
    def test_repeated_calls_performance(self, mock_shared_data):
        """Repeated calls should be reasonably fast"""
        mock_shared_data.set_setting("api_key:openai", "sk-performance-test")
        
        # Warm up
        get_openai_key()
        
        # Time 100 calls (reduced for faster testing)
        start_time = time.time()
        for _ in range(100):
            result = get_openai_key()
            assert result == "sk-performance-test"
        end_time = time.time()
        
        # Should complete in under 2 seconds
        duration = end_time - start_time
        assert duration < 2.0, f"100 calls took {duration:.2f}s, too slow"


class TestSecurityAspects:
    """Test security-related aspects"""
    
    def test_no_key_leakage_in_logs(self, mock_shared_data, capture_logs):
        """API keys should not appear in full in log messages"""
        secret_key = "sk-very-secret-key-that-should-not-leak-1234567890"
        mock_shared_data.set_setting("api_key:openai", secret_key)
        
        # Use the key
        result = get_openai_key()
        assert result == secret_key
        
        # Check logs don't contain full key
        log_contents = capture_logs.getvalue()
        assert secret_key not in log_contents
        assert "very-secret-key" not in log_contents
        
        # Should have appropriate debug message without key
        assert "Using shared data for openai API key" in log_contents
    
    def test_debug_function_truncates_keys(self, mock_shared_data):
        """Debug function should truncate sensitive keys"""
        secret_key = "sk-very-long-secret-key-that-should-be-truncated-1234567890"
        mock_shared_data.set_setting("api_key:openai", secret_key)
        
        debug_info = debug_api_key_sources("openai")
        
        # Should show truncated version
        shared_value = debug_info["sources"]["shared_data"]["value"]
        assert len(shared_value) <= 13  # "sk-very-lo..." format
        assert shared_value.endswith("...")
        assert "secret-key-that-should-be-truncated" not in shared_value


class TestIntegrationScenarios:
    """Test real-world integration scenarios"""
    
    def test_tool_workflow_simulation(self, mock_shared_data):
        """Simulate real tool workflow using API keys"""
        # Setup like a real tool would have
        mock_shared_data.set_setting("api_key:openai", "sk-tool-workflow-test")
        mock_shared_data.set_setting("api_key:qwen", "qwen-tool-workflow-test")
        
        # Simulate transcription tool workflow
        def simulate_transcribe_tool(api_key_arg=None):
            qwen_key = get_qwen_key(api_key_arg)
            if not qwen_key:
                raise ValueError("Qwen API key required for transcription")
            return f"transcription_result_using_{qwen_key[:10]}"
        
        # Simulate LLM processing tool workflow  
        def simulate_llm_tool(api_key_arg=None):
            openai_key = get_openai_key(api_key_arg)
            if not openai_key:
                raise ValueError("OpenAI API key required for LLM processing")
            return f"llm_result_using_{openai_key[:10]}"
        
        # Test normal workflow (keys from shared data)
        transcription_result = simulate_transcribe_tool()
        assert "qwen-tool-" in transcription_result  # First 10 chars: "qwen-tool-"
        
        llm_result = simulate_llm_tool()
        assert "sk-tool-wo" in llm_result
        
        # Test CLI override workflow
        transcription_result = simulate_transcribe_tool("cli-qwen-override")
        assert "cli-qwen-o" in transcription_result
    
    def test_cross_process_simulation(self):
        """Simulate cross-process API key sharing"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Process 1: Settings system stores API keys
            shared_data_1 = SharedDataManager(namespace="cross_process", data_dir=Path(temp_dir))
            shared_data_1.set_setting("api_key:openai", "sk-cross-process-test")
            shared_data_1.backend.save_to_disk()
            
            # Process 2: Worker process reads API keys
            shared_data_2 = SharedDataManager(namespace="cross_process", data_dir=Path(temp_dir))
            
            with patch('fichero.shared_data.get_shared_data', return_value=shared_data_2):
                # Worker should be able to access the key
                result = get_openai_key()
                assert result == "sk-cross-process-test"


class TestErrorRecoveryAndResilience:
    """Test error recovery and system resilience"""
    
    def test_shared_data_intermittent_failures(self, environment_with_keys, test_api_keys):
        """Should handle intermittent shared data failures gracefully"""
        call_count = 0
        
        def failing_get_shared_data():
            nonlocal call_count
            call_count += 1
            if call_count % 3 == 0:  # Fail every 3rd call
                raise Exception(f"Simulated failure #{call_count}")
            # Return mock that returns None for get_setting
            mock = Mock()
            mock.get_setting.return_value = None
            return mock
        
        with patch('fichero.shared_data.get_shared_data', side_effect=failing_get_shared_data):
            # Should fall back to environment variables on failures
            for _ in range(6):
                result = get_openai_key()
                assert result == test_api_keys["openai"]  # From environment
    
    def test_malformed_shared_data_responses(self, clean_environment):
        """Should handle malformed shared data responses gracefully"""
        mock_shared_data = Mock()
        
        # Test various malformed responses
        malformed_responses = [
            Exception("Database error"),
            None,
            "",
            False,
            0
        ]
        
        for response in malformed_responses:
            if isinstance(response, Exception):
                mock_shared_data.get_setting.side_effect = response
            else:
                mock_shared_data.get_setting.return_value = response
            
            with patch('fichero.shared_data.get_shared_data', return_value=mock_shared_data):
                # Should not crash, should fall back to environment (which is clean) = None
                result = get_api_key("openai")
                assert result is None


# Custom fixtures for comprehensive testing
@pytest.fixture
def environment_with_all_providers():
    """Environment with all supported provider keys"""
    env_vars = {
        "OPENAI_API_KEY": "test_openai_key",
        "DASHSCOPE_API_KEY": "test_qwen_key",
        "ANTHROPIC_API_KEY": "test_claude_key", 
        "HUGGINGFACE_TOKEN": "test_huggingface_key"
    }
    
    # Clear environment first, then set test values
    with patch.dict('os.environ', env_vars, clear=True):
        yield env_vars


@pytest.fixture
def capture_logs():
    """Capture log output for testing"""
    import io
    import logging
    
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    logger = logging.getLogger('fichero.tools.utils.api_keys')
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    
    yield log_capture
    
    logger.removeHandler(handler) 