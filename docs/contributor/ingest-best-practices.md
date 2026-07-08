(AI generated. Not reviewed.)

# Ingest Best Practices

Guidelines and recommendations for effective use of the Fichero ingest module.

## General Recommendations

### Mode Selection

**Use LINK mode when:**
- Working with very large files (>100MB)
- Files are on fast, reliable storage
- You want to save storage space
- Files may be updated externally
- You need to preserve original file locations

**Use COPY mode when:**
- Files should be preserved independently
- You need portable libraries
- Working with removable media
- Files may be deleted from original locations
- You want consistent performance

### Performance Optimization

**For large file collections:**
- Use batch processing with `ingest_folder()`
- Enable recursive processing for nested directories
- Consider parallel processing for independent files
- Use progress callbacks for user feedback

**For memory management:**
- Process files in reasonable batches (100-500 at a time)
- Disable text extraction for non-searchable files
- Use generators for file discovery
- Monitor memory usage during large operations

### Error Handling

**Best practices:**
- Implement comprehensive try-catch blocks
- Log detailed error information
- Provide user-friendly error messages
- Implement recovery mechanisms
- Validate inputs before processing

```python
try:
    docs = ingest_folder(Path("/path/to/folder"))
    logger.info(f"Successfully ingested {len(docs)} files")
except FileNotFoundError as e:
    logger.error(f"Folder not found: {e}")
    # Notify user
except Exception as e:
    logger.error(f"Ingestion failed: {e}")
    # Implement recovery
```

## File Type Specific Guidelines

### Image Files

**Best practices:**
- Enable metadata extraction for EXIF data
- Use COPY mode for important images
- Consider LINK mode for large image libraries
- Extract dimensions for thumbnail generation

**Example:**
```python
# Ingest image with full metadata
doc = ingest_file(
    Path("/path/to/photo.jpg"),
    mode=IngestMode.COPY,
    extract_metadata=True  # Includes EXIF data
)
```

### Document Files

**Best practices:**
- Always enable text extraction for searchability
- Use COPY mode for important documents
- Consider embedding for semantic search
- Extract metadata for organization

**Example:**
```python
# Ingest document with search optimization
doc = ingest_file(
    Path("/path/to/document.pdf"),
    mode=IngestMode.COPY,
    extract_text=True,
    auto_embed=True
)
```

### Media Files

**Best practices:**
- Use LINK mode for large video/audio files
- Disable text extraction (not applicable)
- Extract basic metadata for organization
- Consider storage implications

**Example:**
```python
# Ingest media file efficiently
doc = ingest_file(
    Path("/path/to/video.mp4"),
    mode=IngestMode.LINK,
    extract_text=False  # Not applicable for video
)
```

## Folder Ingestion Strategies

### Large Folder Processing

**Recommendations:**
- Use recursive processing for nested structures
- Implement progress tracking
- Consider batch processing
- Monitor performance metrics

**Example:**
```python
def progress_callback(current, total):
    if current % 100 == 0:  # Update every 100 files
        print(f"Processed {current}/{total} files")

docs = ingest_folder(
    Path("/large/folder"),
    recursive=True,
    on_progress=progress_callback
)
```

### Selective File Processing

**Recommendations:**
- Use `discover_files()` for filtering
- Process specific file types separately
- Implement custom logic for different types

**Example:**
```python
# Process only images
image_extensions = {".jpg", ".png", ".gif", ".webp"}
for file_path in discover_files(Path("/folder"), extensions=image_extensions):
    ingest_file(file_path, mode=IngestMode.COPY)
```

### Hierarchy Preservation

**Recommendations:**
- Use recursive mode for complex structures
- Let system create folder hierarchy automatically
- Consider custom parent collections

**Example:**
```python
# Preserve folder structure
docs = ingest_folder(
    Path("/complex/folder/structure"),
    recursive=True,
    create_collection=True
)
```

## Text Extraction Best Practices

### When to Extract Text

**Enable text extraction for:**
- PDF documents
- Word processing files (.doc, .docx, .odt)
- Text files (.txt, .md, .rst)
- EPUB ebooks
- Files that need to be searchable

**Disable text extraction for:**
- Image files
- Audio/video files
- Binary files
- Very large documents (>50MB)
- Files where text isn't needed

### Memory Management

**For large documents:**
- Process one at a time
- Monitor memory usage
- Consider file size limits
- Implement fallback mechanisms

**Example:**
```python
# Check file size before text extraction
file_size = path.stat().st_size
if file_size < 50 * 1024 * 1024:  # < 50MB
    doc = ingest_file(file_path, extract_text=True)
else:
    doc = ingest_file(file_path, extract_text=False)
```

## Metadata Extraction Guidelines

### Standard Metadata

**Always extract:**
- File size
- Checksum (for deduplication)
- MIME type
- Basic file information

**Example:**
```python
# Standard metadata extraction
doc = ingest_file(
    Path("/path/to/file.jpg"),
    extract_metadata=True  # Default
)
```

### Specialized Metadata

**Extract when applicable:**
- Image dimensions and EXIF data
- Document text length
- File creation/modification dates
- Custom metadata fields

## Deduplication Strategies

### Checksum-Based Deduplication

**Best practices:**
- Use `find_duplicates()` before ingestion
- Compare checksums for identical files
- Implement user confirmation for duplicates
- Consider file modification dates

**Example:**
```python
# Check for duplicates before ingestion
existing_docs = db.query(Document, parent_id=collection_id)
duplicates = find_duplicates(existing_docs)
if duplicates:
    print(f"Found {len(duplicates)} duplicate sets")
```

### Content-Based Deduplication

**Recommendations:**
- Use checksums for binary comparison
- Consider content hashing for text files
- Implement fuzzy matching for similar files
- Provide user options for handling duplicates

## Error Handling Patterns

### Common Error Scenarios

**File not found:**
```python
try:
    doc = ingest_file(Path("/missing/file.pdf"))
except FileNotFoundError:
    logger.warning("File not found, skipping")
```

**Unsupported file type:**
```python
file_type = detect_file_type(file_path)
if file_type == FileType.other:
    logger.info(f"Skipping unsupported file type: {file_path}")
```

**Permission errors:**
```python
try:
    doc = ingest_file(Path("/protected/file.pdf"))
except PermissionError:
    logger.error("Permission denied for file")
```

### Recovery Strategies

**Partial failure handling:**
```python
successful = []
failed = []

for file_path in discover_files(folder):
    try:
        doc = ingest_file(file_path)
        successful.append(doc)
    except Exception as e:
        failed.append((file_path, str(e)))

print(f"Success: {len(successful)}, Failed: {len(failed)}")
```

## Performance Monitoring

### Metrics to Track

- Files processed per second
- Memory usage during operations
- Disk I/O performance
- Text extraction times
- Error rates and types

### Optimization Techniques

**For slow operations:**
- Identify bottlenecks
- Consider parallel processing
- Optimize file system access
- Review text extraction performance

**For memory issues:**
- Reduce batch sizes
- Disable unnecessary features
- Monitor memory usage
- Implement memory limits

## Security Considerations

### File Handling Security

- Validate all file paths
- Check file permissions
- Handle symbolic links carefully
- Implement size limits
- Scan for malicious content

### Data Protection

- Secure sensitive metadata
- Handle personal information carefully
- Implement access controls
- Consider encryption for sensitive files

## Integration Best Practices

### Database Integration

**Recommendations:**
- Use transactions for batch operations
- Implement proper indexing
- Monitor database performance
- Consider batch inserts for large operations

### Search Integration

**Recommendations:**
- Enable text extraction for searchable content
- Use embeddings for semantic search
- Implement proper indexing strategies
- Consider search performance implications

### UI Integration

**Recommendations:**
- Provide progress feedback
- Implement cancellation support
- Show error messages clearly
- Provide detailed logging options

## Maintenance and Updates

### Documentation Updates

- Keep documentation current
- Update for new file types
- Document API changes
- Maintain usage examples

### Version Compatibility

- Test with new Python versions
- Verify library compatibility
- Update dependencies as needed
- Maintain backward compatibility

### Performance Tuning

- Review performance regularly
- Optimize for common use cases
- Update for new hardware
- Monitor resource usage

## Troubleshooting Guide

### Common Issues

**Slow ingestion:**
- Check disk I/O performance
- Review text extraction settings
- Monitor memory usage
- Consider batch size reduction

**Memory errors:**
- Reduce batch sizes
- Disable text extraction
- Monitor memory usage
- Implement memory limits

**File access errors:**
- Check file permissions
- Verify file paths
- Handle symbolic links
- Implement proper error handling

**Deduplication issues:**
- Verify checksum calculation
- Check file content
- Review duplicate detection logic
- Implement user confirmation

### Debugging Techniques

**Logging:**
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

**Profiling:**
```python
import cProfile
cProfile.run("ingest_folder(folder)")
```

**Unit Testing:**
```python
# Test individual components
from fichero.ingest import detect_file_type
assert detect_file_type(Path("test.jpg")) == FileType.image
```

## Migration Guide

### From Older Versions

**Check for:**
- API changes
- New features
- Deprecated functionality
- Performance improvements

### Data Migration

**Considerations:**
- Backup existing data
- Test migration process
- Verify data integrity
- Update documentation

## Future Considerations

### Potential Enhancements

- Parallel processing support
- Additional file type support
- Enhanced metadata extraction
- Improved error recovery
- Advanced deduplication options

### Scalability Planning

- Consider large-scale deployments
- Review performance bottlenecks
- Plan for growth
- Monitor resource usage

## Conclusion

Following these best practices will help ensure:
- Reliable file ingestion
- Optimal performance
- Effective error handling
- Good user experience
- Maintainable code
- Scalable solutions

Always consider the specific requirements of your use case and adjust these recommendations accordingly.