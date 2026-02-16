# AI Background Removal Models

This directory caches the AI models used for background removal when the `ai` method is selected.

## Available AI Models

| Model | Speed | Best For | Description |
|-------|-------|----------|-------------|
| `default` | 1.34s | Balanced performance | Best overall choice for most documents |
| `u2net_human` | 1.40s | People/portraits | Optimized for images with people |
| `silueta` | 1.47s | Fast processing | Good balance of speed and quality |
| `u2net` | 1.52s | General purpose | Works well on various image types |

## Configuration

To use AI background removal:

```yaml
background_removal_method: "ai"
background_removal_ai_model: "default"  # or "u2net", "u2net_human", "silueta"
```

## Performance Comparison

| Method | Speed | Quality | Use Case |
|--------|-------|---------|----------|
| `opencv` | 0.68s | Good | Fast document processing, black backgrounds |
| `ai` models | 1.3-1.5s | Excellent | High-quality results, any background type |

## Model Details

- **Model Size**: ~176MB each, downloaded on first use
- **Format**: ONNX models for cross-platform compatibility
- **Caching**: Models are cached here to avoid re-downloading

## Storage

Models are automatically downloaded and cached here on first use. Each model is downloaded separately when first selected. 