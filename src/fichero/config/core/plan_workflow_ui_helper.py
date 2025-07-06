"""
Plan/Workflow UI Helper

Unified helper for managing plan and workflow selections across all interfaces.
Eliminates code duplication between Settings, Document window, and CLI.
"""

import logging
from typing import Dict, List, Optional, Callable, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class PlanWorkflowUIHelper:
    """
    Unified helper for plan/workflow UI operations.
    
    Handles:
    - Loading plans/workflows for dropdowns
    - App-wide defaults (Settings window)
    - Document-specific selections (Document window)
    - CLI default handling
    - UI widget updates
    """
    
    def __init__(self, app):
        self.app = app
        
    # Core Data Access
    
    def get_plan_options(self) -> List[str]:
        """Get available plans for dropdown (clean list, no management options)"""
        from .plan_manager import PlanManager
        
        # Get basic plan list
        plans = PlanManager.get_available_plans(self.app)
        
        # Filter out error messages and management options
        valid_plans = [plan for plan in plans if plan not in [
            "No plans found", "Error loading plans", "Manage Plans..."
        ]]
        
        if valid_plans:
            return valid_plans
        else:
            return ["No plans found"]
    
    def get_workflow_options(self, plan_name: str) -> List[str]:
        """Get available workflows for a plan (clean list, no management options)"""
        from .plan_manager import PlanManager
        
        workflows = PlanManager.get_workflow_dropdown_options(plan_name, self.app)
        
        # Filter out any management options that might have slipped through
        clean_workflows = [wf for wf in workflows if wf not in [
            "Manage Plans...", "Manage Workflows..."
        ]]
        
        return clean_workflows
    
    def get_app_default_plan(self) -> Optional[str]:
        """Get app-wide default plan from shared settings"""
        from .plan_manager import PlanManager
        return PlanManager.get_default_plan(self.app)
    
    def get_app_default_workflow(self, plan_name: str = None) -> Optional[str]:
        """Get app-wide default workflow from shared settings"""
        from .plan_manager import PlanManager
        return PlanManager.get_default_workflow(plan_name, self.app)
    
    def set_app_default_plan(self, plan_name: str):
        """Set app-wide default plan in shared settings"""
        from .plan_manager import PlanManager
        PlanManager.set_default_plan(plan_name, self.app)
        logger.info(f"Set app default plan: {plan_name}")
    
    def set_app_default_workflow(self, workflow_name: str):
        """Set app-wide default workflow in shared settings"""
        from .plan_manager import PlanManager
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
                
                # Determine what value to set
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
                
                # Fall back to first available
                if workflow_options:
                    widget.value = workflow_options[0]
                    logger.debug(f"Set workflow to first available: {workflow_options[0]}")
                    return workflow_options[0]
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