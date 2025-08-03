from pathlib import Path
from typing import Callable, Dict, List, Optional
from fichero.manifest import ManifestProcessor
from fichero.tool_logger import get_tool_logger
import sys

tool_logger = get_tool_logger('batch')

class BatchProcessor:
    """Handles batch processing of files with progress tracking and manifest management"""
    
    def __init__(
        self,
        input_manifest: Path,
        output_folder: Path,
        process_name: str,
        processor_fn: Callable,
        batch_size: int = 100,
        base_folder: Path = None,
        use_source: bool = False
    ):
        self.input_manifest = Path(input_manifest)
        self.output_folder = Path(output_folder)
        self.base_folder = Path(base_folder) if base_folder else None
        self.process_name = process_name
        self.processor_fn = processor_fn
        self.batch_size = batch_size
        self.use_source = use_source
        
        # Setup folders and files
        self.output_folder.mkdir(parents=True, exist_ok=True)
        self.manifest_file = self.output_folder / f"{self.process_name}_manifest.jsonl"
        self.progress_file = self.output_folder / f"{self.process_name}_progress.jsonl"
        
        # Initialize manifest processors
        self.input_proc = ManifestProcessor(manifest_path=self.input_manifest, progress_file=None)
        self.output_proc = ManifestProcessor(manifest_path=self.manifest_file, progress_file=self.progress_file)
        
        # Initialize original order from input manifest
        self._initialize_original_order()
        
    def process(self) -> Dict:
        """Run the batch processing"""
        documents = []
        skipped_count = 0
        
        tool_logger.info("Checking files to process...")
        tool_logger.info(f"Base folder: {self.base_folder}")
        tool_logger.info(f"Input manifest: {self.input_manifest}")
        tool_logger.info(f"Output folder: {self.output_folder}")
        
        for doc in self.input_proc.stream_entries():
            # Skip directory entries
            if doc.get("type") == "directory":
                continue

            paths_to_process = []
            
            # Get document paths based on configuration
            if self.use_source and "source" in doc:
                paths_to_process.append(doc["source"])
            elif "outputs" in doc and doc["outputs"]:
                # Handle both string and dict outputs
                for out_path in doc["outputs"]:
                    if isinstance(out_path, str):
                        paths_to_process.append(out_path)
                    elif isinstance(out_path, dict) and "path" in out_path:
                        paths_to_process.append(out_path["path"])
            elif doc.get("path"):  # Fallback for direct paths
                paths_to_process.append(doc["path"])
                
            # Process collected paths
            for path in paths_to_process:
                # Skip if already successfully processed (not failed)
                if path in self.output_proc.entries:
                    entry = self.output_proc.entries[path]
                    # Only skip if the entry was successful and has outputs
                    if entry.get("success", False) and entry.get("outputs"):
                        skipped_count += 1
                        continue
                    # If failed or no outputs, reprocess it
                documents.append({"path": path})

        total_files = len(documents)
        stats = {
            "total": total_files + skipped_count,
            "skipped": skipped_count,
            "processed": 0,
            "failed": 0
        }

        tool_logger.info(f"Total files: {stats['total']}")
        tool_logger.info(f"Already processed: {stats['skipped']}")
        tool_logger.info(f"To process: {total_files}")

        if total_files == 0:
            return stats

        # Process files in batches
        tool_logger.progress(f"Processing {total_files} files...")
        
        try:
            current_batch = []
            
            for doc in documents:
                current_batch.append(doc)
                
                if len(current_batch) >= self.batch_size:
                    self._process_batch(current_batch, stats)
                    current_batch = []
                    self.output_proc.write_progress(stats)

            # Process remaining files
            if current_batch:
                self._process_batch(current_batch, stats)

            # Ensure final manifest is saved after all processing
            self.output_proc._write_manifest(self.manifest_file)
            self.output_proc.write_progress(stats)
            self._print_stats(stats)
            return stats

        except KeyboardInterrupt:
            tool_logger.warning("Processing interrupted by user. Saving progress...")
            self.output_proc._write_manifest(self.manifest_file)  # Save manifest
            self.output_proc.write_progress(stats)  # Save progress
            sys.exit(1)
        except Exception as e:
            tool_logger.error(f"Error occurred: {e}")
            self.output_proc.write_progress(stats)
            raise

    def _process_batch(self, batch: List[dict], stats: dict):
        """Process a batch of files"""
        for doc in batch:
            try:
                path = Path(doc["path"])
                
                # Use base folder directly without adding documents/ prefix
                if self.base_folder:
                    # Only add documents/ if it's not already in the base folder and path doesn't start with projects/
                    if "documents" not in str(self.base_folder) and not str(path).startswith("projects/"):
                        full_path = self.base_folder / "documents" / path
                    else:
                        full_path = self.base_folder / path
                else:
                    full_path = path

                # Only preserve extension if using source files (use_source=True)
                # When use_source=False, let the processing function determine the output extension
                if self.use_source and path.suffix:
                    full_path = full_path.with_suffix(path.suffix)
                
                result = self.processor_fn(str(full_path), self.output_folder)
                
                # Preserve source path in result
                if not result.get("source"):
                    result["source"] = str(path)
                    
                self.output_proc.save_entry(result)
                
                if result.get("skipped"):
                    stats["skipped"] += 1
                elif result.get("error"):
                    stats["failed"] += 1
                else:
                    stats["processed"] += 1
                    
            except Exception as e:
                tool_logger.error(f"Error processing {doc['path']}: {e}")
                stats["failed"] += 1

    def _initialize_original_order(self):
        """Initialize original order from input manifest"""
        self.output_proc.original_order = []
        for doc in self.input_proc.stream_entries():
            # Skip directory entries
            if doc.get("type") == "directory":
                continue

            paths_to_process = []
            
            # Get document paths based on configuration
            if self.use_source and "source" in doc:
                paths_to_process.append(doc["source"])
            elif "outputs" in doc and doc["outputs"]:
                # Handle both string and dict outputs
                for out_path in doc["outputs"]:
                    if isinstance(out_path, str):
                        paths_to_process.append(out_path)
                    elif isinstance(out_path, dict) and "path" in out_path:
                        paths_to_process.append(out_path["path"])
            elif doc.get("path"):  # Fallback for direct paths
                paths_to_process.append(doc["path"])
                
            # Add to original order
            for path in paths_to_process:
                # Normalize path key
                if "documents/" in path:
                    key = path.split("documents/", 1)[1]
                else:
                    key = path
                if key not in self.output_proc.original_order:
                    self.output_proc.original_order.append(key)

    def _print_stats(self, stats: dict):
        """Print final statistics"""
        tool_logger.success("Processing completed!")
        tool_logger.info(f"Total: {stats['total']}")
        tool_logger.info(f"Processed: {stats['processed']}")
        tool_logger.info(f"Skipped: {stats['skipped']}")
        tool_logger.info(f"Failed: {stats['failed']}")
