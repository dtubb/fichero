"""
Plan Manager utility
Handles loading and parsing of plan files and workflows
"""

from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
import logging

from .loader import ConfigLoader

logger = logging.getLogger(__name__)


class PlanManager:
    """Manages plan files and workflow extraction"""
    
    @staticmethod
    def get_available_plans(app=None) -> List[str]:
        """
        Get list of available plans from both default and user directories
        
        Args:
            app: Application instance to get paths
            
        Returns:
            List of plan names (without file extensions)
        """
        try:
            plans = []
            
            # Get plan directories
            default_plans_dir, user_plans_dir = PlanManager._get_plan_directories(app)
            
            # Collect plan files from both directories
            for plans_dir in [default_plans_dir, user_plans_dir]:
                if plans_dir and plans_dir.exists():
                    for ext in ConfigLoader.get_supported_extensions():
                        plan_files = list(plans_dir.glob(f"*{ext}"))
                        plan_names = [f.stem for f in plan_files]
                        plans.extend(plan_names)
            
            # Remove duplicates and sort (user plans override defaults)
            unique_plans = sorted(list(set(plans)))
            
            if not unique_plans:
                return ["No plans found"]
            
            return unique_plans
            
        except Exception as e:
            logger.error(f"Error loading available plans: {e}")
            return ["Error loading plans"]
    
    @staticmethod
    def get_workflows_for_plan(plan_name: str, app=None) -> List[str]:
        """
        Get list of workflows for a specific plan
        
        Args:
            plan_name: Name of the plan
            app: Application instance to get paths
            
        Returns:
            List of workflow names
        """
        try:
            if plan_name in ["No plans found", "Error loading plans"]:
                return ["No workflows"]
            
            plan_data = PlanManager._load_plan_file(plan_name, app)
            if not plan_data:
                return ["Plan file not found"]
            
            workflows = plan_data.get('workflows', {})
            if not workflows:
                return ["No workflows in plan"]
            
            return sorted(workflows.keys())
            
        except Exception as e:
            logger.error(f"Error loading workflows for plan {plan_name}: {e}")
            return ["Error loading workflows"]
    
    @staticmethod
    def get_plan_workflow_combinations(app=None) -> List[str]:
        """
        Get dropdown options in format 'plan > workflow'
        
        Args:
            app: Application instance to get paths
            
        Returns:
            List of strings in format "plan > workflow"
        """
        try:
            options = []
            plans = PlanManager.get_available_plans(app)
            
            for plan in plans:
                if plan in ["No plans found", "Error loading plans"]:
                    continue
                    
                workflows = PlanManager.get_workflows_for_plan(plan, app)
                for workflow in workflows:
                    if workflow not in ["No workflows", "Plan file not found", "Error loading workflows"]:
                        options.append(f"{plan} > {workflow}")
            
            # Add edit option at the end
            if options:
                options.append(None)  # macOS separator
                options.append("Manage Plans...")
            
            if not options:
                return ["No plans or workflows available", None, "Manage Plans..."]
            
            return options
            
        except Exception as e:
            logger.error(f"Error getting plan/workflow combinations: {e}")
            return ["Error loading options", None, "Manage Plans..."]
    
    @staticmethod
    def get_plan_dropdown_options(app=None) -> List[str]:
        """
        Get plan options for standalone plan dropdown
        
        Args:
            app: Application instance to get paths
            
        Returns:
            List of plan names with management option
        """
        try:
            plans = PlanManager.get_available_plans(app)
            
            # Filter out error messages and add management option
            valid_plans = [plan for plan in plans if plan not in ["No plans found", "Error loading plans"]]
            
            if valid_plans:
                # Add management option
                valid_plans.append("Manage Plans...")
                return valid_plans
            else:
                return ["No plans found", "Manage Plans..."]
                
        except Exception as e:
            logger.error(f"Error getting plan dropdown options: {e}")
            return ["Error loading plans", "Manage Plans..."]
    
    @staticmethod
    def get_workflow_dropdown_options(plan_name: str, app=None) -> List[str]:
        """
        Get workflow options for a specific plan
        
        Args:
            plan_name: Name of the selected plan
            app: Application instance to get paths
            
        Returns:
            List of workflow names
        """
        try:
            if not plan_name or plan_name in ["No plans found", "Error loading plans", "Manage Plans..."]:
                return ["Select a plan first"]
            
            workflows = PlanManager.get_workflows_for_plan(plan_name, app)
            
            # Filter out error messages
            valid_workflows = [wf for wf in workflows if wf not in [
                "No workflows", "Plan file not found", "Error loading workflows"
            ]]
            
            if valid_workflows:
                return valid_workflows
            else:
                return ["No workflows in plan"]
                
        except Exception as e:
            logger.error(f"Error getting workflow dropdown options for plan {plan_name}: {e}")
            return ["Error loading workflows"]
    
    @staticmethod
    def get_plan_file_path(plan_name: str, app=None) -> Optional[Path]:
        """
        Get the file path for a specific plan
        
        Args:
            plan_name: Name of the plan
            app: Application instance to get paths
            
        Returns:
            Path to the plan file or None if not found
        """
        try:
            if not plan_name or plan_name in ["No plans found", "Error loading plans", "Manage Plans..."]:
                return None
                
            default_dir, user_dir = PlanManager._get_plan_directories(app)
            
            # Check user directory first (takes precedence)
            for plans_dir in [user_dir, default_dir]:
                if plans_dir and plans_dir.exists():
                    for ext in ConfigLoader.get_supported_extensions():
                        plan_file = plans_dir / f"{plan_name}{ext}"
                        if plan_file.exists():
                            return plan_file
            
            logger.warning(f"Plan file not found for: {plan_name}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting plan file path for {plan_name}: {e}")
            return None
    
    @staticmethod
    def get_default_plan(app=None) -> Optional[str]:
        """
        Get the default plan from settings, fallback to shared data, then first available
        
        Args:
            app: Application instance to get paths
            
        Returns:
            Default plan name or None if no plans available
        """
        try:
            # Try to get from app settings first (primary source)
            try:
                from ..core.settings import get_app_settings
                app_settings = get_app_settings(app)
                settings_default = app_settings.get_setting('defaults.plan')
                if settings_default:
                    # Verify the saved plan still exists
                    plans = PlanManager.get_available_plans(app)
                    valid_plans = [plan for plan in plans if plan not in ["No plans found", "Error loading plans"]]
                    if settings_default in valid_plans:
                        logger.debug(f"Using default plan from settings: {settings_default}")
                        return settings_default
                    else:
                        logger.warning(f"Settings default plan '{settings_default}' no longer exists")
            except Exception as e:
                logger.debug(f"Could not read default from app settings: {e}")
            
            # Fallback to shared data (legacy)
            try:
                from ...shared_data import get_shared_data
                shared_data = get_shared_data()
                saved_default = shared_data.get_setting('default_plan')
                if saved_default:
                    # Verify the saved plan still exists
                    plans = PlanManager.get_available_plans(app)
                    valid_plans = [plan for plan in plans if plan not in ["No plans found", "Error loading plans"]]
                    if saved_default in valid_plans:
                        logger.debug(f"Using default plan from shared data: {saved_default}")
                        return saved_default
                    else:
                        logger.warning(f"Saved default plan '{saved_default}' no longer exists")
            except Exception as e:
                logger.debug(f"Could not read default from shared data: {e}")
            
            # Fallback to first available plan
            plans = PlanManager.get_available_plans(app)
            valid_plans = [plan for plan in plans if plan not in ["No plans found", "Error loading plans"]]
            
            if valid_plans:
                logger.debug(f"Using first available plan: {valid_plans[0]}")
                return valid_plans[0]
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error getting default plan: {e}")
            return None
    
    @staticmethod
    def get_default_workflow(plan_name: str, app=None) -> Optional[str]:
        """
        Get the default workflow from settings, fallback to shared data, then 'default' or first
        
        Args:
            plan_name: Name of the plan
            app: Application instance to get paths
            
        Returns:
            Default workflow name or None if no workflows available
        """
        try:
            if not plan_name:
                return None
            
            workflows = PlanManager.get_workflows_for_plan(plan_name, app)
            
            # Filter out error messages
            valid_workflows = [wf for wf in workflows if wf not in [
                "No workflows", "Plan file not found", "Error loading workflows"
            ]]
            
            if not valid_workflows:
                return None
            
            # Try to get from app settings first (primary source)
            try:
                from ..core.settings import get_app_settings
                app_settings = get_app_settings(app)
                settings_default = app_settings.get_setting('defaults.workflow')
                if settings_default and settings_default in valid_workflows:
                    logger.debug(f"Using default workflow from settings: {settings_default}")
                    return settings_default
            except Exception as e:
                logger.debug(f"Could not read default workflow from app settings: {e}")
            
            # Fallback to shared data (legacy)
            try:
                from ...shared_data import get_shared_data
                shared_data = get_shared_data()
                saved_default = shared_data.get_setting('default_workflow')
                if saved_default and saved_default in valid_workflows:
                    logger.debug(f"Using default workflow from shared data: {saved_default}")
                    return saved_default
            except Exception as e:
                logger.debug(f"Could not read default workflow from shared data: {e}")
            
            # Fallback: prefer "default" workflow if it exists
            if "default" in valid_workflows:
                logger.debug(f"Using 'default' workflow: default")
                return "default"
            else:
                logger.debug(f"Using first available workflow: {valid_workflows[0]}")
                return valid_workflows[0]
                
        except Exception as e:
            logger.error(f"Error getting default workflow for plan {plan_name}: {e}")
            return None
    
    @staticmethod
    def set_default_plan(plan_name: str, app=None):
        """
        Set the default plan in settings and shared data
        
        Args:
            plan_name: Name of the plan to set as default
            app: Application instance (optional)
        """
        try:
            # Update app settings (primary storage)
            try:
                from ..core.settings import get_app_settings
                app_settings = get_app_settings(app)
                app_settings.set_setting('defaults.plan', plan_name)
                app_settings.save()
                logger.info(f"Set default plan in settings: {plan_name}")
            except Exception as e:
                logger.error(f"Failed to set default plan in settings: {e}")
            
            # Also update shared data for immediate use
            try:
                from ...shared_data import get_shared_data
                shared_data = get_shared_data()
                shared_data.set_setting('default_plan', plan_name)
                logger.info(f"Set default plan in shared data: {plan_name}")
            except Exception as e:
                logger.error(f"Failed to set default plan in shared data: {e}")
                
        except Exception as e:
            logger.error(f"Failed to set default plan: {e}")
            raise
    
    @staticmethod
    def set_default_workflow(workflow_name: str, app=None):
        """
        Set the default workflow in settings and shared data
        
        Args:
            workflow_name: Name of the workflow to set as default
            app: Application instance (optional)
        """
        try:
            # Update app settings (primary storage)
            try:
                from ..core.settings import get_app_settings
                app_settings = get_app_settings(app)
                app_settings.set_setting('defaults.workflow', workflow_name)
                app_settings.save()
                logger.info(f"Set default workflow in settings: {workflow_name}")
            except Exception as e:
                logger.error(f"Failed to set default workflow in settings: {e}")
            
            # Also update shared data for immediate use
            try:
                from ...shared_data import get_shared_data
                shared_data = get_shared_data()
                shared_data.set_setting('default_workflow', workflow_name)
                logger.info(f"Set default workflow in shared data: {workflow_name}")
            except Exception as e:
                logger.error(f"Failed to set default workflow in shared data: {e}")
                
        except Exception as e:
            logger.error(f"Failed to set default workflow: {e}")
            raise

    @staticmethod
    def parse_selection(selection: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Parse 'plan > workflow' selection back to (plan, workflow)
        
        Args:
            selection: Selection string in format "plan > workflow"
            
        Returns:
            Tuple of (plan_name, workflow_name) or (None, None) for special options
        """
        try:
            if not selection or selection in ["No plans or workflows available", "Error loading options", "Manage Plans..."] or selection is None:
                return None, None
            
            if " > " in selection:
                plan_name, workflow_name = selection.split(" > ", 1)
                return plan_name.strip(), workflow_name.strip()
            else:
                logger.warning(f"Invalid selection format: {selection}")
                return None, None
                
        except Exception as e:
            logger.error(f"Error parsing selection '{selection}': {e}")
            return None, None
    
    @staticmethod
    def _get_plan_directories(app=None) -> Tuple[Optional[Path], Optional[Path]]:
        """Get default and user plan directories"""
        try:
            if app and hasattr(app, 'paths'):
                # Default plans from app resources
                default_plans_dir = app.paths.app / "resources" / "config_defaults" / "plans"
                # User plans from app data
                user_plans_dir = app.paths.data / "plans"
            else:
                # Fallback paths
                default_plans_dir = Path(__file__).parent.parent.parent / "resources" / "config_defaults" / "plans"
                user_plans_dir = None
            
            return default_plans_dir, user_plans_dir
            
        except Exception as e:
            logger.error(f"Error getting plan directories: {e}")
            return None, None
    
    @staticmethod
    def _load_plan_file(plan_name: str, app=None) -> Optional[Dict[str, Any]]:
        """
        Load plan file data, checking user directory first, then defaults
        
        Args:
            plan_name: Name of the plan (without extension)
            app: Application instance
            
        Returns:
            Plan data dictionary or None if not found
        """
        try:
            default_plans_dir, user_plans_dir = PlanManager._get_plan_directories(app)
            
            # Check user plans first (overrides defaults)
            for plans_dir in [user_plans_dir, default_plans_dir]:
                if not plans_dir or not plans_dir.exists():
                    continue
                
                # Try each supported extension
                for ext in ConfigLoader.get_supported_extensions():
                    plan_file = plans_dir / f"{plan_name}{ext}"
                    if plan_file.exists():
                        return ConfigLoader.load_config_file(plan_file)
            
            logger.warning(f"Plan file not found: {plan_name}")
            return None
            
        except Exception as e:
            logger.error(f"Error loading plan file {plan_name}: {e}")
            return None
    
