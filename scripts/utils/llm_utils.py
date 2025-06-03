from typing import Dict, List, Optional, Any, Union
from pathlib import Path
import json
from datetime import datetime
from rich.console import Console
import os
import requests
from langchain.schema import HumanMessage
from langchain_ollama.chat_models import ChatOllama
import openai
import anthropic
from http import HTTPStatus
import dashscope
from dashscope import Generation
import logging
from .segment_handler import SegmentHandler
from .files import ensure_dirs, get_relative_path
from .manifest import ManifestProcessor
import srsly
import asyncio

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
console = Console()

# Default configuration values
DEFAULT_MAX_TOKENS = 3072

class LLMBackend:
    """Base class for LLM backends. max_tokens is always set from config, argument, or defaults to DEFAULT_MAX_TOKENS."""
    def __init__(self, model_name: str, temperature: float = 0.0, max_tokens: int = DEFAULT_MAX_TOKENS):
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens

    def process_text(self, text: str, prompt: str) -> str:
        raise NotImplementedErrorno

class ChatGPTBackend(LLMBackend):
    def __init__(self, model_name: str, api_key: Optional[str] = None, temperature: float = 0.0, max_tokens: int = DEFAULT_MAX_TOKENS):
        super().__init__(model_name, temperature, max_tokens)
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key must be provided via argument or OPENAI_API_KEY env var.")
        import openai
        self.client = openai.OpenAI(api_key=self.api_key)
        # Also create async client for concurrent processing
        self.async_client = openai.AsyncOpenAI(api_key=self.api_key)

    def process_text(self, text: str, prompt: str) -> str:
        try:
            max_tokens = min(self.max_tokens, 4096)  # GPT-3.5-turbo's limit
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": f"{prompt}\n\n{text}"}
                ],
                max_tokens=max_tokens,
                temperature=self.temperature
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            console.print(f"[red]Error invoking ChatGPT: {e}")
            return ""

    async def process_text_async(self, text: str, prompt: str) -> str:
        """Async version of process_text for concurrent processing"""
        try:
            max_tokens = min(self.max_tokens, 4096)  # GPT-3.5-turbo's limit
            response = await self.async_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": f"{prompt}\n\n{text}"}
                ],
                max_tokens=max_tokens,
                temperature=self.temperature
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            console.print(f"[red]Error invoking ChatGPT async: {e}")
            return ""

    async def process_pages_batch(self, pages: List[Dict], prompt: str, batch_size: int = 10) -> List[Dict]:
        """Process multiple pages concurrently with rate limiting"""
        semaphore = asyncio.Semaphore(batch_size)
        
        async def process_page_with_limit(page_info: Dict) -> Dict:
            async with semaphore:
                page_num = page_info.get('page_num', 0)
                text = page_info.get('content', '')
                
                # Add page number to prompt
                page_prompt = f"{prompt}\n\nPage Number: {page_num}"
                
                result = await self.process_text_async(text, page_prompt)
                
                return {
                    'page_num': page_num,
                    'result': result,
                    'source_file': page_info.get('path', ''),
                    'timestamp': datetime.now().isoformat()
                }
        
        # Process all pages concurrently
        tasks = [process_page_with_limit(page) for page in pages]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions and return successful results
        successful_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                console.print(f"[red]Error processing page {pages[i].get('page_num', i)}: {result}")
            else:
                successful_results.append(result)
        
        return successful_results

class ClaudeBackend(LLMBackend):
    def __init__(self, model_name: str, api_key: Optional[str] = None, temperature: float = 0.0, max_tokens: int = DEFAULT_MAX_TOKENS):
        super().__init__(model_name, temperature, max_tokens)
        try:
            key = api_key or os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
            self.client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
        except ImportError:
            raise ImportError("Please install anthropic package: pip install anthropic")

    def process_text(self, text: str, prompt: str) -> str:
        try:
            response = self.client.messages.create(
                model=self.model_name,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                messages=[
                    {"role": "user", "content": f"{prompt}\n\n{text}"}
                ]
            )
            return response.content[0].text.strip()
        except Exception as e:
            console.print(f"[red]Error invoking Claude: {e}")
            return ""

class QwenBackend(LLMBackend):
    def __init__(self, model_name: str, api_key: Optional[str] = None, temperature: float = 0.0, max_tokens: int = DEFAULT_MAX_TOKENS):
        super().__init__(model_name, temperature, max_tokens)
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY")
        if not self.api_key:
            raise ValueError("Qwen API key required. Set DASHSCOPE_API_KEY or QWEN_API_KEY environment variable or pass api_key")

    def process_text(self, text: str, prompt: str) -> str:
        try:
            dashscope.api_key = self.api_key
            response = Generation.call(
                model=self.model_name,
                prompt=f"{prompt}\n\n{text}",
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            if response.status_code == HTTPStatus.OK:
                return response.output.text.strip()
            else:
                console.print(f"[red]Qwen API error: {response.code}: {response.message}")
                return ""
        except Exception as e:
            console.print(f"[red]Error invoking Qwen: {e}")
            return ""

class LMStudioBackend(LLMBackend):
    def __init__(self, model_name: str, api_url: str = "http://localhost:1234", temperature: float = 0.0, max_tokens: int = DEFAULT_MAX_TOKENS):
        super().__init__(model_name, temperature, max_tokens)
        self.api_url = api_url

    def process_text(self, text: str, prompt: str) -> str:
        try:
            response = requests.post(
                f"{self.api_url}/v1/chat/completions",
                json={
                    "model": self.model_name,
                    "messages": [
                        {"role": "system", "content": "You are a helpful assistant. This is a new conversation."},
                        {"role": "user", "content": f"{prompt}\n\n{text}"}
                    ],
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature
                },
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"].strip()
        except Exception as e:
            console.print(f"[red]Error invoking LMStudio: {e}")
            return ""

class OllamaBackend(LLMBackend):
    def __init__(self, model_name: str, temperature: float = 0.0, max_tokens: int = DEFAULT_MAX_TOKENS):
        super().__init__(model_name, temperature, max_tokens)
        self.llm = ChatOllama(model=model_name, format="json", num_ctx=1000, temperature=temperature)

    def process_text(self, text: str, prompt: str) -> str:
        try:
            response = self.llm.invoke([HumanMessage(content=f"{prompt}\n\n{text}")])
            if response:
                return response.content.strip()
            return ""
        except Exception as e:
            console.print(f"[red]Error invoking Ollama: {e}")
            return ""

def get_llm_backend_from_config(config: Dict) -> LLMBackend:
    """Create LLM backend from configuration. max_tokens is always set from config, or defaults to DEFAULT_MAX_TOKENS."""
    llm_config = config.get("llm", {})
    backend_type = llm_config.get("backend", "ollama")
    model_name = llm_config.get("model", "mistral")
    temperature = llm_config.get("temperature", 0.0)
    api_key = llm_config.get("api_key")
    api_url = llm_config.get("api_url")
    max_tokens = llm_config.get("max_tokens", DEFAULT_MAX_TOKENS)
    if backend_type == "chatgpt" or backend_type == "openai":
        return ChatGPTBackend(model_name, api_key, temperature, max_tokens)
    elif backend_type == "claude" or backend_type == "anthropic":
        return ClaudeBackend(model_name, api_key, temperature, max_tokens)
    elif backend_type == "qwen":
        return QwenBackend(model_name, api_key, temperature, max_tokens)
    elif backend_type == "lmstudio":
        api_url = api_url or "http://localhost:1234"
        return LMStudioBackend(model_name, api_url, temperature, max_tokens)
    elif backend_type == "ollama":
        return OllamaBackend(model_name, temperature, max_tokens)
    else:
        raise ValueError(f"Unsupported backend type: {backend_type}")

def chunk_text_intelligently(text: str, max_tokens: int = 1000, overlap: int = 100) -> List[Dict[str, any]]:
    """Split text into intelligent chunks with overlap for context"""
    if not text.strip():
        console.print("[yellow]Empty text provided for chunking")
        return []
        
    paragraphs = text.split('\n\n')
    chunks = []
    current_chunk = []
    current_tokens = 0
    
    for para in paragraphs:
        if not para.strip():
            continue
            
        para_tokens = len(para.split())
        
        if current_tokens + para_tokens > max_tokens and current_chunk:
            chunk_text = '\n\n'.join(current_chunk)
            if chunk_text.strip():
                chunks.append({
                    'text': chunk_text,
                    'tokens': current_tokens,
                    'start_idx': len(chunks),
                    'is_complete': False
                })
            
            if overlap > 0 and len(current_chunk) > 1:
                current_chunk = [current_chunk[-1]]
                current_tokens = len(current_chunk[0].split())
            else:
                current_chunk = []
                current_tokens = 0
        
        current_chunk.append(para)
        current_tokens += para_tokens
    
    if current_chunk:
        chunk_text = '\n\n'.join(current_chunk)
        if chunk_text.strip():
            chunks.append({
                'text': chunk_text,
                'tokens': current_tokens,
                'start_idx': len(chunks),
                'is_complete': True
            })
    
    return chunks

def process_with_iterative_refinement(
    chunks: List[Dict],
    llm: LLMBackend,
    prompt: str,
    refinement_prompt: str = None
) -> str:
    """Process chunks with iterative refinement"""
    if not refinement_prompt:
        refinement_prompt = (
            "Here is the previous analysis:\n{previous}\n\n"
            "Now, considering this additional text:\n{current}\n\n"
            "Please update and refine the analysis based on this new information. "
            "Revise any conclusions, add new findings, and ensure coherence with the full context."
        )
    
    accumulated_result = ""
    
    for i, chunk_info in enumerate(chunks):
        if not isinstance(chunk_info, dict) or 'text' not in chunk_info:
            console.print(f"[yellow]Skipping malformed chunk {i}: {chunk_info}")
            continue
            
        chunk_text = chunk_info.get('text', '')
        if not chunk_text.strip():
            console.print(f"[yellow]Skipping empty chunk {i}")
            continue
        
        if i == 0:
            result = llm.process_text(chunk_text, prompt)
            accumulated_result = result
        else:
            refinement_request = refinement_prompt.format(
                previous=accumulated_result,
                current=chunk_text
            )
            result = llm.process_text(chunk_text, refinement_request)
            accumulated_result = result
            
        console.print(f"[blue]Processed chunk {i+1}/{len(chunks)} ({chunk_info.get('tokens', 0)} tokens)")
    
    return accumulated_result

def load_prompt_config(prompt_config: Path) -> Dict:
    """Load prompt configuration from JSON or JSONL file using srsly"""
    if not prompt_config.exists():
        raise FileNotFoundError(f"Prompt config file not found: {prompt_config}")
    # Try JSON first
    try:
        return srsly.read_json(prompt_config)
    except Exception:
        # Fallback to JSONL (returns list of dicts)
        return list(srsly.read_jsonl(prompt_config))

def save_llm_result(
    result: Any,
    output_folder: Path,
    source_path: Path,
    prompt_config: Dict,
    metadata: Dict = None
) -> Path:
    """Save LLM processing result with metadata"""
    # Get relative path using SegmentHandler
    rel_path = SegmentHandler.get_relative_path(source_path)
    output_path = output_folder / "documents" / rel_path.parent / f"{rel_path.stem}_result.json"
    
    # Ensure output directory exists
    ensure_dirs(output_path.parent)
    
    data = {
        "result": result,
        "source": str(rel_path),
        "prompt_config": prompt_config.get("name", "unnamed"),
        "timestamp": datetime.now().isoformat()
    }
    
    if metadata:
        data.update(metadata)
        
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(srsly.json_dumps(data, indent=2))
        
    logger.info(f"Saved LLM result to: {output_path}")
    return output_path

class LLMProcessor:
    """Handles LLM processing with consistent initialization and logging"""
    def __init__(
        self,
        input_folder: Path,
        output_folder: Path,
        prompt_config: Dict,
        llm: LLMBackend,
        max_tokens: int = 1000,
        input_manifest: Optional[Path] = None
    ):
        # Validate input parameters
        if not input_folder.exists():
            raise ValueError(f"Input folder does not exist: {input_folder}")
        
        if not isinstance(prompt_config, dict):
            raise ValueError("prompt_config must be a dictionary")
        
        if "steps" not in prompt_config:
            raise ValueError("prompt_config must contain 'steps' key")
        
        if input_manifest and not input_manifest.exists():
            raise ValueError(f"Input manifest does not exist: {input_manifest}")
        
        # Initialize instance variables
        self.input_folder = input_folder
        self.output_folder = output_folder
        self.prompt_config = prompt_config
        self.llm = llm
        self.max_tokens = max_tokens
        self.input_manifest = input_manifest
        
        # Create all required output directories
        self.steps_folder = output_folder / "steps"
        self.chunks_folder = output_folder / "chunks"
        self.documents_folder = output_folder / "documents"
        
        for folder in [self.steps_folder, self.chunks_folder, self.documents_folder]:
            ensure_dirs(folder)
        
        try:
            # Initialize manifest processor
            self.manifest_proc = ManifestProcessor(
                manifest_path=input_manifest,
                progress_file=output_folder / "llm_process_progress.jsonl"
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize manifest processor: {str(e)}")
        
        # Log initialization
        logger.info(f"Initialized LLMProcessor:")
        logger.info(f"  Input folder: {input_folder}")
        logger.info(f"  Output folder: {output_folder}")
        logger.info(f"  Steps folder: {self.steps_folder}")
        logger.info(f"  Chunks folder: {self.chunks_folder}")
        logger.info(f"  Documents folder: {self.documents_folder}")
        logger.info(f"  Max tokens: {max_tokens}")
        logger.info(f"  Model: {llm.model_name}")
        logger.info(f"  Steps configured: {len(prompt_config.get('steps', []))}")

def get_llm_backend_from_step_config(step_config: Dict, global_llm_config: Dict = None) -> LLMBackend:
    """Create LLM backend from step-specific configuration, falling back to global config"""
    # Use step-specific llm config if available, otherwise fall back to global
    llm_config = step_config.get("llm", global_llm_config or {})
    
    backend_type = llm_config.get("backend", "ollama")
    model_name = llm_config.get("model", "mistral")
    temperature = llm_config.get("temperature", 0.0)
    api_key = llm_config.get("api_key")
    api_url = llm_config.get("api_url")
    max_tokens = llm_config.get("max_tokens", DEFAULT_MAX_TOKENS)
    
    if backend_type == "chatgpt" or backend_type == "openai":
        return ChatGPTBackend(model_name, api_key, temperature, max_tokens)
    elif backend_type == "claude" or backend_type == "anthropic":
        return ClaudeBackend(model_name, api_key, temperature, max_tokens)
    elif backend_type == "qwen":
        return QwenBackend(model_name, api_key, temperature, max_tokens)
    elif backend_type == "lmstudio":
        api_url = api_url or "http://localhost:1234"
        return LMStudioBackend(model_name, api_url, temperature, max_tokens)
    elif backend_type == "ollama":
        return OllamaBackend(model_name, temperature, max_tokens)
    else:
        raise ValueError(f"Unsupported backend type: {backend_type}")

async def process_pages_async(
    pages: List[Dict],  # List of {'path': Path, 'content': str, 'page_num': int}
    llm: ChatGPTBackend,
    prompt: str,
    batch_size: int = 10,
    output_folder: Path = None,
    step_name: str = "async_step"
) -> List[Dict]:
    """Process pages asynchronously and save individual JSONL files"""
    
    console.print(f"[blue]Processing {len(pages)} pages asynchronously (batch size: {batch_size})")
    
    # Process pages in batches
    results = await llm.process_pages_batch(pages, prompt, batch_size)
    
    # Save individual page results as JSONL if output folder specified
    if output_folder:
        pages_folder = output_folder / "pages" / step_name
        pages_folder.mkdir(parents=True, exist_ok=True)
        
        for result in results:
            page_num = result.get('page_num', 0)
            page_file = pages_folder / f"page_{page_num:03d}.jsonl"
            
            # Convert result to JSONL format
            jsonl_entry = {
                "page_num": page_num,
                "source_file": str(result.get('source_file', '')),  # Convert Path to string
                "timestamp": result.get('timestamp', ''),
                "step": step_name,
                "result": result.get('result', '')
            }
            
            # Try to parse result as JSON if it looks like JSON
            try:
                if isinstance(result.get('result'), str):
                    result_text = result.get('result', '').strip()
                    if result_text.startswith('{') or result_text.startswith('['):
                        jsonl_entry["result"] = json.loads(result_text)
            except json.JSONDecodeError:
                # Keep as string if not valid JSON
                pass
            
            # Save as JSONL (one line per file for individual pages)
            with open(page_file, 'w', encoding='utf-8') as f:
                f.write(srsly.json_dumps(jsonl_entry) + '\n')
            
            logger.info(f"Saved page {page_num} result to: {page_file}")
    
    # Convert any remaining Path objects to strings in the results
    for result in results:
        if 'source_file' in result and isinstance(result['source_file'], Path):
            result['source_file'] = str(result['source_file'])
    
    console.print(f"[green]Completed async processing of {len(results)} pages")
    return results

def combine_page_results(
    page_results: List[Dict],
    llm: LLMBackend,
    combine_prompt: str,
    output_folder: Path = None,
    step_name: str = "combine_step"
) -> Dict:
    """Combine multiple page results using a potentially different LLM"""
    
    console.print(f"[blue]Combining results from {len(page_results)} pages")
    
    if not page_results:
        logger.warning("No page results to combine")
        return {
            'combined_result': "No page results found to combine",
            'source_pages': 0,
            'timestamp': datetime.now().isoformat()
        }
    
    # Prepare combined input for the LLM
    combined_input = []
    for result in page_results:
        page_num = result.get('page_num', 0)
        page_result = result.get('result', '')
        
        # Handle both parsed JSON and string results
        if isinstance(page_result, dict) or isinstance(page_result, list):
            combined_input.append(f"Page {page_num}: {json.dumps(page_result, indent=2)}")
        elif isinstance(page_result, str) and page_result.strip():
            # Try to parse as JSON for better formatting
            try:
                if page_result.strip().startswith('{') or page_result.strip().startswith('['):
                    parsed_result = json.loads(page_result)
                    combined_input.append(f"Page {page_num}: {json.dumps(parsed_result, indent=2)}")
                else:
                    combined_input.append(f"Page {page_num}: {page_result}")
            except json.JSONDecodeError:
                combined_input.append(f"Page {page_num}: {page_result}")
        else:
            logger.warning(f"Skipping empty result for page {page_num}")
    
    if not combined_input:
        logger.warning("No valid page results found after processing")
        return {
            'combined_result': "No valid page results found",
            'source_pages': len(page_results),
            'timestamp': datetime.now().isoformat()
        }
    
    # Combine all page results into one text
    all_pages_text = "\n\n".join(combined_input)
    
    # Check if the combined text is too long and chunk if necessary
    # Estimate tokens (rough approximation: 1 token ~= 4 characters)
    estimated_tokens = len(all_pages_text) // 4
    max_tokens = getattr(llm, 'max_tokens', DEFAULT_MAX_TOKENS)
    
    # Reserve some tokens for the prompt and response
    available_tokens = max_tokens - len(combine_prompt) // 4 - 2000  # Reserve 2000 for response
    
    if estimated_tokens > available_tokens:
        logger.info(f"Text too long ({estimated_tokens} tokens), chunking into smaller pieces")
        
        # Split into chunks that fit within token limits
        chunk_size = available_tokens * 4  # Convert back to characters
        chunks = []
        current_chunk = []
        current_length = 0
        
        for page_text in combined_input:
            if current_length + len(page_text) > chunk_size and current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = [page_text]
                current_length = len(page_text)
            else:
                current_chunk.append(page_text)
                current_length += len(page_text) + 2  # +2 for \n\n
        
        if current_chunk:
            chunks.append("\n\n".join(current_chunk))
        
        logger.info(f"Split into {len(chunks)} chunks")
        
        # Process each chunk and combine results
        chunk_results = []
        for i, chunk in enumerate(chunks):
            logger.info(f"Processing chunk {i+1}/{len(chunks)}")
            
            chunk_prompt = f"{combine_prompt}\n\nThis is chunk {i+1} of {len(chunks)}. Please process this subset of pages:"
            result = llm.process_text(chunk, chunk_prompt)
            chunk_results.append(result)
        
        # Now combine the chunk results
        if len(chunk_results) > 1:
            final_combine_prompt = f"{combine_prompt}\n\nHere are the results from processing chunks. Please combine these into a final consolidated result:"
            combined_chunks = "\n\n".join([f"Chunk {i+1}: {result}" for i, result in enumerate(chunk_results)])
            combined_result = llm.process_text(combined_chunks, final_combine_prompt)
        else:
            combined_result = chunk_results[0]
    else:
        # Process all at once if it fits
        logger.info(f"Processing all {len(page_results)} pages in one request ({estimated_tokens} tokens)")
        combined_result = llm.process_text(all_pages_text, combine_prompt)
    
    # Save combined result
    if output_folder:
        combined_folder = output_folder / "combined"
        combined_folder.mkdir(parents=True, exist_ok=True)
        
        combined_file = combined_folder / f"{step_name}_combined.jsonl"
        
        # Try to parse as JSON
        final_result = combined_result
        try:
            if isinstance(combined_result, str):
                result_text = combined_result.strip()
                # Handle code blocks
                if result_text.startswith('```json'):
                    start = result_text.find('```json') + 7
                    end = result_text.rfind('```')
                    if end > start:
                        result_text = result_text[start:end].strip()
                elif result_text.startswith('```'):
                    lines = result_text.split('\n')
                    if lines[0].startswith('```') and lines[-1] == '```':
                        result_text = '\n'.join(lines[1:-1])
                
                if result_text.startswith('{') or result_text.startswith('['):
                    final_result = json.loads(result_text)
                    logger.info("Successfully parsed final JSON result")
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse final JSON result: {e}")
            # Keep as string if not valid JSON
        
        jsonl_entry = {
            "step": step_name,
            "source_pages": len(page_results),
            "timestamp": datetime.now().isoformat(),
            "result": final_result
        }
        
        # Save as JSONL
        with open(combined_file, 'w', encoding='utf-8') as f:
            f.write(srsly.json_dumps(jsonl_entry) + '\n')
        
        logger.info(f"Saved combined result to: {combined_file}")
    
    console.print(f"[green]Combined {len(page_results)} page results")
    return {
        'combined_result': final_result,
        'source_pages': len(page_results),
        'timestamp': datetime.now().isoformat()
    }

def get_llm_backend(config_or_backend_type: Union[Dict, str], model_name: Optional[str] = None, api_key: Optional[str] = None, api_url: Optional[str] = None, temperature: float = 0.0, max_tokens: int = DEFAULT_MAX_TOKENS) -> LLMBackend:
    """Flexible factory function to create an LLM backend from either a config dict or direct arguments."""
    if isinstance(config_or_backend_type, dict):
        return get_llm_backend_from_config(config_or_backend_type)
    else:
        backend_type = config_or_backend_type
        if backend_type == "chatgpt" or backend_type == "openai":
            return ChatGPTBackend(model_name, api_key, temperature, max_tokens)
        elif backend_type == "claude" or backend_type == "anthropic":
            return ClaudeBackend(model_name, api_key, temperature, max_tokens)
        elif backend_type == "qwen":
            return QwenBackend(model_name, api_key, temperature, max_tokens)
        elif backend_type == "lmstudio":
            api_url = api_url or "http://localhost:1234"
            return LMStudioBackend(model_name, api_url, temperature, max_tokens)
        elif backend_type == "ollama":
            return OllamaBackend(model_name, temperature, max_tokens)
        else:
            raise ValueError(f"Unsupported backend type: {backend_type}")

def process_document_with_llm(
    doc_path: Path,
    text_content: str,
    llm: LLMBackend,
    prompt_config: Dict,
    max_tokens: int,
    output_folder: Path
) -> dict:
    """Process a single document through LLM pipeline"""
    
    # Convert to Path object if needed
    doc_path = Path(doc_path)
    output_folder = Path(output_folder)
    
    # Use get_relative_path from files.py for consistent path handling
    rel_path = get_relative_path(doc_path)
    logger.info(f"Processing document: {rel_path}")
    
    # Create organized output structure
    doc_stem = rel_path.stem
    doc_parent = rel_path.parent if rel_path.parent != Path('.') else Path('')
    
    # Create folders for each type of output - use the relative path directly
    steps_folder = output_folder / "steps" / doc_stem
    chunks_folder = output_folder / "chunks" / doc_stem
    documents_folder = output_folder / "documents"
    
    # Create the directories
    for folder in [steps_folder, chunks_folder, documents_folder]:
        folder.mkdir(parents=True, exist_ok=True)
        logger.info(f"Ensured directory exists: {folder}")
    
    # Check if we should use intelligent chunking
    use_intelligent_chunking = prompt_config.get("intelligent_chunking", False)
    chunk_overlap = prompt_config.get("chunk_overlap", 100)
    
    # Process text in chunks
    logger.info("Chunking text...")
    if use_intelligent_chunking:
        chunks = chunk_text_by_structure(text_content, max_tokens, chunk_overlap)
        logger.info(f"Using intelligent chunking:")
        logger.info(f"  Chunks: {len(chunks)}")
        logger.info(f"  Overlap: {chunk_overlap} tokens")
        logger.info(f"  Max tokens per chunk: {max_tokens}")
    else:
        # Simple text chunking when intelligent_chunking is False
        words = text_content.split()
        text_chunks = []
        current_chunk = []
        current_tokens = 0
        
        for word in words:
            if current_tokens + 1 > max_tokens and current_chunk:
                text_chunks.append(' '.join(current_chunk))
                current_chunk = [word]
                current_tokens = 1
            else:
                current_chunk.append(word)
                current_tokens += 1
        
        # Add the last chunk if it exists
        if current_chunk:
            text_chunks.append(' '.join(current_chunk))
        
        chunks = []
        for i, chunk in enumerate(text_chunks):
            if chunk.strip():  # Only add non-empty chunks
                chunks.append({
                    "text": chunk, 
                    "tokens": len(chunk.split()), 
                    "start_idx": i
                })
        logger.info(f"Using basic chunking:")
        logger.info(f"  Chunks: {len(chunks)}")
        logger.info(f"  Max tokens per chunk: {max_tokens}")
    
    all_results = {}
    step_outputs = []  # Track all step output files
    
    # Validate chunks
    if not chunks:
        logger.warning("No chunks generated from text, skipping processing")
        return {}
    
    # Process each step defined in prompt config
    for step_idx, step in enumerate(prompt_config.get("steps", [])):
        step_name = step.get("name", f"step_{step_idx}")
        prompt = step.get("prompt", "")
        
        logger.info(f"Processing step {step_idx + 1}/{len(prompt_config.get('steps', []))}: {step_name}")
        logger.info(f"Prompt: {prompt[:100]}...")
        
        # Check if this step uses iterative refinement
        if step.get("iterative_refinement", False):
            logger.info("Using iterative refinement")
            # Use iterative refinement for this step
            refinement_prompt = step.get("refinement_prompt", None)
            result = process_with_iterative_refinement(
                chunks, llm, prompt, refinement_prompt
            )
            all_results[step_name] = result
            
            # Save the step result
            step_file = steps_folder / f"{step_name}.json"
            with open(step_file, 'w', encoding='utf-8') as f:
                f.write(srsly.json_dumps({
                    "source": str(rel_path),
                    "step": step_name,
                    "result": result,
                    "mode": "iterative_refinement",
                    "timestamp": datetime.now().isoformat()
                }, indent=2))
            step_outputs.append(str(step_file.relative_to(output_folder)))
            logger.info(f"Saved step result to: {step_file}")
            
            # Also save chunk results for debugging
            chunk_file = chunks_folder / f"{step_name}_chunks.json"
            with open(chunk_file, 'w', encoding='utf-8') as f:
                f.write(srsly.json_dumps({
                    "source": str(rel_path),
                    "step": step_name,
                    "chunks": [{"idx": i, "tokens": c["tokens"]} for i, c in enumerate(chunks)],
                    "mode": "iterative_refinement"
                }, indent=2))
            logger.info(f"Saved chunk info to: {chunk_file}")
        else:
            # Original chunk-by-chunk processing
            logger.info("Processing chunks sequentially")
            chunk_results = []
            
            for chunk_idx, chunk_info in enumerate(chunks):
                # Validate chunk structure
                if not isinstance(chunk_info, dict) or 'text' not in chunk_info:
                    logger.warning(f"Skipping malformed chunk {chunk_idx}: {chunk_info}")
                    continue
                    
                chunk_text = chunk_info.get('text', '')  # Initialize with default chunk text
                if not chunk_text.strip():
                    logger.warning(f"Skipping empty chunk {chunk_idx}")
                    continue
                
                logger.info(f"Processing chunk {chunk_idx + 1}/{len(chunks)} ({chunk_info.get('tokens', 0)} tokens)")
                
                # Use previous step's output if chaining
                if step.get("use_previous", False) and step_idx > 0:
                    prev_step_name = prompt_config["steps"][step_idx-1].get("name", f"step_{step_idx-1}")
                    if prev_step_name in all_results:
                        prev_result = all_results[prev_step_name]
                        if isinstance(prev_result, list):
                            # Use specific chunk if available, otherwise use first result
                            chunk_text = "\n\n".join(prev_result) if len(prev_result) > chunk_idx else prev_result[0] if prev_result else chunk_text
                        else:
                            # Use the previous result as text
                            chunk_text = str(prev_result) if prev_result else chunk_text
                        logger.info(f"Using output from previous step: {prev_step_name}")
                    else:
                        logger.warning(f"Previous step {prev_step_name} not found, using original chunk text")
                
                result = llm.process_text(chunk_text, prompt)
                logger.info(f"Got result ({len(result)} chars)")
                
                # Try to parse as JSON if specified
                if step.get("json", False):
                    try:
                        if result.strip().startswith('{') or result.strip().startswith('['):
                            result = json.loads(result)
                            logger.info("Successfully parsed JSON result")
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse JSON for {rel_path}, chunk {chunk_idx}")
                
                chunk_results.append(result)

                # Save individual chunk result
                chunk_file = chunks_folder / f"{step_name}_chunk{chunk_idx}.json"
                with open(chunk_file, 'w', encoding='utf-8') as f:
                    f.write(srsly.json_dumps({
                        "source": str(rel_path),
                        "step": step_name,
                        "chunk": chunk_idx,
                        "result": result
                    }, indent=2))
                logger.info(f"Saved chunk result to: {chunk_file}")
            
            # Combine results if specified
            if step.get("combine", False):
                logger.info("Combining chunk results...")
                if chunk_results and isinstance(chunk_results[0], (dict, list)):
                    # Combine JSON results
                    if isinstance(chunk_results[0], list):
                        combined = []
                        for r in chunk_results:
                            if isinstance(r, list):
                                combined.extend(r)
                        all_results[step_name] = combined
                        logger.info(f"Combined {len(combined)} list items")
                    else:
                        # For dicts, merge or take first
                        all_results[step_name] = chunk_results[0]
                        logger.info("Using first dictionary result")
                elif chunk_results:
                    # Combine text results
                    all_results[step_name] = "\n\n".join(str(r) for r in chunk_results)
                    logger.info(f"Combined {len(chunk_results)} text chunks")
                else:
                    # Handle empty results
                    all_results[step_name] = ""
                    logger.warning("No results to combine, using empty string")
            else:
                all_results[step_name] = chunk_results
                logger.info(f"Kept {len(chunk_results)} separate results")
            
            # Save the step result
            step_file = steps_folder / f"{step_name}.json"
            with open(step_file, 'w', encoding='utf-8') as f:
                f.write(srsly.json_dumps({
                    "source": str(rel_path),
                    "step": step_name,
                    "result": all_results[step_name],
                    "chunks_processed": len(chunk_results),
                    "timestamp": datetime.now().isoformat()
                }, indent=2))
            step_outputs.append(str(step_file.relative_to(output_folder)))
            logger.info(f"Saved step result to: {step_file}")
    
    # Save combined summary file
    logger.info("Creating summary file...")
    summary_file = documents_folder / f"{doc_stem}_summary.json"
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write(srsly.json_dumps({
            "source": str(rel_path),
            "config": prompt_config.get("name", "unnamed"),
            "steps": list(all_results.keys()),
            "step_outputs": step_outputs,
            "results": all_results,
            "timestamp": datetime.now().isoformat()
        }, indent=2))
    logger.info(f"Saved summary to: {summary_file}")
    
    return {
        "outputs": [str(summary_file.relative_to(output_folder))],
        "source": str(rel_path),
        "details": {
            "steps": list(all_results.keys()),
            "step_outputs": step_outputs,
            "results": all_results
        }
    }

def process_folder_with_llm(
    folder_path: Path,
    files: List[Dict],  # List of {'path': Path, 'content': str, 'page_num': int}
    llm: LLMBackend,
    prompt_config: Dict,
    max_tokens: int,
    output_folder: Path
) -> Dict:
    """Process an entire folder of documents as a cohesive unit through LLM pipeline"""
    
    console.print(f"[blue]Processing folder: {folder_path}")
    console.print(f"[green]Total files in folder: {len(files)}")
    
    # Convert to Path objects if needed
    folder_path = Path(folder_path)
    output_folder = Path(output_folder)
    
    # Get relative path for the folder
    rel_folder = get_relative_path(folder_path)
    folder_name = rel_folder.name if rel_folder.name else folder_path.name
    
    # Create output directories - simplified structure
    steps_folder = output_folder / "steps" / folder_name
    chunks_folder = output_folder / "chunks" / folder_name
    documents_folder = output_folder / "documents"
    
    # Ensure directories exist
    for folder in [steps_folder, chunks_folder, documents_folder]:
        folder.mkdir(parents=True, exist_ok=True)
        logger.info(f"Ensured directory exists: {folder}")
    
    # Get global LLM config for fallback
    global_llm_config = prompt_config.get("llm", {})
    
    all_results = {}
    step_outputs = []  # Track all step output files
    
    # Process each step defined in prompt config
    for step_idx, step in enumerate(prompt_config.get("steps", [])):
        step_name = step.get("name", f"step_{step_idx}")
        prompt = step.get("prompt", "")
        
        logger.info(f"Processing step {step_idx + 1}/{len(prompt_config.get('steps', []))}: {step_name}")
        logger.info(f"Prompt: {prompt[:100]}...")
        
        # Get step-specific LLM if configured
        step_llm = llm  # Default to global LLM
        if "llm" in step:
            try:
                step_llm = get_llm_backend_from_step_config(step, global_llm_config)
                logger.info(f"Using step-specific LLM: {step_llm.model_name}")
            except Exception as e:
                logger.warning(f"Failed to create step-specific LLM, using global: {e}")
        
        # Check if this step should process pages asynchronously
        if step.get("async_page_processing", False):
            logger.info("Using async page processing")
            
            # Ensure we have a ChatGPT backend for async processing
            if not isinstance(step_llm, ChatGPTBackend):
                logger.error(f"Async processing requires ChatGPT backend, got {type(step_llm)}")
                continue
            
            batch_size = step.get("async_batch_size", 10)
            
            # Process pages asynchronously
            try:
                # Run async function in event loop
                try:
                    # Check if there's an existing event loop
                    loop = asyncio.get_running_loop()
                    # If we're already in an async context, we need to use create_task
                    # But since this function isn't async, we'll run in a new event loop
                    page_results = asyncio.run(process_pages_async(
                        files, step_llm, prompt, batch_size, output_folder, step_name
                    ))
                except RuntimeError:
                    # No running event loop, create a new one
                    page_results = asyncio.run(process_pages_async(
                        files, step_llm, prompt, batch_size, output_folder, step_name
                    ))
                
                # Clean up the results and parse JSON if needed
                cleaned_results = []
                for result in page_results:
                    page_result = result.get('result', '')
                    
                    # Clean up JSON code blocks if present
                    if isinstance(page_result, str):
                        # Remove markdown code blocks
                        if page_result.strip().startswith('```json'):
                            page_result = page_result.strip()
                            # Find the JSON content between ```json and ```
                            start = page_result.find('```json') + 7
                            end = page_result.rfind('```')
                            if end > start:
                                page_result = page_result[start:end].strip()
                        elif page_result.strip().startswith('```'):
                            # Handle other code block formats
                            lines = page_result.strip().split('\n')
                            if lines[0].startswith('```') and lines[-1] == '```':
                                page_result = '\n'.join(lines[1:-1])
                    
                    # Try to parse as JSON
                    if step.get("json", False):
                        try:
                            if isinstance(page_result, str) and page_result.strip():
                                parsed_result = json.loads(page_result)
                                result['result'] = parsed_result
                                logger.info(f"Successfully parsed JSON for page {result.get('page_num', 0)}")
                        except json.JSONDecodeError as e:
                            logger.warning(f"Failed to parse JSON for page {result.get('page_num', 0)}: {e}")
                            # Keep the original result
                    
                    cleaned_results.append(result)
                
                all_results[step_name] = cleaned_results
                logger.info(f"Async processing completed: {len(cleaned_results)} pages processed")
                
                # Save the step result
                step_file = steps_folder / f"{step_name}.json"
                with open(step_file, 'w', encoding='utf-8') as f:
                    f.write(srsly.json_dumps({
                        "source": str(rel_folder),
                        "step": step_name,
                        "result": cleaned_results,
                        "mode": "async_page_processing",
                        "pages_processed": len(cleaned_results),
                        "timestamp": datetime.now().isoformat()
                    }, indent=2))
                step_outputs.append(str(step_file.relative_to(output_folder)))
                logger.info(f"Saved async step result to: {step_file}")
                
            except Exception as e:
                logger.error(f"Error in async page processing: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                all_results[step_name] = []
        
        # Check if this step should combine previous results
        elif step.get("combine_results", False):
            logger.info("Combining previous step results")
            
            # Get previous step results
            use_previous = step.get("use_previous", True)
            if use_previous and step_idx > 0:
                prev_step_name = prompt_config["steps"][step_idx-1].get("name", f"step_{step_idx-1}")
                if prev_step_name in all_results:
                    prev_results = all_results[prev_step_name]
                    
                    if isinstance(prev_results, list) and all(isinstance(r, dict) for r in prev_results):
                        # Convert any PosixPath objects to strings in the results
                        for result in prev_results:
                            if 'source_file' in result and isinstance(result['source_file'], Path):
                                result['source_file'] = str(result['source_file'])
                        
                        # Combine page results
                        combined_result = combine_page_results(
                            prev_results, step_llm, prompt, output_folder, step_name
                        )
                        all_results[step_name] = combined_result
                        
                        # Save the step result
                        step_file = steps_folder / f"{step_name}.json"
                        with open(step_file, 'w', encoding='utf-8') as f:
                            f.write(srsly.json_dumps({
                                "source": str(rel_folder),
                                "step": step_name,
                                "result": combined_result,
                                "mode": "combine_results",
                                "source_step": prev_step_name,
                                "timestamp": datetime.now().isoformat()
                            }, indent=2))
                        step_outputs.append(str(step_file.relative_to(output_folder)))
                        logger.info(f"Saved combine step result to: {step_file}")
                    else:
                        logger.warning(f"Previous step {prev_step_name} results not in expected format for combining")
                else:
                    logger.warning(f"Previous step {prev_step_name} not found for combining")
        
        # Default processing (existing functionality)
        else:
            # Combine all documents with page numbers (existing functionality)
            combined_text = ""
            page_metadata = []
            
            for file_info in files:
                page_num = file_info.get('page_num', 0)
                file_path = file_info['path']
                content = file_info['content']
                
                # Add page marker
                page_marker = f"\n\n[PAGE {page_num}]\n\n"
                combined_text += page_marker + content
                
                page_metadata.append({
                    "page": page_num,
                    "file": str(file_path.name),  # Just the filename
                    "char_start": len(combined_text) - len(content),
                    "char_end": len(combined_text)
                })
            
            console.print(f"[green]Combined text length: {len(combined_text)} characters")
            
            # Process the combined text as a single document (existing functionality)
            result = process_document_with_llm(
                doc_path=folder_path,
                text_content=combined_text,
                llm=step_llm,
                prompt_config={"steps": [step]},  # Single step config
                max_tokens=max_tokens,
                output_folder=output_folder
            )
            
            # Extract just the result for this step
            step_result = result.get("details", {}).get("results", {}).get(step_name, "")
            all_results[step_name] = step_result
    
    # Create final summary with folder-specific metadata
    summary_file = documents_folder / f"{folder_name}_summary.json"
    summary_data = {
        "source_folder": str(rel_folder),
        "config": prompt_config.get("name", "unnamed"),
        "steps": list(all_results.keys()),
        "step_outputs": step_outputs,
        "results": all_results,
        "folder_metadata": {
            "files_processed": [f['path'].name for f in files],
            "total_pages": len(files),
        },
        "timestamp": datetime.now().isoformat()
    }
    
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write(srsly.json_dumps(summary_data, indent=2))
    logger.info(f"Saved folder summary to: {summary_file}")
    
    return {
        "outputs": [str(summary_file.relative_to(output_folder))],
        "source": str(rel_folder),
        "details": {
            "steps": list(all_results.keys()),
            "step_outputs": step_outputs,
            "results": all_results
        },
        "folder_metadata": summary_data["folder_metadata"]
    }

def chunk_text_by_structure(text: str, max_tokens: int = 1000, overlap: int = 100) -> List[Dict[str, any]]:
    """Intelligently chunk text by page boundaries first, then by paragraphs"""
    if not text.strip():
        console.print("[yellow]Empty text provided for chunking")
        return []
    
    chunks = []
    
    # First, try to detect page boundaries
    import re
    page_pattern = r'\n\s*(?:PAGE|Page|page)\s*(\d+)\s*\n'
    page_matches = list(re.finditer(page_pattern, text))
    
    if page_matches:
        console.print(f"[green]Found {len(page_matches)} page boundaries, chunking by pages")
        
        # Split by pages
        page_texts = []
        last_end = 0
        
        for i, match in enumerate(page_matches):
            if i == 0:
                # Content before first page marker
                if match.start() > 0:
                    page_texts.append({
                        'text': text[:match.start()].strip(),
                        'page_num': 0,
                        'is_header': True
                    })
            
            # Get content for this page
            start = match.end()
            end = page_matches[i + 1].start() if i + 1 < len(page_matches) else len(text)
            page_content = text[start:end].strip()
            
            if page_content:
                page_texts.append({
                    'text': page_content,
                    'page_num': int(match.group(1)),
                    'is_header': False
                })
        
        # Now chunk pages that are too large
        for page_info in page_texts:
            page_text = page_info['text']
            page_tokens = len(page_text.split())
            
            if page_tokens <= max_tokens:
                # Page fits in one chunk
                chunks.append({
                    'text': page_text,
                    'tokens': page_tokens,
                    'start_idx': len(chunks),
                    'page_num': page_info['page_num'],
                    'is_complete_page': True
                })
            else:
                # Page too large, split by paragraphs
                page_chunks = chunk_text_intelligently(page_text, max_tokens, overlap)
                for i, chunk in enumerate(page_chunks):
                    chunk['page_num'] = page_info['page_num']
                    chunk['is_complete_page'] = False
                    chunk['page_chunk_idx'] = i
                    chunk['start_idx'] = len(chunks)
                    chunks.append(chunk)
    
    else:
        console.print("[yellow]No page boundaries found, chunking by paragraphs")
        
        # No pages found, chunk by paragraphs
        paragraphs = text.split('\n\n')
        current_chunk = []
        current_tokens = 0
        
        for para in paragraphs:
            if not para.strip():
                continue
                
            para_tokens = len(para.split())
            
            # If adding this paragraph would exceed limit and we have content
            if current_tokens + para_tokens > max_tokens and current_chunk:
                chunk_text = '\n\n'.join(current_chunk)
                if chunk_text.strip():
                    chunks.append({
                        'text': chunk_text,
                        'tokens': current_tokens,
                        'start_idx': len(chunks),
                        'is_complete': len(current_chunk) == 1  # Complete if single paragraph
                    })
                
                # Start new chunk with overlap if specified
                if overlap > 0 and len(current_chunk) > 1:
                    # Keep last paragraph for overlap
                    current_chunk = [current_chunk[-1], para]
                    current_tokens = len(current_chunk[0].split()) + para_tokens
                else:
                    current_chunk = [para]
                    current_tokens = para_tokens
            else:
                current_chunk.append(para)
                current_tokens += para_tokens
        
        # Add final chunk
        if current_chunk:
            chunk_text = '\n\n'.join(current_chunk)
            if chunk_text.strip():
                chunks.append({
                    'text': chunk_text,
                    'tokens': current_tokens,
                    'start_idx': len(chunks),
                    'is_complete': True
                })
    
    console.print(f"[blue]Created {len(chunks)} chunks from text structure")
    return chunks 