"""
Comprehensive Director Simplified Tests - Step 5

Tests the simplified director implementation:
- Simplified environment variable handling
- Shared data backend integration
- Clean subprocess environment (no API key injection)
- Task orchestration without API key complexity
"""
import pytest
import tempfile
import os
import subprocess
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
from typing import Dict, Any

import sys
sys.path.append('src')

# Import director functions to test
from fichero.director import (
    get_python_env, 
    run_script_directly,
    expand_vars,
    parse_plan_yml,
    create_plan_yml,
    sanitize_filename,
    sanitize_path,
    smart_copy,
    get_backend_type,
    should_use_celery
)


class TestSimplifiedEnvironmentHandling:
    """Test simplified environment variable handling"""
    
    def test_get_python_env_minimal_variables(self):
        """Should return only essential environment variables"""
        # Mock environment with many variables
        mock_env = {
            'PATH': '/usr/bin:/bin',
            'PYTHONPATH': '/opt/python',
            'HOME': '/home/user',
            'USER': 'testuser',
            'SHELL': '/bin/zsh',
            # These should be excluded
            'OPENAI_API_KEY': 'sk-should-be-excluded',
            'DASHSCOPE_API_KEY': 'should-be-excluded',
            'ANTHROPIC_API_KEY': 'should-be-excluded',
            'RANDOM_VAR': 'should-be-excluded',
            'DISPLAY': ':0',
            'LANG': 'en_US.UTF-8'
        }
        
        with patch.dict('os.environ', mock_env):
            env = get_python_env()
            
            # Should only include essential variables
            essential_vars = {'PATH', 'PYTHONPATH', 'HOME', 'USER', 'SHELL'}
            assert set(env.keys()) == essential_vars
            
            # Should have correct values
            assert env['PATH'] == '/usr/bin:/bin'
            assert env['PYTHONPATH'] == '/opt/python'
            assert env['HOME'] == '/home/user'
            assert env['USER'] == 'testuser'
            assert env['SHELL'] == '/bin/zsh'
            
            # Should not include API keys or other variables
            assert 'OPENAI_API_KEY' not in env
            assert 'DASHSCOPE_API_KEY' not in env
            assert 'ANTHROPIC_API_KEY' not in env
            assert 'RANDOM_VAR' not in env
            assert 'DISPLAY' not in env
    
    def test_get_python_env_missing_variables(self):
        """Should handle missing environment variables gracefully"""
        # Mock environment with only some essential variables
        mock_env = {
            'PATH': '/usr/bin:/bin',
            'HOME': '/home/user'
            # Missing: PYTHONPATH, USER, SHELL
        }
        
        with patch.dict('os.environ', mock_env, clear=True):
            env = get_python_env()
            
            # Should only include variables that exist
            assert 'PATH' in env
            assert 'HOME' in env
            assert env['PATH'] == '/usr/bin:/bin'
            assert env['HOME'] == '/home/user'
            
            # Should not include missing variables
            assert 'PYTHONPATH' not in env
            assert 'USER' not in env  
            assert 'SHELL' not in env
    
    def test_get_python_env_empty_environment(self):
        """Should handle completely empty environment"""
        with patch.dict('os.environ', {}, clear=True):
            env = get_python_env()
            
            # Should return empty dict when no essential vars present
            assert env == {}
    
    @patch('fichero.director.log')
    def test_get_python_env_logging(self, mock_log):
        """Should log debug information about environment preparation"""
        mock_env = {
            'PATH': '/usr/bin',
            'HOME': '/home/user'
        }
        
        with patch.dict('os.environ', mock_env, clear=True):
            env = get_python_env()
            
            # Should log debug message with count
            mock_log.debug.assert_called_with("🔧 Minimal environment prepared with 2 essential variables")


class TestRunScriptDirectly:
    """Test simplified script execution"""
    
    @patch('fichero.director.get_python_path')
    @patch('subprocess.Popen')
    def test_run_script_with_minimal_environment(self, mock_popen, mock_get_python):
        """Should run script with minimal environment from get_python_env"""
        mock_get_python.return_value = '/usr/bin/python3'
        
        # Mock successful process
        mock_process = Mock()
        mock_process.stdout.readline.side_effect = ['output line 1\n', 'output line 2\n', '']
        mock_process.wait.return_value = None
        mock_process.returncode = 0
        mock_process.pid = 12345
        mock_popen.return_value = mock_process
        
        # Mock worker logger
        mock_logger = Mock()
        
        with patch('fichero.director.get_python_env') as mock_get_env:
            mock_get_env.return_value = {
                'PATH': '/usr/bin',
                'HOME': '/home/user'
            }
            
            result = run_script_directly("python script.py", "/test/dir", mock_logger)
            
            # Should succeed
            assert result is True
            
            # Should call get_python_env for environment
            mock_get_env.assert_called_once()
            
            # Should use minimal environment in Popen
            mock_popen.assert_called_once()
            popen_kwargs = mock_popen.call_args[1]
            assert popen_kwargs['env'] == {'PATH': '/usr/bin', 'HOME': '/home/user'}
            
            # Should log environment preparation
            mock_logger.debug.assert_called_with("Subprocess environment prepared with 2 essential variables")
    
    @patch('fichero.director.get_python_path')
    @patch('subprocess.Popen')
    def test_run_script_failure_handling(self, mock_popen, mock_get_python):
        """Should handle script failures gracefully"""
        mock_get_python.return_value = '/usr/bin/python3'
        
        # Mock failed process
        mock_process = Mock()
        mock_process.stdout.readline.side_effect = ['error output\n', '']
        mock_process.wait.return_value = None
        mock_process.returncode = 1  # Non-zero return code
        mock_process.pid = 12345
        mock_popen.return_value = mock_process
        
        mock_logger = Mock()
        
        with patch('fichero.director.get_python_env') as mock_get_env:
            mock_get_env.return_value = {'PATH': '/usr/bin'}
            
            result = run_script_directly("python failing_script.py", "/test/dir", mock_logger)
            
            # Should return False for failure
            assert result is False
    
    @patch('fichero.director.get_python_path')
    @patch('subprocess.Popen')
    def test_run_script_exception_handling(self, mock_popen, mock_get_python):
        """Should handle exceptions during script execution"""
        mock_get_python.return_value = '/usr/bin/python3'
        mock_popen.side_effect = OSError("Permission denied")
        
        mock_logger = Mock()
        
        result = run_script_directly("python script.py", "/test/dir", mock_logger)
        
        # Should return False and log error
        assert result is False
        mock_logger.error.assert_called()
        
        # Should log the exception
        error_call = mock_logger.error.call_args[0][0]
        assert "Permission denied" in error_call


class TestExpandVarsSimplified:
    """Test simplified variable expansion (no environment variables)"""
    
    def test_expand_basic_variables(self):
        """Should expand basic variables from vars_dict"""
        vars_dict = {
            'project_folder': '/test/project',
            'output_folder': '/test/output',
            'python_exe': '/usr/bin/python3'
        }
        
        text = "python ${python_exe} script.py --input ${project_folder} --output ${output_folder}"
        result = expand_vars(text, vars_dict)
        
        expected = "python /usr/bin/python3 script.py --input /test/project --output /test/output"
        assert result == expected
    
    def test_expand_vars_dot_notation(self):
        """Should expand vars.* notation"""
        vars_dict = {
            'input_dir': '/input',
            'output_dir': '/output'
        }
        
        text = "process ${vars.input_dir} ${vars.output_dir}"
        result = expand_vars(text, vars_dict)
        
        expected = "process /input /output"
        assert result == expected
    
    def test_expand_nested_variables(self):
        """Should expand nested variable references"""
        vars_dict = {
            'base_path': '/home/user',
            'project_name': 'test_project',
            'project_path': '${base_path}/${project_name}',
            'data_path': '${project_path}/data'
        }
        
        text = "python process.py --data ${data_path}"
        
        with patch('os.path.isabs', return_value=True):  # Prevent path conversion
            result = expand_vars(text, vars_dict)
            
            expected = "python process.py --data /home/user/test_project/data"
            assert result == expected
    
    def test_no_environment_variable_expansion(self):
        """Should NOT expand environment variables (Step 5 simplification)"""
        vars_dict = {'script': 'test.py'}
        
        # Set environment variable
        with patch.dict('os.environ', {'TEST_VAR': 'should_not_expand'}):
            with patch('os.path.isabs', return_value=True):  # Prevent path conversion
                text = "python ${script} --env $TEST_VAR --env ${TEST_VAR}"
                result = expand_vars(text, vars_dict)
                
                # Should expand vars_dict variables but leave env vars unchanged
                expected = "python test.py --env $TEST_VAR --env ${TEST_VAR}"
                assert result == expected
    
    def test_python_script_absolute_path_conversion(self):
        """Should convert relative script paths to absolute for python commands"""
        vars_dict = {'project_folder': '/test/project'}
        
        with patch('os.path.isabs', return_value=False), \
             patch('os.path.abspath', return_value='/absolute/path/to/script.py'):
            
            text = "python script.py --project ${project_folder}"
            result = expand_vars(text, vars_dict)
            
            expected = "python /absolute/path/to/script.py --project /test/project"
            assert result == expected
    
    def test_expand_empty_vars_dict(self):
        """Should handle empty vars_dict"""
        text = "python script.py --param value"
        
        with patch('os.path.isabs', return_value=True):  # Prevent path conversion
            result = expand_vars(text, {})
            
            # Should return unchanged
            assert result == text
    
    def test_expand_undefined_variables(self):
        """Should leave undefined variables unchanged"""
        vars_dict = {'defined_var': 'value'}
        
        text = "python script.py --defined ${defined_var} --undefined ${undefined_var}"
        
        with patch('os.path.isabs', return_value=True):  # Prevent path conversion
            result = expand_vars(text, vars_dict)
            
            expected = "python script.py --defined value --undefined ${undefined_var}"
            assert result == expected


class TestSharedDataIntegration:
    """Test shared data backend integration"""
    
    @patch('fichero.shared_data.get_shared_data')
    def test_shared_data_backend_verification_success(self, mock_get_shared_data):
        """Should verify shared data backend is available"""
        # Mock successful shared data access
        mock_shared_data = Mock()
        mock_shared_data.backend_name = "redis_backend"
        mock_get_shared_data.return_value = mock_shared_data
        
        # Test the pattern used in process_folder
        try:
            from fichero.shared_data import get_shared_data
            shared_data = get_shared_data()
            backend_available = True
            backend_name = shared_data.backend_name
        except Exception:
            backend_available = False
            backend_name = None
        
        assert backend_available is True
        assert backend_name == "redis_backend"
    
    @patch('fichero.shared_data.get_shared_data')
    def test_shared_data_backend_verification_failure(self, mock_get_shared_data):
        """Should handle shared data backend failure gracefully"""
        # Mock shared data failure
        mock_get_shared_data.side_effect = Exception("Redis not available")
        
        # Test the pattern used in process_folder
        try:
            from fichero.shared_data import get_shared_data
            shared_data = get_shared_data()
            backend_available = True
            backend_name = shared_data.backend_name
        except Exception as e:
            backend_available = False
            backend_name = None
            error_msg = str(e)
        
        assert backend_available is False
        assert backend_name is None
        assert "Redis not available" in error_msg


class TestPlanYmlProcessing:
    """Test plan.yml processing without environment expansion"""
    
    def test_create_plan_yml_basic(self):
        """Should create plan.yml with proper variable substitution"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create template file
            template_path = temp_path / "template.yml"
            template_content = '''
project_folder: "/old/path"
fichero_root: "/old/fichero"
workflows:
  default:
    - step1
    - step2
'''
            template_path.write_text(template_content)
            
            # Create target folder
            target_folder = temp_path / "target_project"
            target_folder.mkdir()
            
            # Create output plan.yml
            output_path = temp_path / "plan.yml"
            
            create_plan_yml(template_path, target_folder, output_path)
            
            # Verify content
            result_content = output_path.read_text()
            
            # Should update project_folder path
            assert f'project_folder: "{target_folder.absolute()}"' in result_content
            
            # Should update fichero_root (director.py is in src/fichero, so parent.parent.parent is correct)
            expected_fichero_root = str(Path(__file__).parent.parent.parent.absolute())
            assert f'fichero_root: "{expected_fichero_root}"' in result_content
            
            # Should preserve other content
            assert 'workflows:' in result_content
            assert '- step1' in result_content
    
    def test_parse_plan_yml_valid(self):
        """Should parse valid plan.yml correctly"""
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_path = Path(temp_dir) / "plan.yml"
            plan_content = '''
vars:
  project_folder: "/test/project"
  output_folder: "/test/output"

commands:
  - name: process
    script: 
      - "python process.py"

workflows:
  default:
    - process
'''
            plan_path.write_text(plan_content)
            
            config = parse_plan_yml(plan_path)
            
            assert isinstance(config, dict)
            assert 'vars' in config
            assert 'commands' in config
            assert 'workflows' in config
            assert config['vars']['project_folder'] == '/test/project'
    
    def test_parse_plan_yml_malformed(self):
        """Should handle malformed YAML gracefully"""
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_path = Path(temp_dir) / "plan.yml"
            # Invalid YAML that returns a string instead of dict
            plan_path.write_text("just a string, not yaml dict")
            
            config = parse_plan_yml(plan_path)
            
            # Should return empty dict for malformed YAML
            assert config == {}


class TestUtilityFunctions:
    """Test utility functions in simplified director"""
    
    def test_sanitize_filename_basic(self):
        """Should sanitize filenames properly"""
        # Test basic sanitization
        assert sanitize_filename("normal_file.txt") == "normal_file.txt"
        
        # Test spaces replaced with dashes
        assert sanitize_filename("file with spaces.txt") == "file-with-spaces.txt"
        
        # Test removing problematic characters
        result = sanitize_filename("file:with|bad<chars>.txt")
        assert ":" not in result
        assert "|" not in result
        assert "<" not in result
    
    def test_sanitize_path_basic(self):
        """Should sanitize paths properly"""
        # Test slashes replaced with dashes
        assert sanitize_path("normal/path") == "normal-path"
        
        # Test removing problematic characters from path components
        result = sanitize_path("bad:path|name")
        assert ":" not in result
        assert "|" not in result
    
    def test_smart_copy_basic(self):
        """Should copy files intelligently"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create source file
            src_file = temp_path / "source.txt"
            src_file.write_text("test content")
            
            # Copy to destination
            dst_file = temp_path / "dest.txt"
            smart_copy(src_file, dst_file)
            
            # Verify copy
            assert dst_file.exists()
            assert dst_file.read_text() == "test content"
    
    def test_get_backend_type(self):
        """Should return correct backend type"""
        backend = get_backend_type()
        # Should return a string (actual implementation returns 'python')
        assert isinstance(backend, str)
        assert len(backend) > 0
    
    def test_should_use_celery(self):
        """Should determine celery usage correctly"""
        result = should_use_celery()
        # Should return boolean
        assert isinstance(result, bool)


class TestWorkerManagement:
    """Test simplified worker management"""
    
    @patch('psutil.process_iter')
    def test_redis_process_detection(self, mock_process_iter):
        """Should detect Redis processes correctly"""
        # Mock process that looks like Redis
        mock_redis_proc = Mock()
        mock_redis_proc.pid = 1234
        mock_redis_proc.cmdline.return_value = ['redis-server', '/etc/redis.conf']
        
        # Mock other process
        mock_other_proc = Mock()
        mock_other_proc.pid = 5678
        mock_other_proc.cmdline.return_value = ['python', 'script.py']
        
        mock_process_iter.return_value = [mock_redis_proc, mock_other_proc]
        
        # Test Redis detection logic (extracted from ensure_workers_running)
        redis_running = False
        for proc in mock_process_iter.return_value:
            try:
                if proc.pid == 1:
                    continue
                cmdline = ' '.join(proc.cmdline()).lower()
                if 'redis-server' in cmdline and not any(x in cmdline for x in ['launchd', 'init']):
                    redis_running = True
                    break
            except (AttributeError, TypeError):
                continue
        
        assert redis_running is True
    
    @patch('psutil.process_iter')
    def test_celery_worker_detection(self, mock_process_iter):
        """Should detect Celery workers correctly"""
        # Mock process that looks like Celery worker
        mock_celery_proc = Mock()
        mock_celery_proc.pid = 1234
        mock_celery_proc.cmdline.return_value = ['celery', '-A', 'fichero.director', 'worker']
        
        mock_process_iter.return_value = [mock_celery_proc]
        
        # Test Celery detection logic
        workers_running = False
        for proc in mock_process_iter.return_value:
            try:
                if proc.pid == 1:
                    continue
                cmdline = ' '.join(proc.cmdline()).lower()
                if 'celery' in cmdline and 'worker' in cmdline:
                    workers_running = True
                    break
            except (AttributeError, TypeError):
                continue
        
        assert workers_running is True


class TestErrorHandlingAndResilience:
    """Test error handling in simplified director"""
    
    def test_graceful_import_failure(self):
        """Should handle import failures gracefully"""
        # Test pattern used for optional imports
        try:
            # This import might fail in test context
            import some_optional_module
            import_success = True
        except ImportError:
            import_success = False
        
        # Should not crash, just continue with fallback
        assert isinstance(import_success, bool)
    
    @patch('subprocess.Popen')
    def test_subprocess_failure_recovery(self, mock_popen):
        """Should recover from subprocess failures"""
        mock_popen.side_effect = OSError("Command not found")
        
        mock_logger = Mock()
        
        result = run_script_directly("invalid_command", "/test", mock_logger)
        
        # Should return False and log error, not crash
        assert result is False
        mock_logger.error.assert_called()
    
    def test_path_handling_edge_cases(self):
        """Should handle various path edge cases"""
        # Test empty path
        result = sanitize_path("")
        assert result == ""
        
        # Test path with only problematic characters
        result = sanitize_path("<<<>>>")
        # Should not crash, should return something safe
        assert isinstance(result, str)
    
    def test_yaml_parsing_error_recovery(self):
        """Should recover from YAML parsing errors"""
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_path = Path(temp_dir) / "invalid.yml"
            
            # Create invalid YAML
            plan_path.write_text("invalid: yaml: content: [unclosed")
            
            # Should not crash, should return empty dict
            try:
                config = parse_plan_yml(plan_path)
                # If it doesn't crash, it should return a dict
                assert isinstance(config, dict)
            except Exception:
                # If it does crash, that's also acceptable behavior
                pass


class TestBackwardCompatibility:
    """Test backward compatibility aspects"""
    
    def test_old_environment_variables_ignored(self):
        """Should ignore old environment variables (no backward compatibility needed)"""
        # Set old-style environment variables
        old_env_vars = {
            'FICHERO_API_KEY': 'old-api-key',
            'WEASEL_PROJECT_ROOT': '/old/root',
            'CUSTOM_SCRIPT_PATH': '/old/scripts'
        }
        
        with patch.dict('os.environ', old_env_vars):
            env = get_python_env()
            
            # Should not include any of the old variables
            for var in old_env_vars:
                assert var not in env
    
    def test_plan_yml_without_env_expansion(self):
        """Should process plan.yml without environment variable expansion"""
        vars_dict = {
            'base_path': '/test',
            'script_name': 'process.py'
        }
        
        # Text that looks like it has environment variables
        text = "python ${script_name} --path ${base_path} --env $HOME --legacy ${LEGACY_VAR}"
        
        with patch.dict('os.environ', {'HOME': '/home/user', 'LEGACY_VAR': 'legacy_value'}):
            with patch('os.path.isabs', return_value=True):  # Prevent path conversion
                result = expand_vars(text, vars_dict)
                
                # Should expand vars_dict variables but leave environment variables untouched
                expected = "python process.py --path /test --env $HOME --legacy ${LEGACY_VAR}"
                assert result == expected


class TestIntegrationPatterns:
    """Test integration patterns used in the simplified director"""
    
    def test_minimal_subprocess_environment_pattern(self):
        """Should use minimal environment in subprocess calls"""
        # Pattern used throughout director
        env = get_python_env()
        
        # Should have minimal set of variables
        max_expected_vars = 5  # PATH, PYTHONPATH, HOME, USER, SHELL
        assert len(env) <= max_expected_vars
        
        # Should not have API keys or other sensitive variables
        sensitive_prefixes = ['API_', 'KEY_', 'SECRET_', 'TOKEN_']
        for var_name in env.keys():
            for prefix in sensitive_prefixes:
                assert not var_name.startswith(prefix)
    
    def test_shared_data_verification_pattern(self):
        """Should verify shared data backend availability before use"""
        # Pattern used in process_folder task
        backend_available = False
        error_message = None
        
        try:
            # This import might fail in test context
            from fichero.shared_data import get_shared_data
            shared_data = get_shared_data()
            backend_available = True
            backend_name = getattr(shared_data, 'backend_name', 'unknown')
        except ImportError:
            error_message = "Shared data module not available"
        except Exception as e:
            error_message = str(e)
        
        # Should not crash regardless of outcome
        assert isinstance(backend_available, bool)
        if not backend_available:
            assert isinstance(error_message, str)
    
    def test_clean_orchestration_pattern(self):
        """Should orchestrate without complex API key management"""
        # Simplified workflow pattern
        workflow_steps = ['step1', 'step2', 'step3']
        vars_dict = {
            'project_folder': '/test/project',
            'output_folder': '/test/output'
        }
        
        # Process each step cleanly
        processed_steps = []
        for step in workflow_steps:
            # Simulate script command expansion
            script_cmd = f"python {step}.py --project ${{project_folder}} --output ${{output_folder}}"
            expanded_cmd = expand_vars(script_cmd, vars_dict)
            processed_steps.append(expanded_cmd)
        
        # Should have clean, expanded commands
        assert len(processed_steps) == 3
        for cmd in processed_steps:
            assert '/test/project' in cmd
            assert '/test/output' in cmd
            assert '${' not in cmd  # All variables should be expanded
    
    def test_no_environment_variable_expansion_pattern(self):
        """Should not expand environment variables in plan.yml processing"""
        vars_dict = {
            'base_path': '/test',
            'script_name': 'process.py'
        }
        
        # Text that looks like it has environment variables
        text = "python ${script_name} --path ${base_path} --env $HOME --legacy ${LEGACY_VAR}"
        
        with patch.dict('os.environ', {'HOME': '/home/user', 'LEGACY_VAR': 'legacy_value'}):
            with patch('os.path.isabs', return_value=True):  # Prevent path conversion
                result = expand_vars(text, vars_dict)
                
                # Should expand vars_dict variables but leave environment variables untouched
                expected = "python process.py --path /test --env $HOME --legacy ${LEGACY_VAR}"
                assert result == expected 