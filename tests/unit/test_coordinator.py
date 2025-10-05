"""
Unit tests for Director Coordinator

Tests end-to-end workflow orchestration and folder processing coordination.
"""

import unittest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import tempfile
import shutil

from fichero.director.coordinator import ProcessingCoordinator


class TestProcessingCoordinator(unittest.TestCase):
    """Test ProcessingCoordinator functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()

        # Create mock components
        self.mock_task_manager = Mock()
        self.mock_variable_generator = Mock()
        self.mock_plan_loader = Mock()

        # Create coordinator
        self.coordinator = ProcessingCoordinator(
            self.mock_task_manager,
            self.mock_variable_generator,
            self.mock_plan_loader
        )

    def tearDown(self):
        """Clean up test fixtures"""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_initialization(self):
        """Test ProcessingCoordinator initializes correctly"""
        self.assertIsNotNone(self.coordinator)
        self.assertEqual(self.coordinator.task_manager, self.mock_task_manager)

    def test_process_folders_returns_task_id(self):
        """Test that process_folders returns a task ID"""
        folder1 = Path(self.temp_dir) / "folder1"
        folder1.mkdir()

        # Mock plan loader
        self.mock_plan_loader.return_value = {
            'workflows': {'test_workflow': []},
            'commands': []
        }

        # Mock variable generator
        self.mock_variable_generator.generate_variables.return_value = {}

        # Mock task manager
        self.mock_task_manager.submit_task.return_value = "task1"

        task_id = self.coordinator.process_folders(
            folders=[folder1],
            plan_name="Test Plan",
            workflow_name="test_workflow"
        )

        # Verify task ID returned
        self.assertEqual(task_id, "task1")

    def test_process_folders_with_multiple_folders(self):
        """Test processing with multiple folders"""
        folder1 = Path(self.temp_dir) / "folder1"
        folder2 = Path(self.temp_dir) / "folder2"
        folder1.mkdir()
        folder2.mkdir()

        # Mock plan loader
        self.mock_plan_loader.return_value = {
            'workflows': {'test_workflow': []},
            'commands': []
        }

        # Mock variable generator
        self.mock_variable_generator.generate_variables.return_value = {}

        # Mock task manager
        self.mock_task_manager.submit_task.return_value = "task1"

        task_id = self.coordinator.process_folders(
            folders=[folder1, folder2],
            plan_name="Test Plan",
            workflow_name="test_workflow"
        )

        # Verify task manager was called
        self.mock_task_manager.submit_task.assert_called_once()

        # Verify task ID returned
        self.assertEqual(task_id, "task1")

    def test_process_folders_with_valid_plan(self):
        """Test that processing with valid plan works"""
        folder1 = Path(self.temp_dir) / "folder1"
        folder1.mkdir()

        # Mock plan loader
        self.mock_plan_loader.return_value = {
            'workflows': {'test_workflow': []},
            'commands': []
        }

        # Mock variable generator
        self.mock_variable_generator.generate_variables.return_value = {}

        # Mock task manager
        self.mock_task_manager.submit_task.return_value = "task1"

        task_id = self.coordinator.process_folders(
            folders=[folder1],
            plan_name="Valid Plan",
            workflow_name="test_workflow"
        )

        # Should return task ID
        self.assertEqual(task_id, "task1")

    def test_process_folders_calls_variable_generator(self):
        """Test that variable generator is called correctly"""
        folder1 = Path(self.temp_dir) / "folder1"
        folder1.mkdir()

        # Mock plan loader
        plan_config = {
            'workflows': {'test_workflow': []},
            'commands': []
        }
        self.mock_plan_loader.return_value = plan_config

        # Mock variable generator
        self.mock_variable_generator.generate_variables.return_value = {'var1': 'value1'}

        # Mock task manager
        self.mock_task_manager.submit_task.return_value = "task1"

        self.coordinator.process_folders(
            folders=[folder1],
            plan_name="Test Plan",
            workflow_name="test_workflow"
        )

        # Verify variable generator was called
        self.mock_variable_generator.generate_variables.assert_called_once()

    def test_empty_folders_list(self):
        """Test handling of empty folders list"""
        # Mock plan loader
        self.mock_plan_loader.return_value = {
            'workflows': {'test_workflow': []},
            'commands': []
        }

        # Mock variable generator
        self.mock_variable_generator.generate_variables.return_value = {}

        # Mock task manager
        self.mock_task_manager.submit_task.return_value = "task1"

        task_id = self.coordinator.process_folders(
            folders=[],
            plan_name="Test Plan",
            workflow_name="test_workflow"
        )

        # Should still return a task ID
        self.assertEqual(task_id, "task1")


class TestProcessingCoordinatorIntegration(unittest.TestCase):
    """Test ProcessingCoordinator integration with other components"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()

        # Create mock components
        self.mock_task_manager = Mock()
        self.mock_variable_generator = Mock()
        self.mock_plan_loader = Mock()

        self.coordinator = ProcessingCoordinator(
            self.mock_task_manager,
            self.mock_variable_generator,
            self.mock_plan_loader
        )

    def tearDown(self):
        """Clean up test fixtures"""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_workflow_variables_passed_to_task_manager(self):
        """Test that workflow variables are correctly passed to task manager"""
        folder1 = Path(self.temp_dir) / "folder1"
        folder1.mkdir()

        # Mock plan loader
        plan_config = {
            'workflows': {'test_workflow': ['step1']},
            'commands': [{'name': 'step1', 'function': 'mock.tool', 'args': {}}]
        }
        self.mock_plan_loader.return_value = plan_config

        # Mock variable generator with variables
        variables = {
            'language': 'es',
            'project_folder': '/test/project'
        }
        self.mock_variable_generator.generate_variables.return_value = variables
        self.mock_task_manager.submit_task.return_value = "task1"

        self.coordinator.process_folders(
            folders=[folder1],
            plan_name="Test Plan",
            workflow_name="test_workflow"
        )

        # Verify task manager was called with variables
        call_args = self.mock_task_manager.submit_task.call_args
        self.assertIsNotNone(call_args)

        # Check that variables were passed
        args, kwargs = call_args
        self.assertEqual(kwargs.get('variables'), variables)


if __name__ == '__main__':
    unittest.main()
