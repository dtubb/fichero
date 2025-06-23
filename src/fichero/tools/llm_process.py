import typer
from pathlib import Path
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
import srsly
import asyncio
import gc
import warnings

# Import utility modules with fallback for standalone execution
try:
    # Try absolute imports first (when run from app context)
    from fichero.tools.utils.manifest import ManifestProcessor
    from fichero.tools.utils.batch import BatchProcessor
    from fichero.tools.utils.files import ensure_dirs, get_relative_path, batch_check_files
    from fichero.tools.utils.segment_handler import SegmentHandler
    from fichero.tools.utils.progress import ProcessingProgress, ProgressTracker
    from fichero.tools.utils.llm_utils import (
        LLMBackend, ChatGPTBackend, ClaudeBackend, QwenBackend, LMStudioBackend, OllamaBackend,
        get_llm_backend, chunk_text_intelligently, process_with_iterative_refinement,
        load_prompt_config, process_document_with_llm, process_folder_with_llm, LLMProcessor
    )
    from fichero.tools.utils.hierarchy import DocumentHierarchy
    from fichero.tools.utils.tool_logger import get_tool_logger
except ImportError:
    # Fall back to relative imports (when run standalone)
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
    from utils.tool_logger import get_tool_logger

tool_logger = get_tool_logger('llm_process')

app = typer.Typer()

# Configuration is loaded per-execution from prompt config files

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
        
        tool_logger.info(f"Initialized LLMProcessScript:")
        tool_logger.info(f"  Input folder: {self.input_folder}")
        tool_logger.info(f"  Output folder: {self.output_folder}")
        tool_logger.info(f"  Hierarchical mode: {self.hierarchical}")
        tool_logger.info(f"  Folder mode: {self.folder_mode}")
        tool_logger.info(f"  Batch size: {self.batch_size}")
    
    def process_documents(self):
        """Process documents using LLM with configurable prompts"""
        try:
            if self.hierarchical:
                tool_logger.info("Running in hierarchical mode")
                hierarchy = DocumentHierarchy(self.input_folder)
                hierarchy.build_hierarchy()
                hierarchy.process_nodes(self.process_document)
            elif self.folder_mode:
                tool_logger.info("Running in folder mode")
                # Get all folders in input directory
                folders = [f for f in self.input_folder.iterdir() if f.is_dir()]
                if not folders:
                    tool_logger.warning("No folders found in input directory")
                    return
                
                tool_logger.info(f"Found {len(folders)} folders to process")
                for folder in folders:
                    tool_logger.info(f"Processing folder: {folder}")
                    # Get all text files in folder
                    files = list(folder.glob("**/*.txt"))
                    if not files:
                        tool_logger.warning(f"No text files found in {folder}")
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
                            tool_logger.error(f"Error reading {file_path}: {e}")
                            continue
                    
                    if not files_data:
                        tool_logger.warning(f"No valid files found in {folder}")
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
                tool_logger.info("Running in file-level mode")
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
                tool_logger.info(f"Final manifest written to: {self.manifest_proc.manifest_path}")
            
            # Clean up LLM backend resources
            if hasattr(self.llm, 'cleanup'):
                self.llm.cleanup()
    
    def process_document(self, file_path: Path, output_path: Path) -> Optional[Path]:
        """Process a single document"""
        try:
            # Use SegmentHandler for consistent path handling
            rel_path = SegmentHandler.get_relative_path(file_path)
            tool_logger.info(f"Processing document: {rel_path}")
            
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
            
            tool_logger.info(f"Saved result to: {output_path}")
            return output_path
            
        except Exception as e:
            tool_logger.error(f"Error processing {file_path}: {str(e)}")
            return None

def create_llm_backend_with_cli_keys(
    backend_type: str,
    model_name: str,
    api_url: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: int = 1000,
    openai_api_key: Optional[str] = None,
    qwen_api_key: Optional[str] = None,
    claude_api_key: Optional[str] = None
) -> LLMBackend:
    """Create LLM backend with API keys from CLI arguments"""
    if backend_type in ["chatgpt", "openai"]:
        return ChatGPTBackend(model_name, openai_api_key, temperature, max_tokens)
    elif backend_type in ["claude", "anthropic"]:
        return ClaudeBackend(model_name, claude_api_key, temperature, max_tokens)
    elif backend_type == "qwen":
        return QwenBackend(model_name, qwen_api_key, temperature, max_tokens)
    elif backend_type == "lmstudio":
        api_url = api_url or "http://localhost:1234"
        return LMStudioBackend(model_name, api_url, temperature, max_tokens)
    elif backend_type == "ollama":
        return OllamaBackend(model_name, temperature, max_tokens)
    else:
        raise ValueError(f"Unsupported backend type: {backend_type}")

def process_documents_batch(
    source_folder: Path,
    source_manifest: Path,
    output_folder: Path,
    prompt_config: Path,
    folder_mode: bool = True,
    **kwargs
) -> dict:
    """
    Process transcribed documents through configurable LLM pipeline for catalogue generation - importable function
    
    Args:
        source_folder: Input folder containing transcribed documents
        source_manifest: Input manifest file
        output_folder: Output folder for LLM results
        prompt_config: JSONL file containing prompt configuration
        folder_mode: Process all files in a folder together as one document
        
    Returns:
        Processing statistics dictionary
    """
    llm = None
    try:
        # Handle case where prompt_config might be passed as boolean instead of Path
        if isinstance(prompt_config, bool):
            tool_logger.error(f"prompt_config parameter is boolean ({prompt_config}) instead of Path. This is likely a configuration error.")
            return {
                "error": f"prompt_config parameter is boolean ({prompt_config}) instead of Path",
                "success": False
            }
        
        # Validate prompt_config is a Path
        if not isinstance(prompt_config, Path):
            tool_logger.error(f"prompt_config parameter is {type(prompt_config)} instead of Path: {prompt_config}")
            return {
                "error": f"prompt_config parameter is {type(prompt_config)} instead of Path",
                "success": False
            }
        
        # Check if prompt_config file exists
        if not prompt_config.exists():
            tool_logger.error(f"Prompt config file not found: {prompt_config}")
            return {
                "error": f"Prompt config file not found: {prompt_config}",
                "success": False
            }
        
        # Load prompt configuration
        tool_logger.info("Loading prompt configuration...")
        config = load_prompt_config(prompt_config)
        tool_logger.info(f"Configuration loaded: {config.get('name', 'unnamed')}")
        tool_logger.info(f"Description: {config.get('description', 'No description')}")
        tool_logger.info(f"Steps: {len(config.get('steps', []))}")
        tool_logger.info(f"Mode: {'Folder-level' if folder_mode else 'File-level'} processing")
        
        # Get max_tokens from config
        max_tokens = config.get("llm", {}).get("max_tokens", 1000)
        tool_logger.info(f"Using max_tokens from config: {max_tokens}")
        
        # Initialize LLM backend from config
        tool_logger.info("Initializing LLM backend...")
        llm = get_llm_backend(config)
        
        # Initialize LLM processor
        processor = LLMProcessScript(
            input_folder=source_folder,
            output_folder=output_folder,
            prompt_config=config,
            llm=llm,
            max_tokens=max_tokens,
            input_manifest=source_manifest,
            hierarchical=False,
            folder_mode=folder_mode,
            batch_size=10
        )
        
        processor.process_documents()
        
        # Return basic stats
        return {
            "processed_folders" if folder_mode else "processed_files": 1,
            "success": True
        }
        
    except Exception as e:
        tool_logger.error(f"Error in process_documents_batch: {str(e)}")
        return {
            "error": str(e),
            "success": False
        }
    finally:
        # Clean up LLM backend resources
        if llm and hasattr(llm, 'cleanup'):
            llm.cleanup()

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
    max_depth: Annotated[int, typer.Option(help="Maximum depth for hierarchical processing")] = 3,
    openai_api_key: Annotated[Optional[str], typer.Option("--openai-api-key", help="OpenAI API key (overrides shared data and env var)")] = None,
    qwen_api_key: Annotated[Optional[str], typer.Option("--qwen-api-key", help="Qwen API key (overrides shared data and env var)")] = None,
    claude_api_key: Annotated[Optional[str], typer.Option("--claude-api-key", help="Claude API key (overrides shared data and env var)")] = None,
):
    """Process documents using LLM with configurable prompts
    
    API keys are resolved using three-tier fallback:
    1. CLI argument (highest priority - for development/testing)
    2. Shared data from app settings (production use)
    3. Environment variable (fallback)
    
    In folder mode, all files in a folder are combined and processed together,
    with page numbers preserved. This is useful for multi-page documents.
    
    In hierarchical mode, documents are processed according to their folder structure,
    with support for level-specific processing.
    """
    llm = None
    try:
        # For CLI usage, use the full implementation with all parameters
        # Load prompt configuration
        tool_logger.info("Loading prompt configuration...")
        config = load_prompt_config(prompt_config)
        tool_logger.info(f"Configuration loaded: {config.get('name', 'unnamed')}")
        tool_logger.info(f"Description: {config.get('description', 'No description')}")
        tool_logger.info(f"Steps: {len(config.get('steps', []))}")
        tool_logger.info(f"Mode: {'Hierarchical' if hierarchical else 'Folder-level' if folder_mode else 'File-level'} processing")
        
        # Get max_tokens from config if not specified
        if max_tokens is None:
            max_tokens = config.get("llm", {}).get("max_tokens", 1000)
            tool_logger.info(f"Using max_tokens from config: {max_tokens}")
        else:
            tool_logger.info(f"Using max_tokens from command line: {max_tokens}")
        
        # Initialize LLM backend
        tool_logger.info("Initializing LLM backend...")
        if "llm" in config:
            tool_logger.info("Using LLM settings from configuration file")
            # For config-based LLM, we need to pass CLI keys to override any config keys
            llm_config = config.copy()
            
            # Override API keys in config with CLI arguments if provided
            if "llm" in llm_config:
                if openai_api_key:
                    llm_config["llm"]["openai_api_key"] = openai_api_key
                if qwen_api_key:
                    llm_config["llm"]["qwen_api_key"] = qwen_api_key
                if claude_api_key:
                    llm_config["llm"]["claude_api_key"] = claude_api_key
            
            llm = get_llm_backend(llm_config)
        else:
            tool_logger.info("Using LLM settings from command line")
            llm = create_llm_backend_with_cli_keys(
                backend_type=backend_type,
                model_name=model_name,
                api_url=api_url,
                temperature=temperature,
                max_tokens=max_tokens,
                openai_api_key=openai_api_key,
                qwen_api_key=qwen_api_key,
                claude_api_key=claude_api_key
            )
        
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
    finally:
        # Clean up LLM backend resources
        if llm and hasattr(llm, 'cleanup'):
            llm.cleanup()

def cleanup_resources():
    """Clean up all resources to prevent ResourceWarnings"""
    try:
        import asyncio
        import gc
        import warnings
        
        # Suppress ResourceWarnings during cleanup
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            
            # Get the current event loop if it exists
            try:
                loop = asyncio.get_running_loop()
                # Cancel all pending tasks
                pending_tasks = asyncio.all_tasks(loop)
                if pending_tasks:
                    for task in pending_tasks:
                        if not task.done():
                            task.cancel()
                    
                    # Wait briefly for tasks to cancel
                    try:
                        loop.run_until_complete(asyncio.wait(pending_tasks, timeout=1.0))
                    except Exception:
                        pass
                
                # Close the loop if it's not the main loop
                if not loop.is_closed():
                    loop.close()
                    
            except RuntimeError:
                # No running event loop
                pass
            
            # Force garbage collection to clean up any remaining resources
            gc.collect()
            
    except Exception:
        # Ignore cleanup errors
        pass

if __name__ == "__main__":
    try:
        typer.run(process_documents)
    finally:
        cleanup_resources() 