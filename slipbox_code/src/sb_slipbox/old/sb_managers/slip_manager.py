# src/sb_slipbox/sb_managers/slip_note_manager.py

"""Manages slips."""

import os
from sb_common.slip import Slip

class SlipManager:
    """Manage slips."""
    
    def __init__(self, slip_dir):
        self.slip_dir = slip_dir
        
    def add(self, slip):
        """Add a new slip."""
        
        path = os.path.join(self.slip_dir, slip.id + ".md") 
        with open(path, "w") as f:
            f.write(str(slip))
            
        return slip.id
    
    def get(self, id):
        """Get a slip by ID."""
        
        path = os.path.join(self.slip_dir, id + ".md")
        if os.path.exists(path):
            with open(path) as f:
                text = f.read()
                
            return Slip.from_markdown(text)

    def update(self, slip):
        """Update an existing slip."""
        
        path = os.path.join(self.slip_dir, slip.id + ".md")
        if os.path.exists(path):
            with open(path, "w") as f:
                f.write(str(slip))
                
    def delete(self, id):
        """Delete a slip."""
        
        path = os.path.join(self.slip_dir, id + ".md")
        if os.path.exists(path):
            os.remove(path)
            
"""
The key aspects:

Saves and loads slips as Markdown files
CRUD methods for adding, getting, updating and deleting slips
Slip IDs used for filenames to uniquely identify slips
This provides basic persistence for slips.

Some ways to improve:

Use a database instead of the filesystem
Add search, filtering, and lookup methods
Support attachments like images
Manage links between slips
Overall it enables creating a collection of slips that can be manipulated independently.

Let me know if you would like me to expand the documentation or modify the implementation!
"""