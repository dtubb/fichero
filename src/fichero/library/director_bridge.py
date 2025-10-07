"""
Library Director Bridge
Integrates library collections with director processing system
"""

import asyncio
from pathlib import Path
from typing import List, Dict, Optional, Any
import logging

from fichero.library.processing_navigator import ProcessingNavigator, ProcessingStep

# Try to import Director - will fail on iOS due to multiprocessing
try:
    from fichero.director.director_service import FicheroDirector
    DIRECTOR_AVAILABLE = True
except ImportError as e:
    # iOS doesn't support Director (multiprocessing not available)
    DIRECTOR_AVAILABLE = False
    FicheroDirector = None
    logging.warning(f"Director not available (likely iOS): {e}")

logger = logging.getLogger(__name__)

class LibraryDirectorBridge:
    """Bridge between library collections and director processing"""
    
    def __init__(self, director: FicheroDirector):
        """Initialize bridge with director instance"""
        self.director = director
        
    async def process_collection(self, collection_path: Path, steps: Optional[List[str]] = None) -> Dict[str, Any]:
        """Process a collection through the director workflow"""
        try:
            # Create navigator for the collection
            navigator = ProcessingNavigator(collection_path)
            
            # Get available steps
            available_steps = navigator.get_available_steps()
            
            if not available_steps:
                return {
                    "success": False,
                    "error": "No processing steps found in collection",
                    "collection_path": str(collection_path)
                }
            
            # If specific steps requested, filter them
            if steps:
                step_names = [step.name for step in available_steps]
                requested_steps = [step for step in steps if step in step_names]
                if not requested_steps:
                    return {
                        "success": False,
                        "error": f"Requested steps {steps} not found in available steps {step_names}",
                        "collection_path": str(collection_path)
                    }
            else:
                # Process all available steps
                requested_steps = [step.name for step in available_steps]
            
            # Process each step
            results = {}
            for step_name in requested_steps:
                try:
                    result = await self._process_step(collection_path, step_name)
                    results[step_name] = result
                except Exception as e:
                    logger.error(f"Error processing step {step_name}: {e}")
                    results[step_name] = {
                        "success": False,
                        "error": str(e),
                        "step": step_name
                    }
            
            return {
                "success": True,
                "collection_path": str(collection_path),
                "processed_steps": requested_steps,
                "results": results
            }
            
        except Exception as e:
            logger.error(f"Error processing collection {collection_path}: {e}")
            return {
                "success": False,
                "error": str(e),
                "collection_path": str(collection_path)
            }
    
    async def _process_step(self, collection_path: Path, step_name: str) -> Dict[str, Any]:
        """Process a specific step for a collection"""
        try:
            # Get the processing step definition
            navigator = ProcessingNavigator(collection_path)
            if step_name not in navigator.steps:
                return {
                    "success": False,
                    "error": f"Unknown processing step: {step_name}",
                    "step": step_name
                }
            
            step = navigator.steps[step_name]
            step_path = collection_path / step.path
            
            # Check if step already has content
            if navigator._has_content(step_path):
                return {
                    "success": True,
                    "message": f"Step {step_name} already processed",
                    "step": step_name,
                    "file_count": len(navigator.get_step_outputs(step_name))
                }
            
            # Process the step using director
            # This would integrate with the actual director processing logic
            # For now, we'll simulate the processing
            
            result = await self.director.process_with_auto_detection(
                input_paths=[str(collection_path)],
                output_path=str(step_path),
                plan_name=f"process_{step_name}"
            )
            
            return {
                "success": True,
                "step": step_name,
                "result": result,
                "output_path": str(step_path)
            }
            
        except Exception as e:
            logger.error(f"Error processing step {step_name}: {e}")
            return {
                "success": False,
                "error": str(e),
                "step": step_name
            }
    
    async def get_collection_processing_status(self, collection_path: Path) -> Dict[str, Any]:
        """Get the processing status of a collection"""
        try:
            navigator = ProcessingNavigator(collection_path)
            summary = navigator.get_processing_summary()
            
            # Add processing status information
            status = {
                "collection_path": str(collection_path),
                "processing_summary": summary,
                "available_steps": summary["available_steps"],
                "total_files": summary["total_files"],
                "steps_status": {}
            }
            
            # Check status of each step
            for step_name, step_info in summary["steps"].items():
                if step_info["file_count"] > 0:
                    status["steps_status"][step_name] = {
                        "status": "completed",
                        "file_count": step_info["file_count"],
                        "description": step_info["description"]
                    }
                else:
                    status["steps_status"][step_name] = {
                        "status": "pending",
                        "file_count": 0,
                        "description": step_info["description"]
                    }
            
            return status
            
        except Exception as e:
            logger.error(f"Error getting collection status {collection_path}: {e}")
            return {
                "success": False,
                "error": str(e),
                "collection_path": str(collection_path)
            }
    
    async def process_collection_level(self, collection_path: Path, level: int = 0) -> Dict[str, Any]:
        """Process a specific level of a collection hierarchy"""
        try:
            # Get all subdirectories at the specified level
            level_paths = self._get_level_paths(collection_path, level)
            
            if not level_paths:
                return {
                    "success": False,
                    "error": f"No paths found at level {level}",
                    "collection_path": str(collection_path),
                    "level": level
                }
            
            # Process each path at this level
            results = {}
            for path in level_paths:
                try:
                    result = await self.process_collection(path)
                    results[str(path)] = result
                except Exception as e:
                    logger.error(f"Error processing path {path}: {e}")
                    results[str(path)] = {
                        "success": False,
                        "error": str(e),
                        "path": str(path)
                    }
            
            return {
                "success": True,
                "collection_path": str(collection_path),
                "level": level,
                "processed_paths": len(level_paths),
                "results": results
            }
            
        except Exception as e:
            logger.error(f"Error processing collection level {level}: {e}")
            return {
                "success": False,
                "error": str(e),
                "collection_path": str(collection_path),
                "level": level
            }
    
    def _get_level_paths(self, collection_path: Path, level: int) -> List[Path]:
        """Get all paths at a specific level in the collection hierarchy"""
        if level == 0:
            return [collection_path]
        
        current_paths = [collection_path]
        for _ in range(level):
            next_paths = []
            for path in current_paths:
                if path.is_dir():
                    for item in path.iterdir():
                        if item.is_dir() and not item.name.startswith('.'):
                            next_paths.append(item)
            current_paths = next_paths
            if not current_paths:
                break
        
        return current_paths
    
    async def preview_collection_structure(self, collection_path: Path, max_depth: int = 3) -> Dict[str, Any]:
        """Preview the structure of a collection"""
        try:
            structure = {
                "collection_path": str(collection_path),
                "max_depth": max_depth,
                "structure": self._build_structure_tree(collection_path, max_depth)
            }
            
            return structure
            
        except Exception as e:
            logger.error(f"Error previewing collection structure {collection_path}: {e}")
            return {
                "success": False,
                "error": str(e),
                "collection_path": str(collection_path)
            }
    
    def _build_structure_tree(self, path: Path, max_depth: int, current_depth: int = 0) -> Dict[str, Any]:
        """Build a tree structure of the collection"""
        if current_depth >= max_depth:
            return {"type": "truncated", "depth": current_depth}
        
        if not path.exists():
            return {"type": "missing", "path": str(path)}
        
        if path.is_file():
            return {
                "type": "file",
                "name": path.name,
                "size": path.stat().st_size,
                "path": str(path)
            }
        
        # It's a directory
        structure = {
            "type": "directory",
            "name": path.name,
            "path": str(path),
            "children": []
        }
        
        try:
            for item in sorted(path.iterdir()):
                if not item.name.startswith('.'):
                    child_structure = self._build_structure_tree(item, max_depth, current_depth + 1)
                    structure["children"].append(child_structure)
        except PermissionError:
            structure["error"] = "Permission denied"
        
        return structure
