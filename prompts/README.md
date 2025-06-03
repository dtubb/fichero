# LLM Processing Configuration

This directory contains configuration files for the LLM processing pipeline.

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
    "api_key": "optional-api-key",
    "api_url": "optional-api-url-for-lmstudio"
  },
  "steps": [
    {
      "name": "step_name",
      "prompt": "The prompt to use for this step",
      "combine": true,              // Whether to combine chunk results
      "json": false,                // Whether to expect JSON output
      "use_previous": false,        // Whether to use previous step's output
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
  "model": "gpt-4",
  "temperature": 0.0
}
```

### Claude (Anthropic)
```json
"llm": {
  "backend": "claude",
  "model": "claude-3-opus-20240229",
  "temperature": 0.0
}
```

### Qwen
```json
"llm": {
  "backend": "qwen",
  "model": "qwen-max",
  "temperature": 0.0
}
```

### LMStudio (Local)
```json
"llm": {
  "backend": "lmstudio",
  "model": "TheBloke/Mistral-7B-Instruct-v0.2-GGUF",
  "api_url": "http://localhost:1234",
  "temperature": 0.0
}
```

### Ollama (Local)
```json
"llm": {
  "backend": "ollama",
  "model": "mistral",
  "temperature": 0.0
}
```

## Example Usage

```bash
# Set environment variable
export OPENAI_API_KEY=sk-your-api-key-here

# Run with a specific configuration
python scripts/llm_process.py \
  assets/transcriptions \
  assets/transcriptions/transcription_manifest.jsonl \
  assets/llm_processed \
  --prompt-config prompts/catalogue_config.jsonl

# Run with iterative refinement for long documents
python scripts/llm_process.py \
  assets/transcriptions \
  assets/transcriptions/transcription_manifest.jsonl \
  assets/llm_processed/progressive \
  --prompt-config prompts/iterative_refinement_example.jsonl \
  --max-tokens 500
```

## Example Configurations

- `prompt_config_example.jsonl` - Basic multi-step analysis
- `catalogue_config.jsonl` - Generate catalog entries for documents
- `claude_example.jsonl` - Deep analysis using Claude
- `qwen_example.jsonl` - Translation and modernization using Qwen
- `lmstudio_example.jsonl` - Local processing with LMStudio
- `iterative_refinement_example.jsonl` - Progressive analysis with iterative refinement 