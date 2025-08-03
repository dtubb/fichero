"""
Plan and Workflow UI Helper - Unified Interface

Provides a unified interface for plan and workflow selection across different UI contexts.
Handles both settings window (save_as_default=True) and document window (save_as_default=False).
"""

import logging
from typing import List, Optional, Dict, Any, Callable
from pathlib import Path

from fichero.config.core.plan_manager import PlanManager
from fichero.config.core.loader import ConfigLoader
from fichero.config.core.settings import get_app_settings

logger = logging.getLogger(__name__)

DEFAULT_PLAN_FILENAME = "Default.yml"


class PlanWorkflowUIHelper:
    """Unified helper for plan and workflow UI management"""
    
    def __init__(self, app):
        self.app = app
        self.settings = get_app_settings(app)
    
    def get_plan_options(self) -> List[str]:
        """Get list of available plan display names"""
        try:
            plan_display_names = []
            default_plans_dir, user_plans_dir = PlanManager._get_plan_directories(self.app)
            
            for plans_dir in [default_plans_dir, user_plans_dir]:
                if plans_dir and plans_dir.exists():
                    for ext in ConfigLoader.get_supported_extensions():
                        plan_files = list(plans_dir.glob(f"*{ext}"))
                        for plan_file in plan_files:
                            plan_data = ConfigLoader.load_config_file(plan_file)
                            if plan_data and 'title' in plan_data:
                                plan_display_names.append(plan_data['title'])
                            else:
                                plan_display_names.append(plan_file.stem)
            
            # Remove duplicates while preserving order
            seen = set()
            unique_plans = []
            for name in plan_display_names:
                if name not in seen:
                    seen.add(name)
                    unique_plans.append(name)
            
            return unique_plans
            
        except Exception as e:
            logger.error(f"Failed to get plan options: {e}")
            return []
    
    def get_plan_filename(self, plan_display_name: str) -> Optional[str]:
        """Get filename for a plan display name"""
        try:
            from fichero.config.core.plan_manager import PlanManager
            default_plans_dir, user_plans_dir = PlanManager._get_plan_directories(self.app)
            
            for plans_dir in [default_plans_dir, user_plans_dir]:
                if plans_dir and plans_dir.exists():
                    for ext in ConfigLoader.get_supported_extensions():
                        plan_files = list(plans_dir.glob(f"*{ext}"))
                        for plan_file in plan_files:
                            plan_data = ConfigLoader.load_config_file(plan_file)
                            if plan_data and 'title' in plan_data and plan_data['title'] == plan_display_name:
                                return plan_file.stem
                            elif plan_file.stem == plan_display_name:
                                return plan_file.stem
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get plan filename: {e}")
            return None
    
    def get_workflow_options(self, plan_filename: str) -> List[str]:
        """Get workflow options for a plan"""
        try:
            from fichero.config.core.plan_manager import PlanManager
            workflows = PlanManager.get_workflows_for_plan(plan_filename, self.app)
            
            if workflows and workflows[0] not in ["No workflows", "Plan file not found", "Error loading workflows"]:
                return workflows
            else:
                return []
                
        except Exception as e:
            logger.error(f"Failed to get workflow options: {e}")
            return []
    
    def get_app_default_plan(self) -> Optional[str]:
        """Get the app's default plan"""
        try:
            from fichero.config.core.plan_manager import PlanManager
            return PlanManager.get_default_plan(self.app)
        except Exception as e:
            logger.error(f"Failed to get app default plan: {e}")
            return None
    
    def get_app_default_workflow(self, plan_name: str) -> Optional[str]:
        """Get the app's default workflow for a plan"""
        try:
            from fichero.config.core.plan_manager import PlanManager
            return PlanManager.get_default_workflow(plan_name, self.app)
        except Exception as e:
            logger.error(f"Failed to get app default workflow: {e}")
            return None
    
    def set_app_default_plan(self, plan_name: str):
        """Set app-wide default plan in shared settings"""
        from fichero.config.core.plan_manager import PlanManager
        PlanManager.set_default_plan(plan_name, self.app)
        logger.info(f"Set app default plan: {plan_name}")
    
    def set_app_default_workflow(self, workflow_name: str):
        """Set app-wide default workflow in shared settings"""
        from fichero.config.core.plan_manager import PlanManager
        PlanManager.set_default_workflow(workflow_name, self.app)
        logger.info(f"Set app default workflow: {workflow_name}")
    
    # UI Helper Methods
    
    def populate_plan_dropdown(self, widget, current_value: str = None) -> str:
        """
        Populate plan dropdown widget with options and set value.
        Returns the value that was set.
        """
        plan_options = self.get_plan_options()
        
        if hasattr(widget, 'items'):
            widget.items = plan_options
            
            # Determine what value to set
            if current_value and current_value in plan_options:
                widget.value = current_value
                return current_value
            else:
                # Use app default or first available
                default_plan = self.get_app_default_plan()
                if default_plan and default_plan in plan_options:
                    widget.value = default_plan
                    return default_plan
                elif plan_options and plan_options[0] not in ["No plans found", "Error loading plans"]:
                    widget.value = plan_options[0]
                    return plan_options[0]
        
        return None
    
    def populate_workflow_dropdown(self, widget, plan_name: str, current_value: str = None, use_app_defaults: bool = True) -> str:
        """
        Populate workflow dropdown widget for given plan.
        Returns the value that was set.
        
        Args:
            widget: The dropdown widget to populate
            plan_name: Plan to get workflows for
            current_value: Current/preferred value to set
            use_app_defaults: Whether to use app defaults (False for document-specific)
        """
        if not plan_name:
            if hasattr(widget, 'items'):
                widget.items = ["Select a plan first"]
                widget.value = None
            logger.debug("Workflow dropdown cleared - no plan selected")
            return None
        
        workflow_options = self.get_workflow_options(plan_name)
        logger.debug(f"Got workflow options for plan '{plan_name}': {workflow_options}")
        
        if hasattr(widget, 'items'):
            if workflow_options and workflow_options[0] not in ["Select a plan first", "No workflows in plan"]:
                widget.items = workflow_options
                logger.debug(f"Set workflow dropdown items: {workflow_options}")
                
                # Determine what value to set - ensure it exists in the list
                if current_value and current_value in workflow_options:
                    widget.value = current_value
                    logger.debug(f"Set workflow to current value: {current_value}")
                    return current_value
                elif use_app_defaults:
                    # Use app default for this plan
                    default_workflow = self.get_app_default_workflow(plan_name)
                    if default_workflow and default_workflow in workflow_options:
                        widget.value = default_workflow
                        logger.debug(f"Set workflow to app default: {default_workflow}")
                        return default_workflow
                
                # Fall back to first available - ensure it exists
                if workflow_options:
                    first_workflow = workflow_options[0]
                    widget.value = first_workflow
                    logger.debug(f"Set workflow to first available: {first_workflow}")
                    return first_workflow
                else:
                    # No valid workflows, clear the selection
                    widget.value = None
                    logger.debug("No valid workflows available")
            else:
                widget.items = ["No workflows in plan"]
                widget.value = None
                logger.debug(f"No workflows found for plan '{plan_name}'")
        
        return None
    
    def handle_plan_change(self, plan_widget, workflow_widget, save_as_default: bool = False) -> Dict[str, str]:
        """
        Handle plan selection change - update workflow dropdown.
        
        Args:
            plan_widget: Plan selection widget
            workflow_widget: Workflow selection widget to update
            save_as_default: Whether to save selection as app default (Settings only)
            
        Returns:
            Dict with 'plan' and 'workflow' values that were set
        """
        try:
            plan_name = getattr(plan_widget, 'value', None)
            if not plan_name or plan_name in ["No plans found", "Error loading plans", "Manage Plans..."]:
                return {'plan': None, 'workflow': None}
            
            # Save as app default if requested (Settings window)
            if save_as_default:
                self.set_app_default_plan(plan_name)
            
            # Update workflow dropdown (use defaults for Settings, not for Document)
            workflow_name = self.populate_workflow_dropdown(
                workflow_widget, 
                plan_name, 
                use_app_defaults=save_as_default
            )
            
            logger.info(f"Plan changed to: {plan_name}, workflow: {workflow_name}")
            
            return {'plan': plan_name, 'workflow': workflow_name}
            
        except Exception as e:
            logger.error(f"Error handling plan change: {e}")
            return {'plan': None, 'workflow': None}
    
    def handle_workflow_change(self, workflow_widget, save_as_default: bool = False) -> Optional[str]:
        """
        Handle workflow selection change.
        
        Args:
            workflow_widget: Workflow selection widget
            save_as_default: Whether to save selection as app default (Settings only)
            
        Returns:
            The workflow name that was selected
        """
        try:
            workflow_name = getattr(workflow_widget, 'value', None)
            if not workflow_name or workflow_name in ["Select a plan first", "No workflows in plan"]:
                return None
            
            # Save as app default if requested (Settings window)
            if save_as_default:
                self.set_app_default_workflow(workflow_name)
            
            logger.info(f"Workflow {'default' if save_as_default else 'selection'} changed to: {workflow_name}")
            
            return workflow_name
            
        except Exception as e:
            logger.error(f"Error handling workflow change: {e}")
            return None
    
    # Initialization Helpers
    
    def initialize_settings_widgets(self, plan_widget, workflow_widget) -> Dict[str, str]:
        """
        Initialize Settings window widgets with app defaults.
        Both selections will be saved as new app defaults when changed.
        """
        try:
            # Load current app defaults
            current_plan = self.get_app_default_plan()
            current_workflow = self.get_app_default_workflow(current_plan) if current_plan else None
            
            # Populate plan dropdown with current default
            plan_name = self.populate_plan_dropdown(plan_widget, current_plan)
            
            # Populate workflow dropdown with current default
            workflow_name = self.populate_workflow_dropdown(
                workflow_widget, 
                plan_name, 
                current_workflow, 
                use_app_defaults=True
            )
            
            logger.info(f"Initialized Settings with plan: {plan_name}, workflow: {workflow_name}")
            
            return {'plan': plan_name, 'workflow': workflow_name}
            
        except Exception as e:
            logger.error(f"Error initializing Settings widgets: {e}")
            return {'plan': None, 'workflow': None}
    
    def initialize_document_widgets(self, plan_widget, workflow_widget) -> Dict[str, str]:
        """
        Initialize Document window widgets with app defaults.
        Selections will NOT be saved as app defaults (document-specific).
        """
        try:
            # Use app defaults to initialize, but don't save changes back
            default_plan = self.get_app_default_plan()
            default_workflow = self.get_app_default_workflow(default_plan) if default_plan else None
            
            # Populate plan dropdown with app default
            plan_name = self.populate_plan_dropdown(plan_widget, default_plan)
            
            # Populate workflow dropdown with app default
            workflow_name = self.populate_workflow_dropdown(
                workflow_widget, 
                plan_name, 
                default_workflow, 
                use_app_defaults=True  # Use for initialization, but won't save back
            )
            
            logger.info(f"Initialized Document with plan: {plan_name}, workflow: {workflow_name}")
            
            return {'plan': plan_name, 'workflow': workflow_name}
            
        except Exception as e:
            logger.error(f"Error initializing Document widgets: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # Set safe fallback values
            try:
                if hasattr(plan_widget, 'items'):
                    plan_widget.items = ["No plans found"]
                    plan_widget.value = None
                if hasattr(workflow_widget, 'items'):
                    workflow_widget.items = ["Select a plan first"]
                    workflow_widget.value = None
            except Exception as widget_error:
                logger.debug(f"Error setting fallback widget values: {widget_error}")
            
            return {'plan': None, 'workflow': None}
    
    # CLI Helper Methods
    
    def get_cli_defaults(self) -> Dict[str, str]:
        """Get defaults for CLI usage"""
        try:
            plan_name = self.get_app_default_plan()
            workflow_name = self.get_app_default_workflow(plan_name) if plan_name else None
            
            # Fallback logic if no defaults set
            if not plan_name:
                plan_options = self.get_plan_options()
                if plan_options and plan_options[0] not in ["No plans found", "Error loading plans"]:
                    plan_name = plan_options[0]
            
            if not workflow_name and plan_name:
                workflow_options = self.get_workflow_options(plan_name)
                if workflow_options and workflow_options[0] not in ["Select a plan first", "No workflows in plan"]:
                    workflow_name = workflow_options[0]
            
            return {'plan': plan_name, 'workflow': workflow_name}
            
        except Exception as e:
            logger.error(f"Error getting CLI defaults: {e}")
            return {'plan': None, 'workflow': None}
    
    # Widget Creation Helpers (for dynamic UI generation)
    
    def create_plan_change_callback(self, workflow_widget, save_as_default: bool = False) -> Callable:
        """Create callback function for plan selection changes"""
        def callback(plan_widget):
            self.handle_plan_change(plan_widget, workflow_widget, save_as_default)
        return callback
    
    def create_workflow_change_callback(self, save_as_default: bool = False) -> Callable:
        """Create callback function for workflow selection changes"""
        def callback(workflow_widget):
            self.handle_workflow_change(workflow_widget, save_as_default)
        return callback 