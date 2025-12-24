"""
Settings Window for Fichero application.

YAML-driven settings UI with schema-based form generation.
"""

import logging
from typing import Dict, Any, List
from pathlib import Path

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from fichero.config.ui.base_config_library import BaseConfigLibrary, UISchema
from fichero.config.core.settings_manager import SettingsManager
from fichero.config.core.plan_workflow_ui_helper import DEFAULT_PLAN_FILENAME

logger = logging.getLogger(__name__)


class SettingsWindow:
    """Settings window with YAML-driven schema UI."""

    def __init__(self, app):
        self.app = app
        self.window = toga.Window(
            title="Fichero Settings",
            size=(425, 500),
            resizable=True
        )

        # Create content and set it
        self._content = _SettingsContent(app)
        self.window.content = self._content.create()

        self._center_window()

        # Register for state persistence
        if hasattr(self.app, 'window_state_tracker') and self.app.window_state_tracker:
            self.app.window_state_tracker.register_window("settings", self.window, restore=True)

        logger.info("SettingsWindow initialized")

    def _center_window(self):
        """Center window on screen."""
        try:
            screen = self.app.screens[0]
            x = (screen.size.width - self.window.size.width) // 2
            y = (screen.size.height - self.window.size.height) // 2
            self.window.position = (x, y)
        except Exception:
            pass

    def show(self):
        self.window.show()

    def hide(self):
        self.window.hide()

    def close(self):
        if self.window:
            if hasattr(self.app, 'window_state_tracker') and self.app.window_state_tracker:
                self.app.window_state_tracker.save_window_state("settings")
            self.window.close()
            self.window = None
            self._content = None


class _SettingsContent(BaseConfigLibrary):
    """Settings content with schema-driven UI generation."""

    def __init__(self, app):
        self.schema_file = app.paths.app / "resources" / "config_ui_schemas" / "settings_schema.yml"
        self.settings_manager = SettingsManager(app)

        super().__init__(app, use_file_library=False, use_option_container=True, create_desktop_window=False)
        logger.info("SettingsContent initialized")

    def create(self):
        """Create the settings UI."""
        schema = self.get_schema()
        data = self.initialize_settings_data()

        # Build content from schema
        if schema.sections:
            content_list = []
            for i, section in enumerate(schema.sections):
                section_title = _(section.get('title', f'Section {i}'))
                section_content = self._create_sectioned_interface(section.get('sections', []), data)

                scroll_container = toga.ScrollContainer(
                    content=section_content,
                    vertical=True,
                    horizontal=False,
                    style=Pack(flex=1)
                )
                content_list.append((section_title, scroll_container))

            option_container = toga.OptionContainer(
                content=content_list,
                style=Pack(flex=1, padding=(20, 20, 0, 20))
            )
        elif schema.content_sections:
            content = self._create_sectioned_interface(schema.content_sections, data)
            option_container = toga.OptionContainer(
                content=[(_("preferences_title"), content)],
                style=Pack(flex=1, padding=(20, 20, 0, 20))
            )
        else:
            option_container = toga.OptionContainer(
                content=[(_("preferences_title"), toga.Label(_("preferences_no_content")))],
                style=Pack(flex=1, padding=(20, 20, 0, 20))
            )

        main_content = toga.Box(style=Pack(direction=COLUMN, flex=1))
        main_content.add(option_container)

        # Restore defaults button
        restore_btn = toga.Button(
            _("preferences_restore_defaults"),
            on_press=self._handle_restore_defaults,
            style=Pack(padding=(10, 20))
        )
        main_content.add(restore_btn)

        return main_content

    def _handle_restore_defaults(self, widget=None):
        """Restore settings to defaults."""
        try:
            default_data = self.settings_manager.get_default_template()
            self.populate_data(default_data)
            self.save_settings_data(default_data)
            logger.info("Settings restored to defaults")
        except Exception as e:
            logger.error(f"Failed to restore defaults: {e}")

    def create_file_manager(self):
        return None

    def get_schema(self) -> UISchema:
        """Load UI schema from YAML file."""
        try:
            logger.info(f"Loading settings schema from: {self.schema_file}")
            with open(self.schema_file, 'r', encoding='utf-8') as f:
                yaml_parser = YAML()
                schema_data = yaml_parser.load(f)

            self._populate_dynamic_options(schema_data)

            return UISchema(
                title=schema_data.get('title', _('preferences_title')),
                description=schema_data.get('description', _('preferences_description')),
                sections=schema_data.get('sections', []),
                content_sections=schema_data.get('content_sections', []),
                window_title=schema_data.get('window_title'),
                window_size=schema_data.get('window_size')
            )
        except Exception as e:
            logger.error(f"Failed to load settings schema: {e}")
            return UISchema(
                title=_('preferences_title'),
                description=_('preferences_description'),
                content_sections=[{
                    "title": _('preferences_error'),
                    "fields": [{
                        "id": "error_message",
                        "type": "label",
                        "label": _('preferences_load_error').format(error=str(e))
                    }]
                }]
            )

    def _populate_dynamic_options(self, schema_data: Dict[str, Any]):
        """Populate dynamic options for plan/workflow fields."""
        try:
            from fichero.config.core.plan_workflow_ui_helper import PlanWorkflowUIHelper

            self.ui_helper = PlanWorkflowUIHelper(self.app)
            plan_options = self.ui_helper.get_plan_options()

            # Find default plan and put it first
            default_plan_display = None
            for plan_display_name in plan_options:
                plan_filename = self.ui_helper.get_plan_filename(plan_display_name)
                if plan_filename == DEFAULT_PLAN_FILENAME.replace('.yml', ''):
                    default_plan_display = plan_display_name
                    break

            if default_plan_display:
                plan_options = [default_plan_display] + [p for p in plan_options if p != default_plan_display]

            self._populate_field_options(schema_data, "defaults.plan", plan_options)
            self._add_field_callback(schema_data, "defaults.plan", self._on_plan_selection_change)
            self._add_field_callback(schema_data, "defaults.workflow", self._on_workflow_selection_change)
            self._populate_field_options(schema_data, "defaults.workflow", [_('preferences_select_plan')])
            self._add_button_handler(schema_data, "auto_calculate_workers", self._on_auto_calculate_workers)

        except Exception as e:
            logger.error(f"Failed to populate dynamic options: {e}")

    def _add_field_callback(self, schema_data: Dict[str, Any], field_id: str, callback):
        for section in schema_data.get('sections', []):
            for subsection in section.get('sections', []):
                for field in subsection.get('fields', []):
                    if field.get('id') == field_id:
                        field['on_change'] = callback
                        return

    def _add_button_handler(self, schema_data: Dict[str, Any], field_id: str, callback):
        for section in schema_data.get('sections', []):
            for subsection in section.get('sections', []):
                for field in subsection.get('fields', []):
                    if field.get('id') == field_id:
                        field['on_press'] = callback
                        return

    def _on_plan_selection_change(self, widget):
        try:
            if not hasattr(self, 'ui_helper'):
                return

            plan_value = getattr(widget, 'value', None)
            logger.info(f"Plan selection changed to: {plan_value}")

            workflow_widget = self.widgets.get('defaults.workflow')
            if workflow_widget:
                result = self.ui_helper.handle_plan_change(widget, workflow_widget, save_as_default=True)
                logger.info(f"Settings plan changed: {result}")
                if result.get('workflow'):
                    self._on_workflow_selection_change(workflow_widget)
        except Exception as e:
            logger.error(f"Error handling plan selection change: {e}")

    def _on_workflow_selection_change(self, widget):
        try:
            if not hasattr(self, 'ui_helper'):
                return
            workflow_name = self.ui_helper.handle_workflow_change(widget, save_as_default=True)
            logger.info(f"Settings workflow changed: {workflow_name}")
        except Exception as e:
            logger.error(f"Error handling workflow selection change: {e}")

    def _on_auto_calculate_workers(self, widget):
        try:
            from fichero.director.backends.worker_sizing import get_optimal_workers

            current_backend = self._get_field_value("workers.backend", self.original_data, "python")
            optimal_config = get_optimal_workers(current_backend)

            logger.info(f"Optimal: {optimal_config.cpu_workers} CPU, {optimal_config.io_workers} IO")

            cpu_widget = self.widgets.get("workers.cpu_workers")
            io_widget = self.widgets.get("workers.io_workers")

            if cpu_widget:
                cpu_widget.value = optimal_config.cpu_workers
            if io_widget:
                io_widget.value = optimal_config.io_workers

            self._perform_save()
        except Exception as e:
            logger.error(f"Error auto-calculating workers: {e}")

    def _populate_field_options(self, schema_data: Dict[str, Any], field_id: str, options: List[str]):
        for section in schema_data.get('sections', []):
            for subsection in section.get('sections', []):
                for field in subsection.get('fields', []):
                    if field.get('id') == field_id:
                        valid_options = [opt for opt in options if opt not in [_('preferences_no_plans'), _('preferences_error_loading_plans')]]
                        if not valid_options:
                            valid_options = [_('preferences_no_options')]
                        field['options'] = valid_options
                        return

    def populate_data(self, data: Dict[str, Any]):
        logger.info(f"Settings populate_data called with {len(data)} keys")
        pass

    def _on_widget_change(self, widget):
        for field_id, stored_widget in self.widgets.items():
            if stored_widget is widget:
                if field_id in self.change_handlers:
                    try:
                        self.change_handlers[field_id](widget)
                    except Exception as e:
                        logger.error(f"Error in change handler for {field_id}: {e}")
                break
        super()._on_widget_change(widget)

    def initialize_settings_data(self) -> Dict[str, Any]:
        logger.info("Loading settings data")
        try:
            data = self.settings_manager.load_settings()

            if 'defaults' not in data:
                data['defaults'] = {}

            try:
                from fichero.config.core.plan_workflow_ui_helper import PlanWorkflowUIHelper
                ui_helper = PlanWorkflowUIHelper(self.app)

                current_plan = ui_helper.get_app_default_plan()
                current_workflow = ui_helper.get_app_default_workflow(current_plan)

                if not data['defaults'].get('plan'):
                    data['defaults']['plan'] = current_plan or ""
                if not data['defaults'].get('workflow'):
                    data['defaults']['workflow'] = current_workflow or ""
            except Exception as e:
                logger.error(f"Failed to load app defaults: {e}")
                data['defaults'].setdefault('plan', "")
                data['defaults'].setdefault('workflow', "")

            return data
        except Exception as e:
            logger.error(f"Failed to load settings: {e}")
            return self.settings_manager.get_default_template()

    def save_settings_data(self, data: Dict[str, Any]) -> bool:
        logger.info(f"Saving settings data with {len(data)} keys")
        try:
            success = self.settings_manager.save_settings(data)
            if success:
                logger.info("Settings saved successfully")
            return success
        except Exception as e:
            logger.error(f"Failed to save settings data: {e}")
            return False

    def save_settings(self):
        return self.save_settings_data(self.get_current_data())

    def load_settings(self):
        return self.initialize_settings_data()

    def refresh(self):
        if hasattr(super(), 'refresh'):
            super().refresh()

    def get_current_data(self):
        if hasattr(super(), 'get_current_data'):
            return super().get_current_data()
        return {}
