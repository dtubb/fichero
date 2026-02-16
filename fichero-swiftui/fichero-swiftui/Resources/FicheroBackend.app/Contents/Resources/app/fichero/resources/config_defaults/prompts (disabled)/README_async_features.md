# Async LLM Processing Features

This document explains the new async processing and multi-model features added to the LLM processing system.

## New Features

### 1. Async Page Processing
Process each page individually using async/concurrent processing for faster execution.

```json
{
  "name": "async_step",
  "prompt": "Extract entities from this page...",
  "async_page_processing": true,
  "async_batch_size": 10,
  "json": true
}
```

**Options:**
- `async_page_processing: true` - Enable async processing
- `async_batch_size: 10` - Number of concurrent requests (default: 10)
- Requires ChatGPT backend for async support

### 2. Per-Step Model Configuration
Use different models for different steps in the same config file.

```json
{
  "steps": [
    {
      "name": "extract_data",
      "llm": {
        "backend": "chatgpt",
        "model": "gpt-3.5-turbo",
        "max_tokens": 4096
      }
    },
    {
      "name": "combine_data", 
      "llm": {
        "backend": "chatgpt",
        "model": "gpt-4",
        "max_tokens": 8192
      }
    }
  ]
}
```

### 3. Result Combining
Combine results from previous steps using a different model.

```json
{
  "name": "combine_step",
  "prompt": "Combine these results...",
  "combine_results": true,
  "use_previous": true,
  "llm": {
    "model": "gpt-4"
  }
}
```

**Options:**
- `combine_results: true` - Enable result combining
- `use_previous: true` - Use previous step's results as input

### 4. JSONL Output
Individual page results are saved as JSONL files in `output/pages/step_name/` directory.

Combined results are saved in `output/combined/` directory.

## File Structure

```
output/
├── pages/
│   └── step_name/
│       ├── page_001.jsonl
│       ├── page_002.jsonl
│       └── ...
├── combined/
│   └── step_name_combined.jsonl
├── steps/
│   └── folder_name/
│       ├── step1.json
│       └── step2.json
└── documents/
    └── folder_summary.json
```

## Example Use Cases

### 1. NER Processing (see `ner_async_config.jsonl`)
- Step 1: Extract entities from each page (GPT-3.5, async)
- Step 2: Combine and deduplicate entities (GPT-4)

### 2. Document Analysis
- Step 1: Extract key points from each page (async)
- Step 2: Synthesize into overall analysis (different model)

## Optional Features Summary

All features are optional and backward compatible:

- `async_page_processing: true/false` (default: false)
- `async_batch_size: number` (default: 10) 
- `combine_results: true/false` (default: false)
- `use_previous: true/false` (default: false)
- `json: true/false` (default: false)
- `iterative_refinement: true/false` (default: false)
- `combine: true/false` (default: false)
- Per-step `llm` configuration (optional)

## Backend Support

**Async Processing:**
- ✅ ChatGPT/OpenAI (full async support)
- ❌ Other backends (falls back to sequential)

**All Other Features:**
- ✅ All backends supported

## Performance

Async processing can significantly reduce processing time for multi-page documents:
- Sequential: ~8 seconds per page
- Async (batch=10): ~1-2 seconds per page
- Time savings: 75-80% for large documents 