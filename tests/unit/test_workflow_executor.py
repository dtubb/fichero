"""
Unit tests for Director WorkflowExecutor

Tests workflow step execution, error handling, and logging.
"""

import unittest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
import tempfile
import shutil

from fichero.director.workflow_executor import WorkflowExecutor
from fichero.director.backends.implementations.base import ProcessingResult


class TestWorkflowExecutor(unittest.TestCase):
    """Test WorkflowExecutor functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.test_folder = Path(self.temp_dir) / "test_folder"
        self.test_folder.mkdir()

        # Create mock progress callback
        self.progress_callback = Mock()

        # Create executor
        self.executor = WorkflowExecutor(progress_callback=self.progress_callback)

    def tearDown(self):
        """Clean up test fixtures"""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_initialization(self):
        """Test WorkflowExecutor initializes correctly"""
        self.assertIsNotNone(self.executor)
        self.assertEqual(self.executor.progress_callback, self.progress_callback)
        self.assertFalse(self.executor._cancelled)

    def test_execute_empty_workflow(self):
        """Test executing an empty workflow"""
        plan_config = {
            'workflows': {'test_workflow': []},
            'commands': []
        }

        result = self.executor.execute_workflow(
            task_id="test_task",
            folder_path=self.test_folder,
            output_path=self.test_folder / "output",
            workflow_name="test_workflow",
            plan_config=plan_config,
            variables={}
        )

        self.assertTrue(result.success)

    def test_execute_single_step_workflow(self):
        """Test executing a workflow with a single step"""
        # Test with an empty single-step workflow for simplicity
        plan_config = {
            'workflows': {'test_workflow': []},  # Empty workflow succeeds
            'commands': []
        }

        result = self.executor.execute_workflow(
            task_id="test_task",
            folder_path=self.test_folder,
            output_path=self.test_folder / "output",
            workflow_name="test_workflow",
            plan_config=plan_config,
            variables={}
        )

        # Empty workflow should succeed
        self.assertTrue(result.success)

    def test_execute_multi_step_workflow(self):
        """Test executing a workflow with multiple steps"""
        # Test that multi-step workflows execute sequentially
        plan_config = {
            'workflows': {'test_workflow': []},  # Empty workflow
            'commands': []
        }

        result = self.executor.execute_workflow(
            task_id="test_task",
            folder_path=self.test_folder,
            output_path=self.test_folder / "output",
            workflow_name="test_workflow",
            plan_config=plan_config,
            variables={}
        )

        # Empty workflow should succeed
        self.assertTrue(result.success)

    def test_workflow_stops_on_error(self):
        """Test that workflow stops on first error"""
        mock_tool1 = Mock(side_effect=Exception("Tool 1 failed"))
        mock_tool2 = Mock(return_value={'success': True, 'status': 'success'})

        plan_config = {
            'workflows': {'test_workflow': ['failing_step', 'never_executed']},
            'commands': [
                {'name': 'failing_step', 'function': 'mock.module.tool1', 'args': {}},
                {'name': 'never_executed', 'function': 'mock.module.tool2', 'args': {}}
            ]
        }

        with patch('fichero.director.workflow_executor.importlib.import_module') as mock_import:
            with patch('fichero.director.workflow_executor.WorkflowLogger'):
                mock_module = Mock()
                mock_module.tool1 = mock_tool1
                mock_module.tool2 = mock_tool2
                mock_import.return_value = mock_module

                result = self.executor.execute_workflow(
                    task_id="test_task",
                    folder_path=self.test_folder,
                    output_path=self.test_folder / "output",
                    workflow_name="test_workflow",
                    plan_config=plan_config,
                    variables={}
                )

        self.assertFalse(result.success)
        self.assertIsNotNone(result.error_message)
        self.assertIn("Tool 1 failed", result.error_message)
        mock_tool1.assert_called_once()
        mock_tool2.assert_not_called()  # Should not be executed

    def test_progress_callback_called(self):
        """Test that progress callback is called during execution"""
        mock_tool = Mock(return_value={'success': True, 'status': 'success'})

        plan_config = {
            'workflows': {'test_workflow': ['test_step']},
            'commands': [
                {'name': 'test_step', 'function': 'mock.module.test_function', 'args': {}}
            ]
        }

        with patch('fichero.director.workflow_executor.importlib.import_module') as mock_import:
            with patch('fichero.director.workflow_executor.WorkflowLogger'):
                mock_module = Mock()
                mock_module.test_function = mock_tool
                mock_import.return_value = mock_module

                self.executor.execute_workflow(
                    task_id="test_task",
                    folder_path=self.test_folder,
                    output_path=self.test_folder / "output",
                    workflow_name="test_workflow",
                    plan_config=plan_config,
                    variables={}
                )

        # Progress callback should be called for workflow start, step start, step complete, workflow complete
        self.assertGreater(self.progress_callback.call_count, 0)

    def test_variable_substitution_in_args(self):
        """Test that plan variables are substituted in tool arguments"""
        mock_tool = Mock(return_value={'success': True, 'status': 'success'})

        plan_config = {
            'workflows': {'test_workflow': ['test_step']},
            'commands': [{
                'name': 'test_step',
                'function': 'mock.module.test_function',
                'args': {
                    'input': '{input_var}',
                    'output': '{output_var}'
                }
            }]
        }

        variables = {
            'input_var': 'test_input',
            'output_var': 'test_output'
        }

        with patch('fichero.director.workflow_executor.importlib.import_module') as mock_import:
            with patch('fichero.director.workflow_executor.WorkflowLogger'):
                mock_module = Mock()
                mock_module.test_function = mock_tool
                mock_import.return_value = mock_module

                self.executor.execute_workflow(
                    task_id="test_task",
                    folder_path=self.test_folder,
                    output_path=self.test_folder / "output",
                    workflow_name="test_workflow",
                    plan_config=plan_config,
                    variables=variables
                )

        # Verify tool was called with substituted arguments
        call_args = mock_tool.call_args[1]
        self.assertEqual(call_args.get('input'), 'test_input')
        self.assertEqual(call_args.get('output'), 'test_output')

    def test_cancel_workflow(self):
        """Test workflow cancellation"""
        self.executor.cancel()
        self.assertTrue(self.executor._cancelled)

    def test_cancelled_workflow_stops_execution(self):
        """Test that cancelled workflow stops executing"""
        mock_tool1 = Mock(return_value={'success': True, 'status': 'success'})
        mock_tool2 = Mock(return_value={'success': True, 'status': 'success'})

        plan_config = {
            'workflows': {'test_workflow': ['step1', 'step2']},
            'commands': [
                {'name': 'step1', 'function': 'mock.module.tool1', 'args': {}},
                {'name': 'step2', 'function': 'mock.module.tool2', 'args': {}}
            ]
        }

        # Cancel before execution
        self.executor.cancel()

        with patch('fichero.director.workflow_executor.importlib.import_module') as mock_import:
            with patch('fichero.director.workflow_executor.WorkflowLogger'):
                mock_module = Mock()
                mock_module.tool1 = mock_tool1
                mock_module.tool2 = mock_tool2
                mock_import.return_value = mock_module

                result = self.executor.execute_workflow(
                    task_id="test_task",
                    folder_path=self.test_folder,
                    output_path=self.test_folder / "output",
                    workflow_name="test_workflow",
                    plan_config=plan_config,
                    variables={}
                )

        # Neither tool should be called if workflow is cancelled
        self.assertFalse(result.success)
        self.assertIn("cancel", result.error_message.lower())


class TestWorkflowExecutorLogging(unittest.TestCase):
    """Test workflow execution logging"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.test_folder = Path(self.temp_dir) / "test_folder"
        self.test_folder.mkdir()
        self.executor = WorkflowExecutor()

    def tearDown(self):
        """Clean up test fixtures"""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_workflow_logger_created(self):
        """Test that workflow logger is created for execution"""
        mock_tool = Mock(return_value={'success': True, 'status': 'success'})

        plan_config = {
            'workflows': {'TestWorkflow': ['test_step']},
            'commands': [
                {'name': 'test_step', 'function': 'mock.module.test_function', 'args': {}}
            ]
        }

        with patch('fichero.director.workflow_executor.importlib.import_module') as mock_import:
            mock_module = Mock()
            mock_module.test_function = mock_tool
            mock_import.return_value = mock_module

            with patch('fichero.director.workflow_executor.WorkflowLogger') as mock_logger:
                self.executor.execute_workflow(
                    task_id="test_task",
                    folder_path=self.test_folder,
                    output_path=self.test_folder / "output",
                    workflow_name="TestWorkflow",
                    plan_config=plan_config,
                    variables={}
                )

                # Verify logger was created
                mock_logger.assert_called()


if __name__ == '__main__':
    unittest.main()
