# src/sb_slipbox/sb_managers/__init__.py

"""
sb_managers init.

Imports manager classes for convenient access.
"""

from .source_manager import source_manager
from .extract_manager import ExtractManager
from .slip_manager import SlipManager
from .reference_manager import ReferenceManager
from .tag_manager import TagManager


"""

This __init__.py file does a few things:

- Imports all the manager classes for easy usage
- Uses relative imports with dot notation for portability 

This allows doing:

```python
from sb_slipbox.sb_managers import SourceManager, SlipManager
```

Without having to specify the full submodule path.

Some additional things that could be included:

- A common base Manager class that the others inherit from
- Manager factory functions to instantiate managers
- Configuration options for managers like DB connections

The goals are:

1. Provide simple access to all managers from one import

2. Allow portable imports that work regardless of where sb_managers is imported from

Let me know if you would like me to expand the __init__.py further or if you have any other recommendations!
"""