# TODO-076: Model Comparison Top-Level View

## Summary
Add a new top-level sidebar mode for comparing AI model responses side-by-side.

## Requirements

### User Goals
- Compare responses from multiple AI models to the same prompt
- Compare pricing across models
- Test vision models with images
- See diff between responses

### UI Layout
```
┌─────────────────────────────────────────────────────────────────────┐
│ Sidebar        │  Input Panel            │  Results Comparison     │
│                │                         │                         │
│ ● Navigate     │  ┌─────────────────────┐│  ┌─────────┬─────────┐  │
│ ● Search       │  │ Prompt text...      ││  │ GPT-4o  │ Claude  │  │
│ ● Chat         │  │                     ││  │         │         │  │
│ ● Workflows    │  └─────────────────────┘│  │ Response│ Response│  │
│ ● Compare ←NEW │                         │  │ here... │ here... │  │
│ ● Activity     │  ┌─────────────────────┐│  │         │         │  │
│                │  │ Drag image here     ││  │ $0.002  │ $0.003  │  │
│ Models to test:│  │                     ││  └─────────┴─────────┘  │
│ ☑ GPT-4o       │  └─────────────────────┘│                         │
│ ☑ Claude 3.5   │                         │  [Diff View] [Side by]  │
│ ☐ Gemini Pro   │  [Run Comparison]       │                         │
│                │                         │  Image Preview:         │
│                │  Pricing estimate:      │  ┌─────────────────┐    │
│                │  ~$0.005 total          │  │    [image]      │    │
└─────────────────────────────────────────────────────────────────────┘
```

### Features
1. **Model Selection**: Multi-select from configured models (with pricing shown)
2. **Input Panel**:
   - Text prompt area
   - Image drop zone (for vision model testing)
   - Cost estimate before running
3. **Results Panel**:
   - Side-by-side view (2+ columns)
   - Diff view (text diff between two responses)
   - Per-model: response, tokens, cost, latency
4. **Image Preview**: Show the input image alongside results

## Implementation Steps

### Backend
1. Create `POST /api/compare/run` endpoint
   - Input: prompt, image (optional), model_ids[]
   - Output: streaming results from each model in parallel
   - Include: tokens used, cost, latency per model
2. Add comparison history storage (optional)

### Frontend
1. Add `compare` case to `SidebarMode` enum
2. Add `compare` case to `AppViewMode` enum
3. Create `CompareView` main view
4. Create `CompareInputPanel` (prompt + image)
5. Create `ModelSelector` (checkboxes with pricing)
6. Create `CompareResultsView` (side-by-side cards)
7. Create `CompareResultCard` (individual model result)
8. Create `DiffView` (text diff between two responses)
9. Wire up streaming via SSE

## Dependencies
- Providers must be configured with models
- LiteLLM pricing data

## Priority
P2 - Medium (nice to have, not blocking core workflows)

## Estimate
3-5 days
