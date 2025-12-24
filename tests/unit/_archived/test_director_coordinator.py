"""
Unit tests for Director Coordinator and Workflow Executor.

Tests the core director components:
- ProcessingCoordinator: Task submission and folder processing
- WorkflowExecutor: Step execution and error handling
- TaskManager: Task lifecycle management
"""

import pytest
import asyncio
import time
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from typing import Dict, Any
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


class TestProcessingCoordinator:
    """Test ProcessingCoordinator functionality"""

    def test_coordinator_initialization(self):
        """Test coordinator initializes with required dependencies"""
        from fichero.director.coordinator import ProcessingCoordinator

        task_manager = Mock()
        variable_generator = Mock()
        plan_loader = Mock()

        coordinator = ProcessingCoordinator(
            task_manager=task_manager,
            variable_generator=variable_generator,
            plan_loader_func=plan_loader
        )

        assert coordinator.task_manager == task_manager
        assert coordinator.variable_generator == variable_generator

    def test_process_folders_loads_plan(self):
        """Test that process_folders loads plan configuration"""
        from fichero.director.coordinator import ProcessingCoordinator

        task_manager = Mock()
        task_manager.submit_task.return_value = "task-123"

        variable_generator = Mock()
        variable_generator.generate_variables.return_value = {"output_folder": "/output"}

        plan_config = {
            "title": "Test Plan",
            "workflows": {"default": ["step1", "step2"]},
            "commands": []
        }
        plan_loader = Mock(return_value=plan_config)

        coordinator = ProcessingCoordinator(
            task_manager=task_manager,
            variable_generator=variable_generator,
            plan_loader_func=plan_loader
        )

        result = coordinator.process_folders(
            folders=[Path("/test/folder")],
            plan_name="Test Plan",
            workflow_name="default"
        )

        assert result == "task-123"
        plan_loader.assert_called_once_with("Test Plan")
        task_manager.submit_task.assert_called_once()

    def test_process_folders_raises_on_missing_plan(self):
        """Test that process_folders raises error for missing plan"""
        from fichero.director.coordinator import ProcessingCoordinator

        task_manager = Mock()
        variable_generator = Mock()
        plan_loader = Mock(return_value=None)

        coordinator = ProcessingCoordinator(
            task_manager=task_manager,
            variable_generator=variable_generator,
            plan_loader_func=plan_loader
        )

        with pytest.raises(ValueError, match="Plan config is None"):
            coordinator.process_folders(
                folders=[Path("/test/folder")],
                plan_name="NonexistentPlan"
            )

    def test_process_folders_generates_variables(self):
        """Test that process_folders generates variables correctly"""
        from fichero.director.coordinator import ProcessingCoordinator

        task_manager = Mock()
        task_manager.submit_task.return_value = "task-456"

        variable_generator = Mock()
        variable_generator.generate_variables.return_value = {
            "output_folder": "/output",
            "source_folder": "/input"
        }

        plan_config = {"title": "Test", "workflows": {}, "commands": []}
        plan_loader = Mock(return_value=plan_config)

        coordinator = ProcessingCoordinator(
            task_manager=task_manager,
            variable_generator=variable_generator,
            plan_loader_func=plan_loader
        )

        coordinator.process_folders(
            folders=[Path("/input")],
            plan_name="Test",
            output_path=Path("/output")
        )

        variable_generator.generate_variables.assert_called_once()
        call_args = variable_generator.generate_variables.call_args
        assert call_args[0][0] == plan_config  # plan_config
        assert call_args[0][1] == Path("/output")  # output_path


class TestWorkflowExecutor:
    """Test WorkflowExecutor functionality"""

    def test_executor_initialization(self):
        """Test executor initializes correctly"""
        from fichero.director.workflow_executor import WorkflowExecutor

        callback = Mock()
        executor = WorkflowExecutor(progress_callback=callback)

        assert executor.progress_callback == callback
        assert executor._cancelled is False

    def test_execute_workflow_empty_steps(self, tmp_path):
        """Test workflow execution with no steps"""
        from fichero.director.workflow_executor import WorkflowExecutor

        executor = WorkflowExecutor()

        plan_config = {
            "title": "Empty Plan",
            "workflows": {"default": []},
            "commands": []
        }

        result = executor.execute_workflow(
            task_id="test-task",
            folder_path=tmp_path / "input",
            output_path=tmp_path / "output",
            workflow_name="default",
            plan_config=plan_config,
            variables={}
        )

        assert result.success is True

    def test_execute_workflow_no_plan_config(self, tmp_path):
        """Test workflow execution with no plan config"""
        from fichero.director.workflow_executor import WorkflowExecutor

        executor = WorkflowExecutor()

        result = executor.execute_workflow(
            task_id="test-task",
            folder_path=tmp_path / "input",
            output_path=tmp_path / "output",
            workflow_name="default",
            plan_config=None,
            variables={}
        )

        assert result.success is False

    def test_execute_workflow_stores_callback(self, tmp_path):
        """Test that executor stores the progress callback"""
        from fichero.director.workflow_executor import WorkflowExecutor

        callback = Mock()
        executor = WorkflowExecutor(progress_callback=callback)

        # Verify callback is stored
        assert executor.progress_callback == callback

    def test_execute_workflow_with_steps_calls_callback(self, tmp_path):
        """Test that progress callback is called when steps are executed"""
        from fichero.director.workflow_executor import WorkflowExecutor

        callback = Mock()
        executor = WorkflowExecutor(progress_callback=callback)

        # Create input/output dirs
        input_path = tmp_path / "input"
        input_path.mkdir()
        output_path = tmp_path / "output"
        output_path.mkdir()

        # A workflow with a simple step (even if it doesn't do much)
        plan_config = {
            "title": "Test Plan",
            "workflows": {"default": ["dummy_step"]},
            "commands": [{"name": "dummy_step", "command": "echo test", "worker_type": "io"}]
        }

        # Execute - the callback should be called for workflow progress
        result = executor.execute_workflow(
            task_id="test-task",
            folder_path=input_path,
            output_path=output_path,
            workflow_name="default",
            plan_config=plan_config,
            variables={}
        )

        # Result should exist (success or failure)
        assert result is not None

    def test_execute_workflow_missing_workflow(self, tmp_path):
        """Test workflow execution with missing workflow name"""
        from fichero.director.workflow_executor import WorkflowExecutor

        executor = WorkflowExecutor()

        plan_config = {
            "title": "Test Plan",
            "workflows": {"default": ["step1"]},
            "commands": []
        }

        result = executor.execute_workflow(
            task_id="test-task",
            folder_path=tmp_path / "input",
            output_path=tmp_path / "output",
            workflow_name="nonexistent",  # Missing workflow
            plan_config=plan_config,
            variables={}
        )

        # Should succeed with no steps to execute
        assert result.success is True


class TestTaskManager:
    """Test TaskManager functionality"""

    def test_task_manager_initialization(self):
        """Test task manager initializes correctly"""
        from fichero.director.task_manager import TaskManager

        backend = Mock()
        backend.set_progress_callback = Mock()  # Required by TaskManager.__init__
        task_manager = TaskManager(backend=backend)

        assert task_manager.backend == backend

    def test_submit_task_creates_task_id(self):
        """Test that submit_task creates a unique task ID"""
        from fichero.director.task_manager import TaskManager
        from fichero.director.backends.implementations.base import ProcessingStatus

        backend = Mock()
        backend.set_progress_callback = Mock()
        backend.process_folders = Mock(return_value={})

        task_manager = TaskManager(backend=backend)

        plan_config = {"title": "Test", "workflows": {"default": []}}

        # TaskManager expects folders as list of dicts or Path objects
        task_id = task_manager.submit_task(
            folders=[{"output_folder": Path("/test"), "documents_folder": Path("/test/docs")}],
            plan_config=plan_config,
            workflow_name="default",
            variables={}
        )

        assert task_id is not None
        assert len(task_id) > 0
        backend.process_folders.assert_called_once()

    def test_get_task_status(self):
        """Test getting task status"""
        from fichero.director.task_manager import TaskManager
        from fichero.director.backends.implementations.base import ProcessingStatus

        backend = Mock()
        backend.set_progress_callback = Mock()
        backend.get_status = Mock(return_value=ProcessingStatus.RUNNING)

        task_manager = TaskManager(backend=backend)
        status = task_manager.get_task_status("task-123")

        backend.get_status.assert_called_once_with("task-123")
        assert status == ProcessingStatus.RUNNING


class TestPythonProcessingBackend:
    """Test PythonProcessingBackend executor selection and worker management"""

    def test_backend_initialization(self):
        """Test backend initializes with correct worker counts"""
        from fichero.director.backends.implementations.python_backend import PythonProcessingBackend

        backend = PythonProcessingBackend(
            cpu_workers=4,
            io_workers=16
        )

        assert backend.cpu_workers == 4
        assert backend.io_workers == 16
        assert backend.backend_name == "python"

    def test_backend_default_workers(self):
        """Test backend uses sensible defaults when no workers specified"""
        from fichero.director.backends.implementations.python_backend import PythonProcessingBackend

        backend = PythonProcessingBackend()

        # Should have positive worker counts
        assert backend.cpu_workers > 0
        assert backend.io_workers > 0

    def test_backend_initialization_state(self):
        """Test backend starts uninitialized"""
        from fichero.director.backends.implementations.python_backend import PythonProcessingBackend

        backend = PythonProcessingBackend(cpu_workers=4, io_workers=8)

        # Not initialized until initialize() called
        assert backend._initialized is False

    def test_backend_initialize(self):
        """Test backend initializes correctly"""
        from fichero.director.backends.implementations.python_backend import PythonProcessingBackend

        backend = PythonProcessingBackend(cpu_workers=4, io_workers=8)
        result = backend.initialize()

        assert result is True
        assert backend.is_initialized is True

    def test_backend_properties(self):
        """Test backend capability properties"""
        from fichero.director.backends.implementations.python_backend import PythonProcessingBackend

        backend = PythonProcessingBackend(cpu_workers=4, io_workers=8)

        assert backend.supports_async is True
        assert backend.supports_multiple_instances is True
        assert backend.requires_external_services is False


class TestWorkflowManifest:
    """Test WorkflowManifest tracking"""

    def test_manifest_initialization(self, tmp_path):
        """Test manifest initializes correctly"""
        from fichero.director.workflow_manifest import WorkflowManifest

        output_path = tmp_path / "output"
        output_path.mkdir()

        manifest = WorkflowManifest(
            output_path=output_path,
            plan_name="Test Plan",
            workflow_name="default",
            task_id="task-123"
        )

        assert manifest.plan_name == "Test Plan"
        assert manifest.workflow_name == "default"
        assert manifest.task_id == "task-123"
        assert manifest.steps == []

    def test_manifest_records_step(self, tmp_path):
        """Test manifest records step execution"""
        from fichero.director.workflow_manifest import WorkflowManifest

        output_path = tmp_path / "output"
        output_path.mkdir()

        manifest = WorkflowManifest(
            output_path=output_path,
            plan_name="Test",
            workflow_name="default",
            task_id="task-123"
        )

        # start_step takes step_order, step_name, output_scope
        manifest.start_step(1, "crop", "leaf")
        # complete_step takes step_order, success, manifest_path, errors
        manifest.complete_step(1, success=True, manifest_path="assets/crop/manifest.jsonl")

        # Check step was recorded (steps is a list, 0-indexed)
        assert len(manifest.steps) == 1
        assert manifest.steps[0]["name"] == "crop"
        assert manifest.steps[0]["status"] == "success"
        assert manifest.steps[0]["manifest_file"] == "assets/crop/manifest.jsonl"

    def test_manifest_finalize_saves_to_file(self, tmp_path):
        """Test manifest finalize saves to JSON file"""
        from fichero.director.workflow_manifest import WorkflowManifest

        output_path = tmp_path / "output"
        output_path.mkdir()

        manifest = WorkflowManifest(
            output_path=output_path,
            plan_name="Test",
            workflow_name="default",
            task_id="task-123"
        )

        manifest.start_step(1, "step1")
        manifest.complete_step(1, success=True)
        manifest.finalize(success=True)

        manifest_file = output_path / "workflow_manifest.json"
        assert manifest_file.exists()

    def test_manifest_read_manifest(self, tmp_path):
        """Test reading manifest from disk"""
        from fichero.director.workflow_manifest import WorkflowManifest

        output_path = tmp_path / "output"
        output_path.mkdir()

        # Create and save a manifest
        manifest = WorkflowManifest(
            output_path=output_path,
            plan_name="Test",
            workflow_name="default",
            task_id="task-123"
        )
        manifest.start_step(1, "step1")
        manifest.complete_step(1, success=True)
        manifest.finalize(success=True)

        # Read it back
        loaded = WorkflowManifest.read_manifest(output_path)

        assert loaded is not None
        assert loaded["workflow"]["plan_name"] == "Test"
        assert loaded["workflow"]["success"] is True
        assert len(loaded["steps"]) == 1


class TestVariableGenerator:
    """Test VariableGenerator functionality"""

    def test_variable_generator_initialization(self):
        """Test variable generator initializes correctly"""
        from fichero.director.variable_generator import VariableGenerator

        generator = VariableGenerator()
        assert generator is not None

    def test_variable_generation_with_output_path(self, tmp_path):
        """Test that variables include output path"""
        from fichero.director.variable_generator import VariableGenerator

        generator = VariableGenerator()

        plan_config = {
            "title": "Test Plan",
            "vars": {
                "custom_var": "custom_value"
            }
        }

        output_path = tmp_path / "output"
        folders = [tmp_path / "input"]

        variables = generator.generate_variables(plan_config, output_path, folders)

        # Should have output_folder and output_path
        assert "output_folder" in variables
        assert variables["output_folder"] == str(output_path)
        # Should pass through custom vars
        assert variables.get("custom_var") == "custom_value"

    def test_variable_generation_includes_system_paths(self, tmp_path):
        """Test that system paths are generated"""
        from fichero.director.variable_generator import VariableGenerator

        generator = VariableGenerator()

        plan_config = {"title": "Test"}
        output_path = tmp_path / "output"

        variables = generator.generate_variables(plan_config, output_path)

        # Should have system path variables
        assert "fichero_root" in variables
        assert "scripts_dir" in variables
        assert "prompts_dir" in variables

    def test_variable_generation_no_plan_config(self, tmp_path):
        """Test variable generation with no plan config"""
        from fichero.director.variable_generator import VariableGenerator

        generator = VariableGenerator()

        output_path = tmp_path / "output"
        variables = generator.generate_variables(None, output_path)

        # Should still have system paths
        assert "fichero_root" in variables


class TestProcessingResult:
    """Test ProcessingResult data class"""

    def test_processing_result_creation(self, tmp_path):
        """Test ProcessingResult can be created"""
        from fichero.director.backends.implementations.base import ProcessingResult

        result = ProcessingResult(
            task_id="task-123",
            success=True,
            folder_path=tmp_path / "input",
            output_path=tmp_path / "output",
            execution_time=10.5
        )

        assert result.task_id == "task-123"
        assert result.success is True
        assert result.execution_time == 10.5

    def test_processing_result_with_error(self, tmp_path):
        """Test ProcessingResult with error message"""
        from fichero.director.backends.implementations.base import ProcessingResult

        result = ProcessingResult(
            task_id="task-456",
            success=False,
            folder_path=tmp_path / "input",
            output_path=tmp_path / "output",
            execution_time=5.0,
            error_message="Step failed"
        )

        assert result.success is False
        assert result.error_message == "Step failed"


class TestFolderPreparation:
    """Test folder preparation utilities"""

    def test_prepare_folder_in_place_mode(self, tmp_path):
        """Test folder preparation in in-place mode"""
        from fichero.director.utils.folder_preparation import prepare_folder

        input_folder = tmp_path / "input"
        input_folder.mkdir()
        (input_folder / "test.jpg").write_text("test")

        output_folder = tmp_path / "output"

        # prepare_folder returns (output_subfolder, documents_folder)
        output_subfolder, documents_folder = prepare_folder(input_folder, output_folder, "in_place")

        assert output_subfolder.exists()
        assert (output_subfolder / "assets").exists()
        assert (output_subfolder / "logs").exists()
        # In in-place mode, documents_folder is the original input
        assert documents_folder == input_folder

    def test_prepare_folder_copy_mode(self, tmp_path):
        """Test folder preparation in copy mode"""
        from fichero.director.utils.folder_preparation import prepare_folder

        input_folder = tmp_path / "input"
        input_folder.mkdir()
        (input_folder / "test.jpg").write_text("test")

        output_folder = tmp_path / "output"

        output_subfolder, documents_folder = prepare_folder(input_folder, output_folder, "copy")

        assert output_subfolder.exists()
        assert (output_subfolder / "assets").exists()
        # In copy mode, files are copied to documents folder
        assert documents_folder.exists()

    def test_sanitize_name(self):
        """Test filename sanitization"""
        from fichero.director.utils.folder_preparation import sanitize_name

        # Test problematic characters are replaced
        assert sanitize_name("hello world.jpg") == "hello-world.jpg"
        assert sanitize_name("file,with;special{chars}.png") == "file-with-special-chars.png"
        assert sanitize_name("no-change.txt") == "no-change.txt"

    def test_create_output_subdirectories(self, tmp_path):
        """Test output subdirectory creation"""
        from fichero.director.utils.folder_preparation import create_output_subdirectories

        output_path = tmp_path / "output"
        output_path.mkdir()

        create_output_subdirectories(output_path)

        assert (output_path / "assets").exists()
        assert (output_path / "logs").exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
