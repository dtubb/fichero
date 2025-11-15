"""
Tool Registry - Loads tool definitions from actual tool modules

Extracts parameter schemas directly from tool files instead of
manually defining them. This ensures UI stays in sync with backend.
"""
import logging
from typing import Dict, Any, List, Optional
import inspect

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Registry that loads tool definitions from actual tool modules.

    Introspects tool files to extract:
    - Parameter names and types
    - Default values
    - Available options (from templates/enums)
    - Descriptions
    """

    _instance = None
    _tools: Dict[str, Dict[str, Any]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Load all tool definitions"""
        logger.info("Initializing ToolRegistry")
        self._tools = {}

        # Load each tool
        self._load_crop()
        self._load_rotate()
        self._load_enhance()
        self._load_split()
        self._load_transcribe_qwen()

        logger.info(f"Loaded {len(self._tools)} tool definitions")

    def _load_crop(self):
        """Load crop tool definition from crop.py programmatically"""
        try:
            import fichero.tools.crop as crop_module

            # Get the batch function to introspect
            crop_fn = crop_module.crop_batch

            # Extract docstring for description
            doc = inspect.getdoc(crop_fn) or ""
            description = doc.split('\n')[0] if doc else "Crop document pages to remove borders"

            # Get function signature
            sig = inspect.signature(crop_fn)

            # Auto-extract UI parameters
            parameters = []

            # Look for parameters starting with 'contour_' - these are user-facing
            for param_name, param in sig.parameters.items():
                if not param_name.startswith('contour_'):
                    continue

                # Get default value
                default_value = param.default if param.default != inspect.Parameter.empty else None

                # Get type annotation
                param_type = param.annotation
                type_str = str(param_type) if param_type != inspect.Parameter.empty else 'str'

                # Auto-generate label from parameter name
                # contour_template -> "Template", contour_padding -> "Padding"
                label_parts = param_name.replace('contour_', '').split('_')
                label = ' '.join(word.capitalize() for word in label_parts)

                # Determine widget type based on parameter name and type
                if param_name == 'contour_template':
                    # Special case: load options from CONTOUR_TEMPLATES
                    templates = crop_module.CONTOUR_TEMPLATES
                    options = [(key, template['name']) for key, template in templates.items()]

                    parameters.append({
                        'name': param_name,
                        'label': f'{label}',
                        'type': 'select',
                        'options': options,
                        'default': default_value
                    })

                elif 'bool' in type_str or type(default_value) is bool:
                    # Boolean parameter - use checkbox
                    parameters.append({
                        'name': param_name,
                        'label': label,
                        'type': 'boolean',
                        'default': default_value or False
                    })

                elif 'float' in type_str or isinstance(default_value, float):
                    # Float parameter - use number input with step
                    parameters.append({
                        'name': param_name,
                        'label': label,
                        'type': 'number',
                        'default': default_value or 0.0,
                        'min': 0.0,
                        'max': 1.0,
                        'step': 0.1
                    })

                elif 'int' in type_str or isinstance(default_value, int):
                    # Integer parameter - use number input
                    # Auto-detect reasonable min/max based on parameter name
                    min_val = 0
                    max_val = 1000
                    if 'padding' in param_name:
                        max_val = 100
                    elif 'threshold' in param_name:
                        max_val = 255

                    parameters.append({
                        'name': param_name,
                        'label': f'{label} (px)' if 'padding' in param_name else label,
                        'type': 'number',
                        'default': default_value or 0,
                        'min': min_val,
                        'max': max_val
                    })

            # Extract tool name from module or derive from module name
            tool_name = getattr(crop_module, 'TOOL_NAME', 'Crop Document')

            self._tools['crop'] = {
                'name': tool_name,
                'description': description,
                'parameters': parameters
            }

            logger.info(f"✓ Programmatically loaded crop: {len(parameters)} params from function signature")

        except Exception as e:
            logger.error(f"Failed to load crop tool: {e}", exc_info=True)

    def _load_rotate(self):
        """Load rotate tool definition from rotate.py"""
        self._tools['rotate'] = {
            'name': 'Rotate/Straighten',
            'description': 'Auto-straighten text orientation using Hough line transform',
            'parameters': []  # Uses optimal defaults
        }
        logger.debug("Loaded rotate tool definition")

    def _load_enhance(self):
        """Load enhance tool definition from enhance.py"""
        self._tools['enhance'] = {
            'name': 'Enhance Quality',
            'description': 'Improve contrast and clarity using CLAHE',
            'parameters': []  # Uses optimal defaults
        }
        logger.debug("Loaded enhance tool definition")

    def _load_split(self):
        """Load split tool definition from split.py"""
        self._tools['split'] = {
            'name': 'Split Pages',
            'description': 'Divide double-page images',
            'parameters': [
                {
                    'name': 'method',
                    'label': 'Split Method',
                    'type': 'select',
                    'options': [
                        ('auto', 'Auto-detect'),
                        ('center', 'Center Split'),
                        ('fold', 'Fold Detection'),
                    ],
                    'default': 'auto'
                }
            ]
        }
        logger.debug("Loaded split tool definition")

    def _load_transcribe_qwen(self):
        """Load transcribe_qwen_max tool definition"""
        self._tools['transcribe_qwen_max'] = {
            'name': 'Transcribe (AI)',
            'description': 'Extract text from images using Qwen AI models',
            'parameters': [
                {
                    'name': 'model',
                    'label': 'Model',
                    'type': 'select',
                    'options': [
                        ('qwen-max', 'Qwen Max (Best)'),
                        ('qwen-plus', 'Qwen Plus (Fast)'),
                    ],
                    'default': 'qwen-max'
                }
            ]
        }
        logger.debug("Loaded transcribe_qwen_max tool definition")

    @classmethod
    def get_tool(cls, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get tool definition by name"""
        instance = cls()
        return instance._tools.get(tool_name)

    @classmethod
    def get_all_tools(cls) -> Dict[str, Dict[str, Any]]:
        """Get all tool definitions"""
        instance = cls()
        return instance._tools.copy()

    @classmethod
    def get_workflow_order(cls) -> List[str]:
        """Get recommended workflow order"""
        return [
            'crop',
            'split',
            'rotate',
            'enhance',
            'transcribe_qwen_max'
        ]
