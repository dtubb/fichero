import typer
from pathlib import Path
from rich.console import Console
from typing_extensions import Annotated
from langchain_ollama.chat_models import ChatOllama
import yaml
import os
from langchain.schema import HumanMessage
import openai
from typing import Dict, List, Optional
import json
import requests
from datetime import datetime
import logging
import srsly

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
console = Console()

# Import utility modules
from utils.manifest import ManifestProcessor
from utils.batch import BatchProcessor
from utils.files import ensure_dirs, get_relative_path, batch_check_files
from utils.segment_handler import SegmentHandler
from utils.progress import ProcessingProgress, ProgressTracker
from utils.llm_utils import (
    LLMBackend, ChatGPTBackend, ClaudeBackend, QwenBackend, LMStudioBackend, OllamaBackend,
    get_llm_backend, chunk_text_intelligently, process_with_iterative_refinement,
    load_prompt_config, process_document_with_llm, process_folder_with_llm, LLMProcessor
)
from utils.hierarchy import DocumentHierarchy

app = typer.Typer()

# Load configuration
with open("project.yml", "r") as config_file:
    config = yaml.safe_load(config_file)

class LLMProcessScript:
    def __init__(
        self,
        input_folder: Path,
        output_folder: Path,
        prompt_config: Dict,
        llm: LLMBackend,
        max_tokens: int,
        input_manifest: Optional[Path] = None,
        hierarchical: bool = False,
        folder_mode: bool = False,
        batch_size: int = 10
    ):
        # Initialize using utility class
        processor = LLMProcessor(
            input_folder=input_folder,
            output_folder=output_folder,
            prompt_config=prompt_config,
            llm=llm,
            max_tokens=max_tokens,
            input_manifest=input_manifest
        )
        
        # Copy attributes from processor
        self.input_folder = processor.input_folder
        self.output_folder = processor.output_folder
        self.prompt_config = processor.prompt_config
        self.llm = processor.llm
        self.max_tokens = processor.max_tokens
        self.input_manifest = input_manifest
        self.hierarchical = hierarchical
        self.folder_mode = folder_mode
        self.batch_size = batch_size
        
        # Ensure output directories exist
        ensure_dirs(self.output_folder / "steps")
        ensure_dirs(self.output_folder / "chunks")
        ensure_dirs(self.output_folder / "documents")
        
        # Initialize manifest processor for output
        self.manifest_proc = ManifestProcessor(
            manifest_path=self.output_folder / "llm_process_manifest.jsonl",
            progress_file=self.output_folder / "llm_process_progress.jsonl"
        )
        
        logger.info(f"Initialized LLMProcessScript:")
        logger.info(f"  Input folder: {self.input_folder}")
        logger.info(f"  Output folder: {self.output_folder}")
        logger.info(f"  Hierarchical mode: {self.hierarchical}")
        logger.info(f"  Folder mode: {self.folder_mode}")
        logger.info(f"  Batch size: {self.batch_size}")
    
    def process_documents(self):
        """Process documents using LLM with configurable prompts"""
        try:
            if self.hierarchical:
                logger.info("Running in hierarchical mode")
                hierarchy = DocumentHierarchy(self.input_folder)
                hierarchy.build_hierarchy()
                hierarchy.process_nodes(self.process_document)
            elif self.folder_mode:
                logger.info("Running in folder mode")
                # Get all folders in input directory
                folders = [f for f in self.input_folder.iterdir() if f.is_dir()]
                if not folders:
                    logger.warning("No folders found in input directory")
                    return
                
                logger.info(f"Found {len(folders)} folders to process")
                for folder in folders:
                    logger.info(f"Processing folder: {folder}")
                    # Get all text files in folder
                    files = list(folder.glob("**/*.txt"))
                    if not files:
                        logger.warning(f"No text files found in {folder}")
                        continue
                    
                    # Build file data list
                    files_data = []
                    for idx, file_path in enumerate(sorted(files)):
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                            files_data.append({
                                'path': file_path,
                                'content': content,
                                'page_num': idx + 1
                            })
                        except Exception as e:
                            logger.error(f"Error reading {file_path}: {e}")
                            continue
                    
                    if not files_data:
                        logger.warning(f"No valid files found in {folder}")
                        continue
                    
                    # Process folder with all files
                    result = process_folder_with_llm(
                        folder_path=folder,
                        files=files_data,
                        llm=self.llm,
                        prompt_config=self.prompt_config,
                        max_tokens=self.max_tokens,
                        output_folder=self.output_folder
                    )
                    
                    # Save result using manifest processor
                    if hasattr(self, 'manifest_proc'):
                        # Use just the folder name for source and outputs
                        self.manifest_proc.save_entry({
                            "source": folder.name,
                            "outputs": [f"{folder.name}_summary.json"],
                            "type": "folder",
                            "files_processed": len(files_data),
                            "model": self.llm.model_name
                        })
            else:
                logger.info("Running in file-level mode")
                # Use BatchProcessor for consistent file handling
                processor = BatchProcessor(
                    input_manifest=self.input_manifest,
                    output_folder=self.output_folder,
                    process_name="llm_process",
                    processor_fn=self.process_document,
                    batch_size=self.batch_size,
                    base_folder=self.input_folder
                )
                processor.process()
                # BatchProcessor handles its own manifest, so return early
                return
        finally:
            # Ensure final manifest is written for hierarchical and folder modes
            if hasattr(self, 'manifest_proc'):
                self.manifest_proc._write_manifest(self.manifest_proc.manifest_path)
                logger.info(f"Final manifest written to: {self.manifest_proc.manifest_path}")
    
    def process_document(self, file_path: Path, output_path: Path) -> Optional[Path]:
        """Process a single document"""
        try:
            # Use SegmentHandler for consistent path handling
            rel_path = SegmentHandler.get_relative_path(file_path)
            logger.info(f"Processing document: {rel_path}")
            
            # Read file content
            with open(file_path, 'r', encoding='utf-8') as f:
                text_content = f.read()
            
            # Process with LLM
            result = process_document_with_llm(
                doc_path=file_path,
                text_content=text_content,
                llm=self.llm,
                prompt_config=self.prompt_config,
                max_tokens=self.max_tokens,
                output_folder=self.output_folder
            )
            
            # Save result to manifest
            output_path = self.output_folder / "documents" / rel_path.parent / f"{rel_path.stem}_summary.json"
            ensure_dirs(output_path)
            
            # Save result
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            # Use consistent manifest entry format with just the file name
            self.manifest_proc.save_entry({
                "source": rel_path.name,
                "outputs": [f"{rel_path.stem}_summary.json"],
                "type": "document",
                "text_length": len(text_content),
                "model": self.llm.model_name
            })
            
            logger.info(f"Saved result to: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error processing {file_path}: {str(e)}")
            return None

def process_documents(
    input_folder: Annotated[Path, typer.Argument(help="Input folder containing transcribed documents")],
    input_manifest: Annotated[Path, typer.Argument(help="Input manifest file")],
    output_folder: Annotated[Path, typer.Argument(help="Output folder for LLM results")],
    prompt_config: Annotated[Path, typer.Option(help="JSONL file containing prompt configuration")] = Path("prompts/prompt_config.jsonl"),
    backend_type: Annotated[str, typer.Option(help="LLM backend type (chatgpt, lmstudio, ollama)")] = "ollama",
    model_name: Annotated[str, typer.Option(help="Model name")] = "mistral",
    api_url: Annotated[Optional[str], typer.Option(help="API URL for LMStudio")] = None,
    max_tokens: Annotated[Optional[int], typer.Option(help="Maximum tokens per chunk (overrides config if specified)")] = None,
    temperature: Annotated[float, typer.Option(help="Temperature for generation")] = 0.0,
    batch_size: Annotated[int, typer.Option(help="Number of documents to process in each batch")] = 10,
    folder_mode: Annotated[bool, typer.Option(help="Process all files in a folder together as one document")] = False,
    hierarchical: Annotated[bool, typer.Option(help="Process documents in hierarchical order")] = False,
    max_depth: Annotated[int, typer.Option(help="Maximum depth for hierarchical processing")] = 3
):
    """Process documents using LLM with configurable prompts
    
    In folder mode, all files in a folder are combined and processed together,
    with page numbers preserved. This is useful for multi-page documents.
    
    In hierarchical mode, documents are processed according to their folder structure,
    with support for level-specific processing.
    """
    
    # Load prompt configuration
    logger.info("Loading prompt configuration...")
    config = load_prompt_config(prompt_config)
    logger.info(f"Configuration loaded: {config.get('name', 'unnamed')}")
    logger.info(f"Description: {config.get('description', 'No description')}")
    logger.info(f"Steps: {len(config.get('steps', []))}")
    logger.info(f"Mode: {'Hierarchical' if hierarchical else 'Folder-level' if folder_mode else 'File-level'} processing")
    
    # Get max_tokens from config if not specified
    if max_tokens is None:
        max_tokens = config.get("llm", {}).get("max_tokens", 1000)
        logger.info(f"Using max_tokens from config: {max_tokens}")
    else:
        logger.info(f"Using max_tokens from command line: {max_tokens}")
    
    # Initialize LLM backend
    logger.info("Initializing LLM backend...")
    if "llm" in config:
        logger.info("Using LLM settings from configuration file")
        llm = get_llm_backend(config)
    else:
        logger.info("Using LLM settings from command line")
        llm = get_llm_backend(backend_type, model_name=model_name, api_url=api_url, temperature=temperature, max_tokens=max_tokens)
    
    # Initialize LLM processor
    processor = LLMProcessScript(
        input_folder=input_folder,
        output_folder=output_folder,
        prompt_config=config,
        llm=llm,
        max_tokens=max_tokens,
        input_manifest=input_manifest,
        hierarchical=hierarchical,
        folder_mode=folder_mode,
        batch_size=batch_size
    )
    
    processor.process_documents()

if __name__ == "__main__":
    typer.run(process_documents) 