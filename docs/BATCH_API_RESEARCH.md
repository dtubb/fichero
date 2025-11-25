# Batch API Research and Implementation Guide

## Executive Summary

After comprehensive research into OpenAI and DashScope batch processing capabilities, this document clarifies the **two different types of "batch processing"** and provides implementation recommendations for Fichero's transcription system.

## Types of Batch Processing

### 1. OpenAI Batch API (Offline Batch Jobs)

**What it is:**
- An **asynchronous job submission system** for processing large volumes of requests
- Upload a JSONL file with multiple requests → receive results within 24 hours
- 50% cost discount compared to synchronous API calls
- Higher rate limits for bulk processing

**How it works:**
```python
# Step 1: Upload JSONL file with requests
batch_file = client.files.create(
    file=open("requests.jsonl", "rb"),
    purpose="batch"
)

# Step 2: Create batch job
batch = client.batches.create(
    input_file_id=batch_file.id,
    endpoint="/v1/chat/completions",
    completion_window="24h"
)

# Step 3: Wait and retrieve results (up to 24 hours)
```

**Key characteristics:**
- ⏱️ **Processing time**: Up to 24 hours (not real-time)
- 💰 **Cost**: 50% discount
- 📊 **Rate limits**: Substantially higher
- 🎯 **Use case**: Offline, non-time-sensitive workloads

**Supported models:**
- ✅ GPT-4o (with vision)
- ✅ GPT-4o-mini (with vision)
- ✅ GPT-4-turbo
- ✅ GPT-3.5-turbo

**JSONL format example:**
```json
{"custom_id": "request-1", "method": "POST", "url": "/v1/chat/completions", "body": {"model": "gpt-4o", "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}]}]}}
{"custom_id": "request-2", "method": "POST", "url": "/v1/chat/completions", "body": {"model": "gpt-4o", "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}]}]}}
```

### 2. Multi-Image Single Request (True Batch Processing)

**What it is:**
- Send **multiple images in ONE API request** to process them together
- Real-time synchronous processing
- Model processes all images in context
- Useful for comparison, multi-page documents, or related images

**How it works:**
```python
# Send multiple images in single request
completion = client.chat.completions.create(
    model="qwen3-vl-plus",
    messages=[{
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": "image1.jpg"}},
            {"type": "image_url", "image_url": {"url": "image2.jpg"}},
            {"type": "image_url", "image_url": {"url": "image3.jpg"}},
            {"type": "text", "text": "Extract text from all images"}
        ]
    }]
)
```

**Key characteristics:**
- ⚡ **Processing time**: Real-time (seconds to minutes)
- 💰 **Cost**: Standard API pricing
- 🖼️ **Image limits**: 4-512 images per request (model dependent)
- 🎯 **Use case**: Related images that need shared context

**Qwen-VL model limits:**
- **Qwen3-VL, Qwen2.5-VL, QVQ**: 4–512 images
- **Other Qwen models**: 4–80 images
- **Constraint**: Total tokens (images + text) must not exceed model's input limit

**OpenAI support:**
- ❓ **Status**: Documentation unclear on multi-image single request limits
- ✅ **Known**: Can send multiple images in one request
- ⚠️ **Limitation**: May have lower image count limits than Qwen-VL

## Current Fichero Implementation

### What We Have Now

**Architecture:**
```
transcribe.py
  └─> ThreadPoolExecutor (5 workers)
       ├─> Worker 1: process_image_with_provider(image1)
       ├─> Worker 2: process_image_with_provider(image2)
       ├─> Worker 3: process_image_with_provider(image3)
       ├─> Worker 4: process_image_with_provider(image4)
       └─> Worker 5: process_image_with_provider(image5)
```

- **Method**: Parallel API calls using ThreadPoolExecutor
- **Concurrency**: 5 separate API requests at once
- **Each request**: 1 image → 1 API call → 1 transcription result
- **Processing**: Real-time, results as they complete

### Comparison with Batch APIs

| Feature | Current (ThreadPool) | OpenAI Batch API | Multi-Image Single Request |
|---------|---------------------|------------------|---------------------------|
| **Processing** | Real-time parallel | Async (24h) | Real-time |
| **API calls** | N separate calls | 1 job submission | 1 API call |
| **Cost** | Standard | 50% discount | Standard |
| **Use case** | ✅ Independent images | ❌ Offline only | ⚠️ Related images |
| **Current fit** | ✅ Perfect | ❌ Too slow | ⚠️ Limited benefit |

## Recommendations

### 1. Keep Current ThreadPoolExecutor Approach ✅

**Why:**
- Fichero processes **independent, unrelated images** (archival documents)
- Users expect **real-time results** with progress updates
- Each image needs **separate transcription output**
- Current approach is **optimal for this use case**

**Evidence:**
- Archive documents are not related (no need for shared context)
- GUI shows real-time progress (incompatible with 24-hour batch jobs)
- Each document gets its own output file (not a single combined result)

### 2. Do NOT Implement OpenAI Batch API ❌

**Why:**
- **24-hour processing time** is unacceptable for interactive workflows
- **No cost benefit** for most users (processing is fast enough)
- **Complex implementation** (file uploads, polling, result retrieval)
- **Poor UX** (users can't see progress, must wait hours/days)

**When it might make sense:**
- Large-scale archival projects (10,000+ images)
- Cost is primary concern
- No time constraints
- Batch processing mode separate from interactive mode

### 3. Add Multi-Image Batching for Qwen-VL (Optional Enhancement) ⚠️

**What it provides:**
- Process **4-80 related images** in one API call
- Useful for **multi-page documents** or **document sets**
- Reduces API calls (80 images → 1 call vs 80 calls)
- **Shared context** across images

**Implementation approach:**
```python
def process_batch_multi_image(image_paths: List[Path], provider) -> Dict:
    """
    Process multiple images in single API request (Qwen-VL only).

    Args:
        image_paths: List of 4-80 image paths to process together
        provider: DashScope provider instance

    Returns:
        Combined transcription result
    """
    # Build multi-image content
    content = []
    for img_path in image_paths:
        base64_img = encode_image(img_path)
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}
        })
    content.append({
        "type": "text",
        "text": "Extract text from all images, returning results in order"
    })

    # Single API call for all images
    completion = client.chat.completions.create(
        model="qwen3-vl-plus",
        messages=[{"role": "user", "content": content}]
    )

    return parse_multi_image_result(completion.choices[0].message.content)
```

**Benefits:**
- **Cost reduction**: 80 images → 1 API call (lower total costs)
- **Rate limit efficiency**: Fewer calls against rate limits
- **Shared context**: Model can see relationships between images

**Challenges:**
- **Output parsing**: Need to split combined transcription into separate files
- **Error handling**: One failure affects all images in batch
- **Memory limits**: Total image size + text must fit in model's context
- **Provider support**: Qwen-VL only (not OpenAI, not LMStudio)

**Recommended scenarios:**
- Multi-page documents (pages 1-80 of same document)
- Document collections that need cross-referencing
- Cost optimization mode for large-scale processing

## Implementation Plan

### Phase 1: Keep Current System (Completed ✅)

**Status:** Current implementation is optimal for Fichero's use case.

**What we have:**
- ThreadPoolExecutor with 5 workers
- Real-time parallel processing
- Independent image transcription
- Good progress reporting

**No changes needed.**

### Phase 2: Add Multi-Image Batching (Optional)

**Only implement if:**
1. User requests multi-page document processing
2. Cost optimization becomes important
3. Document sets need shared context

**Implementation checklist:**
- [ ] Add `process_multi_image()` method to DashScope provider
- [ ] Add `supports_multi_image` property to base provider
- [ ] Update transcribe.py to detect multi-page documents
- [ ] Implement result parsing to split combined transcription
- [ ] Add error recovery for batch failures
- [ ] Test with 4-80 image batches
- [ ] Document image count limits per model

### Phase 3: OpenAI Batch API (Future, Low Priority)

**Only implement if:**
1. Large-scale archival projects (10,000+ images)
2. Dedicated "offline processing" mode requested
3. Cost savings justify complexity

**Implementation would require:**
- Separate "batch mode" CLI command
- JSONL file generation
- Batch job submission and monitoring
- Result retrieval and processing
- Background job tracking
- Estimated completion time calculation

**Estimated effort:** 2-3 days of development + testing

## Terminology Clarification

To avoid confusion, use these terms:

| Term | Meaning |
|------|---------|
| **Parallel processing** | Multiple simultaneous API calls (current system) |
| **Multi-image batching** | Multiple images in one API request |
| **Offline batch API** | OpenAI's 24-hour async batch job system |
| **Batch size** | Number of images processed per iteration |
| **Worker count** | ThreadPoolExecutor concurrency level |

## Conclusion

**Current Implementation Status:**
- ✅ **Already optimal** for Fichero's interactive transcription workflow
- ✅ **ThreadPoolExecutor** provides efficient parallel processing
- ✅ **Real-time results** with progress reporting
- ✅ **No changes needed** for current use cases

**Future Enhancements:**
- ⚠️ **Multi-image batching**: Optional optimization for multi-page documents
- ❌ **OpenAI Batch API**: Not suitable for interactive workflows

**Recommendation:** Keep current system, document its design, and consider multi-image batching only if specific use cases emerge.

## References

- [OpenAI Batch API Documentation](https://platform.openai.com/docs/guides/batch)
- [OpenAI Batch Processing Cookbook](https://cookbook.openai.com/examples/batch_processing)
- [Alibaba Cloud Qwen-VL Documentation](https://www.alibabacloud.com/help/en/model-studio/vision)
- [LlamaIndex DashScope Multi-Modal Example](https://docs.llamaindex.ai/en/stable/examples/multi_modal/dashscope_multi_modal/)

---

**Document Version:** 1.0
**Last Updated:** 2025-11-24
**Author:** Claude Code
**Status:** Research Complete
