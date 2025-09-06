"""
Processing Navigator for Fichero Library
Handles navigation through processing steps and viewing outputs
"""

import os
import json
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

@dataclass
class ProcessingStep:
    """Represents a processing step in the fiche workflow"""
    name: str
    path: Path
    description: str
    file_types: List[str]
    manifest_file: Optional[str] = None
    progress_file: Optional[str] = None

@dataclass
class ProcessingOutput:
    """Represents an output file from a processing step"""
    name: str
    path: Path
    size: int
    modified: datetime
    file_type: str
    step: str

class ProcessingNavigator:
    """Navigates through fiche processing steps and manages output viewing"""
    
    # Define the standard processing workflow steps
    PROCESSING_STEPS = [
        ProcessingStep(
            name="documents",
            path=Path("documents"),
            description="Original input documents (JPG, PDF, etc.)",
            file_types=[".jpg", ".jpeg", ".png", ".pdf", ".tiff", ".tif"]
        ),
        ProcessingStep(
            name="rotated",
            path=Path("assets/rotated/documents"),
            description="Rotated images for better orientation",
            file_types=[".jpg", ".jpeg", ".png"],
            manifest_file="rotate_manifest.jsonl",
            progress_file="rotate_progress.jsonl"
        ),
        ProcessingStep(
            name="crops",
            path=Path("assets/crops/documents"),
            description="Cropped images to remove borders",
            file_types=[".jpg", ".jpeg", ".png"],
            manifest_file="crop_manifest.jsonl",
            progress_file="crop_progress.jsonl"
        ),
        ProcessingStep(
            name="background_removed",
            path=Path("assets/background_removed/documents"),
            description="Images with background removed",
            file_types=[".png"],
            manifest_file="background_removed_manifest.jsonl",
            progress_file="background_removed_progress.jsonl"
        ),
        ProcessingStep(
            name="enhanced",
            path=Path("assets/enhanced/documents"),
            description="Enhanced images for better quality",
            file_types=[".jpg", ".jpeg", ".png"],
            manifest_file="enhance_manifest.jsonl",
            progress_file="enhance_progress.jsonl"
        ),
        ProcessingStep(
            name="splits",
            path=Path("assets/splits/documents"),
            description="Split images into smaller parts",
            file_types=[".jpg", ".jpeg", ".png"],
            manifest_file="split_manifest.jsonl",
            progress_file="split_progress.jsonl"
        ),
        ProcessingStep(
            name="segments",
            path=Path("assets/segments/documents"),
            description="Segmented images for better processing",
            file_types=[".jpg", ".jpeg", ".png"],
            manifest_file="segment_manifest.jsonl",
            progress_file="segment_progress.jsonl"
        ),
        ProcessingStep(
            name="transcriptions",
            path=Path("assets/transcriptions/documents"),
            description="OCR transcriptions of documents",
            file_types=[".txt"],
            manifest_file="transcription_manifest.jsonl",
            progress_file="transcription_progress.jsonl"
        ),
        ProcessingStep(
            name="segmented_transcriptions",
            path=Path("assets/segmented_transcriptions/documents"),
            description="Transcriptions segmented by image parts",
            file_types=[".txt"]
        ),
        ProcessingStep(
            name="recombined",
            path=Path("assets/recombined/documents"),
            description="Recombined text from segments",
            file_types=[".txt"],
            manifest_file="recombine_manifest.jsonl"
        ),
        ProcessingStep(
            name="llm_catalogue",
            path=Path("assets/llm_catalogue"),
            description="LLM processing results and analysis",
            file_types=[".json", ".jsonl"],
            manifest_file="llm_process_manifest.jsonl"
        )
    ]
    
    def __init__(self, collection_path: Path):
        """Initialize navigator for a collection"""
        self.collection_path = Path(collection_path)
        self.steps = {step.name: step for step in self.PROCESSING_STEPS}
        
    def get_available_steps(self) -> List[ProcessingStep]:
        """Get list of processing steps that have content"""
        available_steps = []
        
        for step in self.PROCESSING_STEPS:
            step_path = self.collection_path / step.path
            if step_path.exists() and self._has_content(step_path):
                available_steps.append(step)
                
        return available_steps
    
    def _has_content(self, path: Path) -> bool:
        """Check if a path has any content files"""
        if not path.exists():
            return False
            
        # Check for files (not just directories)
        for item in path.rglob("*"):
            if item.is_file() and not item.name.startswith('.'):
                return True
        return False
    
    def get_step_outputs(self, step_name: str, collection_name: Optional[str] = None) -> List[ProcessingOutput]:
        """Get all output files from a specific processing step"""
        if step_name not in self.steps:
            return []
            
        step = self.steps[step_name]
        step_path = self.collection_path / step.path
        
        if not step_path.exists():
            return []
            
        outputs = []
        
        # If collection_name is specified, look in that subdirectory
        if collection_name:
            step_path = step_path / collection_name
            
        for file_path in step_path.rglob("*"):
            if file_path.is_file() and not file_path.name.startswith('.'):
                # Check if file type matches step requirements
                if file_path.suffix.lower() in step.file_types:
                    try:
                        stat = file_path.stat()
                        outputs.append(ProcessingOutput(
                            name=file_path.name,
                            path=file_path,
                            size=stat.st_size,
                            modified=datetime.fromtimestamp(stat.st_mtime),
                            file_type=file_path.suffix.lower(),
                            step=step_name
                        ))
                    except OSError as e:
                        logger.warning(f"Could not stat file {file_path}: {e}")
                        
        return sorted(outputs, key=lambda x: x.name)
    
    def get_collection_names(self, step_name: str) -> List[str]:
        """Get list of collection names (subdirectories) in a processing step"""
        if step_name not in self.steps:
            return []
            
        step = self.steps[step_name]
        step_path = self.collection_path / step.path
        
        if not step_path.exists():
            return []
            
        collection_names = []
        for item in step_path.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                collection_names.append(item.name)
                
        return sorted(collection_names)
    
    def get_step_manifest(self, step_name: str) -> Optional[Dict[str, Any]]:
        """Get manifest information for a processing step"""
        if step_name not in self.steps:
            return None
            
        step = self.steps[step_name]
        if not step.manifest_file:
            return None
            
        manifest_path = self.collection_path / step.path.parent / step.manifest_file
        if not manifest_path.exists():
            return None
            
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                # Read JSONL file
                manifest_data = []
                for line in f:
                    line = line.strip()
                    if line:
                        manifest_data.append(json.loads(line))
                return {
                    "file": str(manifest_path),
                    "entries": manifest_data,
                    "count": len(manifest_data)
                }
        except Exception as e:
            logger.error(f"Error reading manifest {manifest_path}: {e}")
            return None
    
    def get_step_progress(self, step_name: str) -> Optional[Dict[str, Any]]:
        """Get progress information for a processing step"""
        if step_name not in self.steps:
            return None
            
        step = self.steps[step_name]
        if not step.progress_file:
            return None
            
        progress_path = self.collection_path / step.path.parent / step.progress_file
        if not progress_path.exists():
            return None
            
        try:
            with open(progress_path, 'r', encoding='utf-8') as f:
                # Read JSONL file
                progress_data = []
                for line in f:
                    line = line.strip()
                    if line:
                        progress_data.append(json.loads(line))
                return {
                    "file": str(progress_path),
                    "entries": progress_data,
                    "count": len(progress_data)
                }
        except Exception as e:
            logger.error(f"Error reading progress {progress_path}: {e}")
            return None
    
    def search_across_steps(self, query: str, file_types: Optional[List[str]] = None) -> List[ProcessingOutput]:
        """Search for files across all processing steps"""
        results = []
        query_lower = query.lower()
        
        for step_name in self.steps:
            outputs = self.get_step_outputs(step_name)
            
            for output in outputs:
                # Filter by file type if specified
                if file_types and output.file_type not in file_types:
                    continue
                    
                # Search in filename
                if query_lower in output.name.lower():
                    results.append(output)
                    
        return sorted(results, key=lambda x: (x.step, x.name))
    
    def get_file_content_preview(self, output: ProcessingOutput, max_lines: int = 10) -> Optional[str]:
        """Get a preview of file content for text files"""
        if output.file_type not in ['.txt', '.json', '.jsonl']:
            return None
            
        try:
            with open(output.path, 'r', encoding='utf-8') as f:
                if output.file_type == '.txt':
                    lines = f.readlines()
                    preview_lines = lines[:max_lines]
                    preview = ''.join(preview_lines)
                    if len(lines) > max_lines:
                        preview += f"\n... ({len(lines) - max_lines} more lines)"
                    return preview
                elif output.file_type in ['.json', '.jsonl']:
                    content = f.read()
                    # Try to parse and pretty-print JSON
                    try:
                        if output.file_type == '.jsonl':
                            # For JSONL, show first few lines
                            lines = content.strip().split('\n')
                            preview_lines = lines[:max_lines]
                            preview = '\n'.join(preview_lines)
                            if len(lines) > max_lines:
                                preview += f"\n... ({len(lines) - max_lines} more lines)"
                        else:
                            # For JSON, pretty-print
                            data = json.loads(content)
                            preview = json.dumps(data, indent=2, ensure_ascii=False)
                    except json.JSONDecodeError:
                        preview = content[:1000] + "..." if len(content) > 1000 else content
                    return preview
        except Exception as e:
            logger.error(f"Error reading file {output.path}: {e}")
            return None
    
    def get_processing_summary(self) -> Dict[str, Any]:
        """Get a summary of all processing steps and their status"""
        summary = {
            "collection_path": str(self.collection_path),
            "steps": {},
            "total_files": 0,
            "available_steps": []
        }
        
        for step in self.PROCESSING_STEPS:
            step_path = self.collection_path / step.path
            has_content = self._has_content(step_path)
            
            if has_content:
                outputs = self.get_step_outputs(step.name)
                summary["steps"][step.name] = {
                    "name": step.name,
                    "description": step.description,
                    "path": str(step_path),
                    "file_count": len(outputs),
                    "file_types": step.file_types,
                    "has_manifest": step.manifest_file is not None,
                    "has_progress": step.progress_file is not None
                }
                summary["total_files"] += len(outputs)
                summary["available_steps"].append(step.name)
            else:
                summary["steps"][step.name] = {
                    "name": step.name,
                    "description": step.description,
                    "path": str(step_path),
                    "file_count": 0,
                    "file_types": step.file_types,
                    "has_manifest": step.manifest_file is not None,
                    "has_progress": step.progress_file is not None,
                    "status": "not_processed"
                }
                
        return summary
