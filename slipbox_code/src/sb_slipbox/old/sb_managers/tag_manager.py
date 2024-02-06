# src/sb_slipbox/sb_managers/tag_manager.py

"""Manages tags for slips."""

"""

The key points:

- Saves and loads tags as Markdown files
- Uses tag name for filename
- CRUD methods for managing tags

This provides basic persistence for tags.

Some improvements:

- Add searching/filtering methods
- Store tags in a database
- Relate tags to slips that use them

Overall it allows creating a collection of tags that can be applied to slips and managed independently.

Let me know if you would like me to expand the docs or modify the implementation!
"""

import os
from sb_common.tag import Tag

class TagManager:
    """Manage tags."""

    def __init__(self, tag_dir):
        self.tag_dir = tag_dir

    def add(self, tag):
        """Add a new tag."""
        
        path = os.path.join(self.tag_dir, tag.name + ".md")
        with open(path, "w") as f:
            f.write(str(tag))

        return tag.name

    def get(self, name):
        """Get a tag by name."""

        path = os.path.join(self.tag_dir, name + ".md")
        if os.path.exists(path):
            with open(path) as f:
                text = f.read()

            return Tag.from_markdown(text)

    def update(self, tag):
        """Update an existing tag."""

        path = os.path.join(self.tag_dir, tag.name + ".md")
        if os.path.exists(path):
            with open(path, "w") as f:
                f.write(str(tag))

    def delete(self, name):
        """Delete a tag."""

        path = os.path.join(self.tag_dir, name + ".md")
        if os.path.exists(path):
            os.remove(path)