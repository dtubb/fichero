"""Resolve every Quartz name the engine uses, once, at import (#5745).

PyObjC loads `Quartz.<name>` lazily and that is not thread-safe: two page reads touching a
name for the first time at once raised a bare KeyError('CGImageGetWidth'). Python's import lock
serialises this module's first import, so importing it before any thread starts is enough.
"""
NAMES = (
    "CGBitmapContextCreate", "CGBitmapContextCreateImage", "CGColorSpaceCreateDeviceRGB",
    "CGContextDrawPDFPage", "CGContextFillRect", "CGContextScaleCTM", "CGContextSetRGBFillColor",
    "CGDataProviderCopyData", "CGImageCreateWithImageInRect", "CGImageDestinationAddImage",
    "CGImageDestinationCreateWithURL", "CGImageDestinationFinalize", "CGImageGetDataProvider",
    "CGImageGetHeight", "CGImageGetWidth", "CGImageSourceCopyPropertiesAtIndex",
    "CGImageSourceCreateImageAtIndex", "CGImageSourceCreateWithURL", "CGPDFDocumentCreateWithURL",
    "CGPDFDocumentGetNumberOfPages", "CGPDFDocumentGetPage", "CGPDFPageGetBoxRect", "CGRectMake",
    "kCGPDFMediaBox",
)

try:
    import Quartz

    for _name in NAMES:
        getattr(Quartz, _name)
except ImportError:  # not macOS: nothing to warm
    pass
