# src/sb_slipbox/__init__.py

"""
sb_slipbox initialization.

Imports commonly used classes and functions
from submodules for convenient access.
"""

# Import SlipBox’s common functions and constants.
from src.common import *

from .sb_slipbox import sb_slipbox
# from .sb_slips.slip import slip

__all__ = ['sb_slipbox']

# Managers
# from sb_managers.source_manager import SourceManager
# from sb_managers.extract_manager import ExtractManager
# from sb_managers.slip_manager import SlipManager
# from sb_managers.reference_manager import ReferenceManager
# from sb_managers.tag_manager import TagManager

# Generators
# from sb_generators.extractor import Extractor
# from sb_generators.reference_generator import ReferenceGenerator
# from sb_generators.slip_generator import SlipGenerator
# from sb_generators.tag_generator import TagGenerator
# from sb_generators.link_generator import LinkGenerator

# Summarizers
# from sb_summarizers.summary_generator import