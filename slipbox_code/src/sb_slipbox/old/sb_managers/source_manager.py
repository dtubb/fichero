# src/sb_slipbox/sb_managers/source_manager.py 

"""Manages source documents."""

import os
from sb_common.source import Source

class SourceManager:
    """Manage source documents."""
    
    def __init__(self, sources_dir):
        self.sources_dir = sources_dir

    def add(self, source):
        """Add a new source document."""
        
        # Create reference slip
        slip = self._create_reference_slip(source)
        
        # Save reference slip to sources dir
        slip_path = os.path.join(self.sources_dir, slip.id + ".md")
        with open(slip_path, "w") as f:
            f.write(str(slip))
            
        return source.id

    def get(self, id):
        """Get a source by id."""
        
        slip_path = os.path.join(self.sources_dir, id + ".md")
        if os.path.exists(slip_path):
            with open(slip_path) as f:
                slip = Slip(text=f.read())
                
            return Source.from_slip(slip)

    def _create_reference_slip(self, source):
        """Create slip containing source reference."""
        
        text = f"Reference: {source.title} located at {source.location}"
        return Slip(id=source.id, text=text)

"""
Key points:

Creates a reference slip instead of storing actual files
Slip contains title and location to find the source
get() reconstructs Source object from slip
This allows managing sources without duplicating files in the slipbox folder structure.

Some ways to improve:

Support attaching full source documents
Add methods like listing, search, delete etc.
Store sources in a database instead of the filesystem
Let me know if you would like me to expand the documentation or modify the implementation!
"""