"""
CLI Display Helper

Handles all CLI display functionality extracted from FicheroDirector.
Focuses on status displays, configuration, and system information.
"""

import logging
import platform
import sys
from typing import Dict, Any

logger = logging.getLogger(__name__)


class CLIDisplayHelper:
    """
    Handles CLI display functionality for the director service.
    
    Extracted from FicheroDirector to improve separation of concerns.
    Handles:
    - Status displays
    - Configuration management  
    - Available plans listing
    - System information display
    """
    
    def __init__(self, director):
        self.director = director
        logger.info("CLIDisplayHelper initialized")
    
    def display_status(self, console):
        """Display current status for CLI"""
        if console:
            # Use task monitor session stats for more accurate information
            if hasattr(self.director, 'task_monitor') and self.director.task_monitor:
                stats = self.director.task_monitor.get_session_stats()
                console.print("\n📊 Director Status:")
                console.print(f"   Backend: {self.director.backend.backend_name if self.director.backend else 'none'}")
                console.print(f"   Initialized: {self.director.backend.is_initialized if self.director.backend else False}")
                console.print(f"   Active tasks: {stats.get('active_tasks', 0)}")
                console.print(f"   Session tasks: {stats.get('session_tasks', 0)}")
                console.print(f"   Completed: {stats.get('completed_tasks', 0)}")
                console.print(f"   Failed: {stats.get('failed_tasks', 0)}")
            else:
                # Fallback to director stats
                stats = self.director.get_stats()
                console.print("\n📊 Director Status:")
                console.print(f"   Backend: {stats.get('backend_type', 'none')}")
                console.print(f"   Initialized: {stats.get('is_initialized', False)}")
                console.print(f"   Active tasks: {stats.get('active_tasks', 0)}")
                console.print(f"   Total submitted: {stats.get('total_submitted', 0)}")
                console.print(f"   Total completed: {stats.get('total_completed', 0)}")
                console.print(f"   Total failed: {stats.get('total_failed', 0)}")
    
    def configure_settings(self, console, show_defaults: bool = False, 
                          backend: str = None, cpu_workers: int = None,
                          io_workers: int = None, memory_per_worker: int = None,
                          plan: str = None, workflow: str = None):
        """Configure settings for CLI"""
        if console:
            console.print("⚙️  Configuration")
            console.print(f"   Current backend: {self.director.settings.get('workers', {}).get('backend', 'python')}")
            
            # Backend configuration
            if backend:
                if 'workers' not in self.director.settings:
                    self.director.settings['workers'] = {}
                self.director.settings['workers']['backend'] = backend
                console.print(f"   ✅ Updated backend to: {backend}")
            
            # Plan/workflow defaults configuration
            if plan or workflow:
                try:
                    from ...config.core.plan_workflow_ui_helper import PlanWorkflowUIHelper
                    ui_helper = PlanWorkflowUIHelper(self.director.app)
                    
                    if plan:
                        # Validate plan exists
                        available_plans = ui_helper.get_plan_options()
                        if plan in available_plans:
                            ui_helper.set_app_default_plan(plan)
                            console.print(f"   ✅ Set default plan to: {plan}")
                        else:
                            console.print(f"   ❌ Plan '{plan}' not found")
                            console.print(f"   Available plans: {', '.join(available_plans)}")
                            return
                    
                    if workflow:
                        # Get the plan to validate workflow against
                        current_plan = plan or ui_helper.get_app_default_plan()
                        if current_plan:
                            available_workflows = ui_helper.get_workflow_options(current_plan)
                            if workflow in available_workflows:
                                ui_helper.set_app_default_workflow(workflow)
                                console.print(f"   ✅ Set default workflow to: {workflow}")
                            else:
                                console.print(f"   ❌ Workflow '{workflow}' not found in plan '{current_plan}'")
                                console.print(f"   Available workflows: {', '.join(available_workflows)}")
                        else:
                            console.print(f"   ❌ No plan set - cannot set workflow '{workflow}'")
                            console.print("   Set a plan first with --plan option")
                    
                except Exception as e:
                    console.print(f"   ❌ Failed to configure defaults: {e}")
            
            # Show current status
            if show_defaults or plan or workflow:
                console.print("\n📊 Current Configuration:")
                console.print(f"   Backend: {self.director.settings.get('workers', {}).get('backend', 'python')}")
                
                try:
                    from ...config.core.plan_workflow_ui_helper import PlanWorkflowUIHelper
                    ui_helper = PlanWorkflowUIHelper(self.director.app)
                    defaults = ui_helper.get_cli_defaults()
                    console.print(f"   Default Plan: {defaults.get('plan', 'None set')}")
                    console.print(f"   Default Workflow: {defaults.get('workflow', 'None set')}")
                except Exception as e:
                    console.print(f"   Failed to get defaults: {e}")
    
    def display_available_plans(self, console):
        """Display available plans for CLI"""
        try:
            from ...config.core.plan_workflow_ui_helper import PlanWorkflowUIHelper
            
            ui_helper = PlanWorkflowUIHelper(self.director.app)
            plans = ui_helper.get_plan_options()
            
            if console:
                console.print("\n📋 Available Plans:")
                
                if not plans or plans == ["No plans found"]:
                    console.print("   No plans found")
                    console.print("   💡 Create plans in the GUI Settings window")
                else:
                    for plan in plans:
                        console.print(f"   • {plan}")
                        
                        # Show all workflows for each plan
                        workflows = ui_helper.get_workflow_options(plan)
                        if workflows and workflows[0] not in ["Select a plan first", "No workflows in plan"]:
                            for workflow in workflows:  # Show ALL workflows
                                console.print(f"     └─ {workflow}")
                        else:
                            console.print("     └─ No workflows")
                
                # Show defaults
                defaults = ui_helper.get_cli_defaults()
                console.print(f"\n⭐ Current Defaults:")
                console.print(f"   Plan: {defaults.get('plan', 'None set')}")
                console.print(f"   Workflow: {defaults.get('workflow', 'None set')}")
                console.print(f"\n💡 To set defaults: 'fichero-cli configure --plan <plan> --workflow <workflow>'")
                
        except Exception as e:
            if console:
                console.print(f"❌ Failed to list plans: {e}")
            logger.error(f"Failed to display available plans: {e}")
    
    def display_system_info(self, console):
        """Display system information for CLI"""
        if console:
            console.print("\n🖥️  System Information:")
            console.print(f"   Platform: {platform.system()} {platform.release()}")
            console.print(f"   Python: {sys.version.split()[0]}")
            console.print(f"   Architecture: {platform.machine()}")
            
            console.print(f"\n📊 Director Info:")
            stats = self.director.get_stats()
            console.print(f"   Instance ID: {stats.get('instance_id', 'unknown')}")
            console.print(f"   Backend: {stats.get('backend_type', 'none')}")
            console.print(f"   Initialized: {stats.get('is_initialized', False)}")
            
            # Show task monitor stats if available
            if hasattr(self.director, 'task_monitor') and self.director.task_monitor:
                task_stats = self.director.task_monitor.get_session_stats()
                console.print(f"\n📈 Current Session:")
                console.print(f"   Active tasks: {task_stats.get('active_tasks', 0)}")
                console.print(f"   Session tasks: {task_stats.get('session_tasks', 0)}")
                console.print(f"   Completed: {task_stats.get('completed_tasks', 0)}")
                console.print(f"   Failed: {task_stats.get('failed_tasks', 0)}")
            
            if self.director.backend:
                console.print(f"\n🔧 Backend Details:")
                backend_info = self.director.get_backend_info()
                console.print(f"   Name: {backend_info.get('backend_name', 'unknown')}")
                console.print(f"   Status: {backend_info.get('status', 'unknown')}") 