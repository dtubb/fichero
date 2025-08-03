"""
Enums for the Director system

Centralized location for enums used across multiple director modules
to avoid circular imports.
"""

from enum import Enum


class TaskPriority(Enum):
    """Task priority levels"""
    LOW = 1
    NORMAL = 5
    HIGH = 8
    URGENT = 10 