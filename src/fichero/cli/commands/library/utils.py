"""
Library Commands Utilities

Helper functions for library command operations.
"""

from pathlib import Path
from typing import Dict, Any
from rich.tree import Tree


def format_file_size(size: int) -> str:
    """Format file size in human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def build_tree_display(tree: Tree, structure: Dict[str, Any], max_depth: int, current_depth: int = 0):
    """Build tree display for structure"""
    if current_depth >= max_depth:
        return
    
    if structure['type'] == 'file':
        size_str = format_file_size(structure['size'])
        tree.add(f"📄 {structure['name']} ({size_str})")
    elif structure['type'] == 'directory':
        branch = tree.add(f"📁 {structure['name']}")
        for child in structure.get('children', []):
            build_tree_display(branch, child, max_depth, current_depth + 1)
    elif structure['type'] == 'truncated':
        tree.add(f"... (truncated at depth {current_depth})")
