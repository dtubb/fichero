# LLM Processing Configuration

This directory contains configuration files for the LLM processing pipeline used by the Fichero document analysis system.

## Configuration Structure

Each configuration file is a JSONL file with the following structure:

```json
{
  "name": "config_name",
  "description": "What this configuration does",
  "intelligent_chunking": false,  // Enable intelligent paragraph-based chunking
  "chunk_overlap": 100,           // Token overlap between chunks for context
  "llm": {
    "backend": "openai|claude|qwen|lmstudio|ollama",
    "model": "model-name",
    "temperature": 0.0,
    "max_tokens": 1000000,
    "top_p": 0.95,
    "frequency_penalty": 0.0,
    "presence_penalty": 0.0,
    "stop_sequences": [],
    "timeout": 120,
    "retry_attempts": 3,
    "retry_delay": 5,
    "api_key": "optional-api-key",
    "api_url": "optional-api-url-for-lmstudio"
  },
  "steps": [
    {
      "name": "step_name",
      "prompt": "The prompt to use for this step",
      "include_page_context": true,
      "combine": true,              // Whether to combine chunk results
      "json": false,                // Whether to expect JSON output
      "use_previous": false,        // Whether to use previous step's output
      "combine_results": false,     // Whether to combine results from multiple sources
      "iterative_refinement": false,// Enable iterative refinement mode
      "refinement_prompt": "..."    // Custom refinement prompt (optional)
    }
  ]
}
```

## Advanced Features

### Intelligent Chunking

When `intelligent_chunking` is enabled:
- Text is split by paragraphs to maintain semantic coherence
- Chunks include overlap from previous chunks for context continuity
- Chunk boundaries respect natural text breaks

### Iterative Refinement

When a step has `iterative_refinement: true`:
- The first chunk is processed normally
- Subsequent chunks are processed with the previous result as context
- The LLM updates and refines its analysis as it sees more content
- Perfect for long documents where context builds progressively

Example use cases:
- **Progressive Summarization**: Build a summary that evolves as more content is processed
- **Entity Accumulation**: Collect entities across the entire document
- **Thematic Analysis**: Refine themes as more evidence appears

### Custom Refinement Prompts

You can provide custom refinement prompts using `refinement_prompt`:
```json
{
  "refinement_prompt": "Previous analysis:\n{previous}\n\nNew content:\n{current}\n\nUpdate your analysis..."
}
```

Variables available:
- `{previous}`: The accumulated result so far
- `{current}`: The new chunk being processed

## Step Configuration Parameters

### Basic Configuration
- `name`: Unique identifier for the step
- `prompt`: The prompt text sent to the LLM
- `include_page_context`: Whether to include page numbers in processing
- `combine`: Whether to combine results from multiple chunks
- `json`: Whether the output should be parsed as JSON

### Processing Strategy
- `chunking_strategy`: How to split long documents
  - `"none"`: Process entire document at once (recommended for most use cases)
  - `"token_based"`: Split by token count
  - `"page_based"`: Split by page boundaries
- `pages_per_chunk`: Number of pages per chunk (for page-based chunking)
- `chunk_overlap`: Number of tokens to overlap between chunks

### Advanced Features
- `async`: Whether to process chunks asynchronously (requires ChatGPT backend)
- `async_batch_size`: Number of concurrent async operations
- `iterative_refinement`: Whether to refine results iteratively
- `refinement_prompt`: Custom prompt for iterative refinement
- `use_previous`: Whether to use output from previous steps as input
- `combine_results`: Whether to combine results from multiple sources
- `debug`: Whether to save debug input/output files

### Step-Specific LLM Configuration
```json
"llm": {
  "backend": "openai",
  "model": "gpt-4.1",
  "temperature": 0.0,
  "max_tokens": 1000000
}
```
Overrides global LLM settings for this specific step.

## Processing Flow

### 1. Document Input
- Documents are processed in their entirety when `chunking_strategy: "none"`
- Text content is passed directly to the LLM with the specified prompt
- Page context is included when `include_page_context: true`

### 2. Step Execution
- Each step processes the document according to its configuration
- If `use_previous: true`, the step receives output from previous steps
- Results are saved to step-specific files in the output directory

### 3. Output Generation
- If `json: true`, LLM output is parsed as JSON and validated
- Results are saved to the `steps/` directory
- Debug files are created if `debug: true`

### 4. Dependencies
- Later steps can access results from earlier steps
- The `use_previous` flag enables step-to-step data flow
- Final summary steps combine all previous results

## API Key Configuration

API keys can be provided in three ways (in order of precedence):

1. **In the configuration file**: Set `api_key` in the `llm` section
2. **Via environment variables**: Export the appropriate variable
3. **Via command line**: Use the `--api-key` option (if available)

### Environment Variables

- **OpenAI/ChatGPT**: `export OPENAI_API_KEY=your-key-here`
- **Claude/Anthropic**: `export ANTHROPIC_API_KEY=your-key-here` or `export CLAUDE_API_KEY=your-key-here`
- **Qwen**: `export DASHSCOPE_API_KEY=your-key-here` or `export QWEN_API_KEY=your-key-here`

## Available Backends

### OpenAI (ChatGPT)
```json
"llm": {
  "backend": "openai",
  "model": "gpt-4o-mini",
  "temperature": 0.0,
  "max_tokens": 1000000
}
```

### Claude (Anthropic)
```json
"llm": {
  "backend": "claude",
  "model": "claude-3-opus-20240229",
  "temperature": 0.0,
  "max_tokens": 1000000
}
```

### Qwen
```json
"llm": {
  "backend": "qwen",
  "model": "qwen-max",
  "temperature": 0.0,
  "max_tokens": 1000000
}
```

### LMStudio (Local)
```json
"llm": {
  "backend": "lmstudio",
  "model": "TheBloke/Mistral-7B-Instruct-v0.2-GGUF",
  "api_url": "http://localhost:1234",
  "temperature": 0.0,
  "max_tokens": 1000000
}
```

### Ollama (Local)
```json
"llm": {
  "backend": "ollama",
  "model": "mistral",
  "temperature": 0.0,
  "max_tokens": 1000000
}
```

## Example Usage

```bash
# Set environment variable
export OPENAI_API_KEY=sk-your-api-key-here

# Run with a specific configuration
python -m fichero.tools.llm_process \
  assets/transcriptions \
  assets/transcriptions/transcription_manifest.jsonl \
  assets/llm_processed \
  --prompt-config prompts/Catalogue (English).jsonl

# Run with folder mode for multi-page documents
python -m fichero.tools.llm_process \
  assets/transcriptions \
  assets/transcriptions/transcription_manifest.jsonl \
  assets/llm_processed \
  --prompt-config prompts/Quotations.jsonl \
  --folder-mode
```

## Available Configurations

### Catalogue (English).jsonl
A comprehensive 6-step pipeline for historical document analysis:
1. **Extract People/Organizations/Locations** - Named Entity Recognition for basic entities
2. **Extract Dates/Legal References/Rivers** - Time and legal-specific entities  
3. **Extract Specialized Entities** - Domain-specific entities (mines, properties, weapons, etc.)
4. **Create Timeline** - Chronological ordering of events
5. **Identify Key People & Tags** - Most important individuals and thematic keywords
6. **Generate Summary** - 150-word archival description

Uses GPT-4o-mini for NER and GPT-4o for summary generation.

### Quotations.jsonl
Specialized pipeline for extracting direct quotations, testimony, and statements by specific people from documents. Designed for legal research and historical analysis where direct quotes are essential.

### Catalogue.jsonl
Spanish-language version of the catalogue pipeline for Spanish-language documents.

## Best Practices

1. **Set `chunking_strategy: "none"`** for steps that need full document context
2. **Use `use_previous: true`** for steps that build on previous results
3. **Set `json: true`** for structured output parsing
4. **Enable `debug: true`** during development for troubleshooting
5. **Use step-specific LLM configs** when different models are needed for different tasks
6. **Set `async: true`** for CPU-intensive steps when using ChatGPT backend
7. **Use `folder_mode: true`** when processing multi-page documents as cohesive units
8. **Set `include_page_context: true`** when page numbers are important for analysis

## Output Structure

The pipeline creates organized output directories:
- `steps/`: Individual step results
- `chunks/`: Chunk processing results (if chunking enabled)
- `documents/`: Final combined results
- `debug/`: Debug input/output files (if debug enabled)

## Integration with Workflows

These prompt configurations are designed to work with the Fichero workflow system:
- **Default.yml** - Spanish transcription and cataloguing
- **Default (English).yml** - English transcription and cataloguing  
- **Quotations.yml** - Extract quotations and testimony

Each workflow uses the appropriate prompt configuration to achieve specific document analysis goals.

This format provides a flexible, configurable way to create complex document processing pipelines while maintaining clear separation of concerns between different processing stages. 