# AI Background Removal Models

This directory caches the AI models used for background removal when the `ai` method is selected.

## Model Details

- **Default Model**: Used for high-quality background removal (⚡ 1.34s on test documents)
- **Model Size**: ~176MB downloaded on first use
- **Format**: ONNX models for cross-platform compatibility

## Configuration

To use AI background removal, set in your configuration:

```yaml
background_removal_method: "ai"  # Instead of "opencv"
```

## Performance Comparison

| Method  | Speed    | Quality | Use Case |
|---------|----------|---------|----------|
| `opencv` | 0.68s    | Good    | Fast document processing, black backgrounds |
| `ai`     | 1.34s    | Excellent | High-quality results, any background type |

## Storage

Models are automatically downloaded and cached here on first use. This avoids re-downloading the model for every processing session.

**Note**: This directory will be created automatically when AI background removal is first used. 