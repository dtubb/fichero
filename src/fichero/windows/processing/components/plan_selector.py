"""
Plan Selector Component

Handles plan and workflow selection for processing.
Clean, modular component that loads available plans and workflows.
"""

import toga
from toga.style import Pack
from toga.constants import ROW
import logging
from typing import Optional, Callable, Dict

# Use the builtin _ function installed by translation.install()
# No need to import gettext or override _ - it's in builtins after app startup

logger = logging.getLogger(__name__)


class PlanSelector:
    """Plan and workflow selection component"""
    
    def __init__(self, app, on_plan_changed: Optional[Callable] = None):
        """Initialize plan selector"""
        self.app = app
        self.on_plan_changed = on_plan_changed
        
        # State
        self.current_plan: Optional[str] = None
        self.current_plan_filename: Optional[str] = None
        self.current_workflow: Optional[str] = None
        self.plan_display_to_filename: Dict[str, str] = {}
        
        # UI components
        self.container: Optional[toga.Box] = None
        self.plan_selector: Optional[toga.Selection] = None
        self.help_btn: Optional[toga.Button] = None
    
    def create(self) -> toga.Box:
        """Create the plan selector UI"""
        # Help button
        self.help_btn = toga.Button(
            _("help"),
            on_press=self._on_help,
            style=Pack(font_size=12, font_weight='bold', height=24)
        )
        
        # Plan selector
        self.plan_selector = toga.Selection(
            items=["Loading plans..."],
            style=Pack(flex=1, font_size=11, margin_left=5, height=24),
            on_change=self._on_plan_change
        )
        
        # Container
        self.container = toga.Box(
            children=[self.help_btn, self.plan_selector],
            style=Pack(direction=ROW)
        )
        
        # Initialize plans
        self._load_plans()
        
        return self.container
    
    def _load_plans(self):
        """Load available plans"""
        try:
            from fichero.config.core.plan_manager import PlanManager
            from fichero.config.core.loader import ConfigLoader
            
            # Get available plans and build mapping
            plan_display_names = []
            self.plan_display_to_filename = {}
            
            default_plans_dir, user_plans_dir = PlanManager._get_plan_directories(self.app)
            
            for plans_dir in [default_plans_dir, user_plans_dir]:
                if plans_dir and plans_dir.exists():
                    for ext in ConfigLoader.get_supported_extensions():
                        plan_files = list(plans_dir.glob(f"*{ext}"))
                        for plan_file in plan_files:
                            plan_data = ConfigLoader.load_config_file(plan_file)
                            if plan_data and 'title' in plan_data:
                                display_name = plan_data['title']
                                self.plan_display_to_filename[display_name] = plan_file.stem
                                plan_display_names.append(display_name)
                            else:
                                self.plan_display_to_filename[plan_file.stem] = plan_file.stem
                                plan_display_names.append(plan_file.stem)
            
            # Remove duplicates while preserving order
            seen_plans = set()
            unique_plans = []
            for name in plan_display_names:
                if name not in seen_plans:
                    seen_plans.add(name)
                    unique_plans.append(name)
            
            # Sort with Default first if present
            default_plan_filename = "Default"
            default_plan_display = None
            for display_name, filename in self.plan_display_to_filename.items():
                if filename == default_plan_filename:
                    default_plan_display = display_name
                    break
            
            sorted_plans = []
            if default_plan_display:
                sorted_plans.append(default_plan_display)
                other_plans = [n for n in unique_plans if n != default_plan_display]
                sorted_plans.extend(other_plans)
            else:
                sorted_plans = unique_plans
            
            # Update selector
            if sorted_plans:
                self.plan_selector.items = sorted_plans
                self.plan_selector.value = sorted_plans[0]
                self.current_plan = sorted_plans[0]
                self.current_plan_filename = self.plan_display_to_filename.get(sorted_plans[0])
                self._load_workflow_for_plan()
            else:
                self.plan_selector.items = ["No plans found"]
                self.plan_selector.value = None
                self.current_plan = None
                self.current_plan_filename = None
                self.current_workflow = None
            
            logger.info(f"Loaded {len(sorted_plans)} plans")
            
        except Exception as e:
            logger.error(f"Error loading plans: {e}")
            self.plan_selector.items = ["Error loading plans"]
            self.plan_selector.value = None
            self.current_plan = None
            self.current_plan_filename = None
            self.current_workflow = None
    
    def _load_workflow_for_plan(self):
        """Load the default workflow for the current plan"""
        try:
            if not self.current_plan_filename:
                self.current_workflow = None
                return
            
            from fichero.config.core.plan_manager import PlanManager
            workflows = PlanManager.get_workflows_for_plan(self.current_plan_filename, self.app)
            
            if workflows and workflows[0] not in ["No workflows", "Plan file not found", "Error loading workflows"]:
                self.current_workflow = workflows[0]
            else:
                self.current_workflow = None
                
        except Exception as e:
            logger.error(f"Error loading workflow: {e}")
            self.current_workflow = None
    
    def _on_plan_change(self, widget):
        """Handle plan selection change"""
        try:
            if not hasattr(self, 'plan_display_to_filename'):
                return
                
            display_name = widget.value
            filename = self.plan_display_to_filename.get(display_name)
            
            self.current_plan = display_name
            self.current_plan_filename = filename
            
            # Load default workflow for this plan
            self._load_workflow_for_plan()
            
            # Notify callback
            if self.on_plan_changed:
                self.on_plan_changed(self.current_plan, self.current_plan_filename, self.current_workflow)
            
            logger.info(f"Plan changed: {display_name} (filename: {filename})")
            
        except Exception as e:
            logger.error(f"Error handling plan change: {e}")
    
    def _on_help(self, widget):
        """Handle help button"""
        import webbrowser
        webbrowser.open("https://www.tubb.ca/fichero/")
    
    def get_current_plan(self) -> Optional[str]:
        """Get current plan display name"""
        return self.current_plan
    
    def get_current_plan_filename(self) -> Optional[str]:
        """Get current plan filename"""
        return self.current_plan_filename
    
    def get_current_workflow(self) -> Optional[str]:
        """Get current workflow"""
        return self.current_workflow
    
    def get_plan_description(self) -> str:
        """Get description of current plan"""
        try:
            if not self.current_plan_filename:
                return "Please select a plan to see its description."
            
            from fichero.config.core.plan_manager import PlanManager
            plan_data = PlanManager._load_plan_file(self.current_plan_filename, self.app)
            
            if plan_data and 'description' in plan_data:
                return plan_data['description']
            else:
                return f"Plan: {self.current_plan}"
                
        except Exception as e:
            logger.debug(f"Could not load plan description: {e}")
            return f"Plan: {self.current_plan}"
    
    def is_plan_selected(self) -> bool:
        """Check if a valid plan is selected"""
        return bool(self.current_plan and self.current_plan_filename) 