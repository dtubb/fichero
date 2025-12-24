"""
Fichero Document Processing Tools Package

This package contains all the processing tools used in workflows.
Each tool provides both a batch function (for direct calls) and a CLI function (for command line usage).
"""

# NOTE: Don't import utils here - it has dependencies on fichero.config
# which may not be available in all contexts. Import utils.* directly when needed.

__all__ = [] 