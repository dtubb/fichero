from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
import json
from fichero.batch import BatchProcessor
from fichero.manifest import ManifestProcessor
from fichero.progress import ProcessingProgress, ProgressTracker
from fichero.files import ensure_dirs
from fichero.segment_handler import SegmentHandler

# Support both standalone CLI usage and workflow executor imports
try:
    # When imported by workflow executor (absolute imports work)
    from fichero.tools.utils.tool_logger import get_tool_logger
except ImportError:
    # When run as standalone script (relative imports work)
    from tool_logger import get_tool_logger

tool_logger = get_tool_logger('hierarchy')

class HierarchyNode:
    """Represents a node in the document hierarchy"""
    def __init__(self, path: Path, level: int = 0):
        self.path = path
        self.level = level
        self.children: List[HierarchyNode] = []
        self.files: List[Dict] = []
        self.metadata: Dict = {}
        
    def add_child(self, child: 'HierarchyNode'):
        self.children.append(child)
        
    def add_file(self, file_data: Dict):
        self.files.append(file_data)
        
    def to_dict(self) -> Dict:
        return {
            "path": str(self.path),
            "level": self.level,
            "children": [child.to_dict() for child in self.children],
            "files": self.files,
            "metadata": self.metadata
        }

class DocumentHierarchy:
    """Manages hierarchical document processing"""
    def __init__(self, base_path: Path, output_folder: Path, process_name: str = "hierarchy"):
        self.base_path = Path(base_path)
        self.output_folder = Path(output_folder)
        self.process_name = process_name
        self.root = HierarchyNode(self.base_path)
        
        # Ensure output folder exists
        self.output_folder.mkdir(parents=True, exist_ok=True)
        
        # Initialize manifest and progress tracking
        self.manifest_file = self.output_folder / f"{process_name}_manifest.jsonl"
        self.progress_file = self.output_folder / f"{process_name}_progress.jsonl"
        
        self.manifest_proc = ManifestProcessor(
            manifest_path=self.manifest_file,
            progress_file=self.progress_file
        )
        
        self.progress = ProcessingProgress(
            progress_file=self.progress_file,
            manifest_file=self.manifest_file
        )
        
        tool_logger.info(f"Initialized DocumentHierarchy:")
        tool_logger.info(f"  Base path: {self.base_path}")
        tool_logger.info(f"  Output folder: {self.output_folder}")
        tool_logger.info(f"  Process name: {self.process_name}")
        
    def build_hierarchy(self, max_depth: int = 3) -> HierarchyNode:
        """Build document hierarchy from directory structure"""
        def _build_node(current_path: Path, level: int, parent: HierarchyNode) -> None:
            if level >= max_depth:
                return
                
            for item in sorted(current_path.iterdir()):
                if item.is_dir():
                    child = HierarchyNode(item, level + 1)
                    parent.add_child(child)
                    _build_node(item, level + 1, child)
                elif item.is_file():
                    rel_path = SegmentHandler.get_relative_path(item)
                    parent.add_file({
                        "path": str(rel_path),
                        "name": item.name,
                        "type": item.suffix[1:] if item.suffix else None
                    })
        
        _build_node(self.base_path, 0, self.root)
        tool_logger.info(f"Built hierarchy with max depth {max_depth}")
        return self.root
        
    def process_hierarchy(
        self,
        process_fn: Callable[[Path, List[Dict], Path], Dict],
        output_folder: Path,
        file_types: Optional[Dict] = None,
        level_processors: Optional[Dict[int, Callable]] = None,
        batch_size: int = 100
    ) -> Dict:
        """Process documents in hierarchical order with progress tracking"""
        results = {
            "processed": 0,
            "failed": 0,
            "skipped": 0,
            "hierarchy_results": []
        }
        
        # Initialize batch processor for file-level processing
        batch_processor = BatchProcessor(
            input_manifest=self.manifest_file,
            output_folder=output_folder,
            process_name=self.process_name,
            processor_fn=process_fn,
            batch_size=batch_size
        )
        
        def _process_node(node: HierarchyNode, current_output: Path) -> Dict:
            rel_path = SegmentHandler.get_relative_path(node.path)
            node_result = {
                "path": str(rel_path),
                "level": node.level,
                "success": True,
                "children": [],
                "files": []
            }
            
            # Process files at this level using batch processor
            if node.files:
                files_to_process = []
                for file_data in node.files:
                    if file_types and file_data["type"] not in file_types:
                        continue
                    files_to_process.append(file_data)
                
                if files_to_process:
                    tool_logger.info(f"Processing {len(files_to_process)} files in {rel_path}")
                    # Process files in batches
                    batch_results = batch_processor.process_batch(files_to_process)
                    node_result["files"].extend(batch_results)
                    
                    # Update statistics
                    for result in batch_results:
                        if result.get("skipped"):
                            results["skipped"] += 1
                        elif result.get("error"):
                            results["failed"] += 1
                            node_result["success"] = False
                        else:
                            results["processed"] += 1
            
            # Process children
            for child in node.children:
                child_output = current_output / child.path.name
                child_result = _process_node(child, child_output)
                node_result["children"].append(child_result)
                
                if not child_result["success"]:
                    node_result["success"] = False
            
            # Apply level-specific processing if defined
            if level_processors and node.level in level_processors:
                try:
                    tool_logger.info(f"Applying level {node.level} processor to {rel_path}")
                    level_result = level_processors[node.level](
                        node.path,
                        node_result["files"],
                        current_output
                    )
                    node_result["level_processing"] = level_result
                except Exception as e:
                    tool_logger.error(f"Error in level processing for {rel_path}: {e}")
                    node_result["success"] = False
                    node_result["level_processing_error"] = str(e)
            
            return node_result
        
        # Start processing from root with progress tracking
        with ProgressTracker(
            total=len(self.root.files),
            task_name=f"{self.process_name.title()} files",
            progress_fields=results
        ) as tracker:
            root_result = _process_node(self.root, output_folder)
            results["hierarchy_results"] = root_result
            
            # Update progress
            tracker.update(
                advance=results["processed"] + results["skipped"] + results["failed"],
                **results
            )
        
        # Save final progress
        self.progress.save_progress(results, results["processed"])
        
        tool_logger.info(f"Hierarchy processing completed:")
        tool_logger.info(f"  Processed: {results['processed']}")
        tool_logger.info(f"  Skipped: {results['skipped']}")
        tool_logger.info(f"  Failed: {results['failed']}")
        
        return results
        
    def save_hierarchy(self, output_path: Path) -> None:
        """Save hierarchy structure to JSON file"""
        hierarchy_data = self.root.to_dict()
        with open(output_path, 'w') as f:
            json.dump(hierarchy_data, f, indent=2)
        tool_logger.info(f"Saved hierarchy to {output_path}")
        
    @classmethod
    def load_hierarchy(cls, input_path: Path, output_folder: Path) -> 'DocumentHierarchy':
        """Load hierarchy from JSON file"""
        with open(input_path, 'r') as f:
            hierarchy_data = json.load(f)
        
        hierarchy = cls(Path(hierarchy_data["path"]), output_folder)
        hierarchy.root = cls._dict_to_node(hierarchy_data)
        return hierarchy
        
    @staticmethod
    def _dict_to_node(data: Dict) -> HierarchyNode:
        """Convert dictionary back to HierarchyNode"""
        node = HierarchyNode(Path(data["path"]), data["level"])
        node.files = data["files"]
        node.metadata = data["metadata"]
        
        for child_data in data["children"]:
            child_node = DocumentHierarchy._dict_to_node(child_data)
            node.add_child(child_node)
            
        return node 