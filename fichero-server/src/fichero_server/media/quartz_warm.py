"""Resolve every Quartz name the engine uses, once, before the first use (#5745).

PyObjC loads `Quartz.<name>` lazily and that is not thread-safe: two page reads touching a
name for the first time at once raised a bare KeyError('CGImageGetWidth'). `warm()` resolves
them under a lock, so whichever thread comes first does it and the rest wait. It is called where
Quartz is first used, never at import: importing Quartz costs the user ~0.2 s before the window
opens (#3950, `test_lazy_engine_imports`).
"""
import threading

NAMES = (
    "CGBitmapContextCreate",
    "CGBitmapContextCreateImage",
    "CGColorSpaceCreateDeviceRGB",
    "CGColorSpaceCreateWithName",
    "CGContextDrawPDFPage",
    "CGContextFillRect",
    "CGContextScaleCTM",
    "CGContextSetRGBFillColor",
    "CGDataProviderCopyData",
    "CGEventSourceSecondsSinceLastEventType",
    "CGImageCreateWithImageInRect",
    "CGImageDestinationAddImage",
    "CGImageDestinationCreateWithURL",
    "CGImageDestinationFinalize",
    "CGImageGetDataProvider",
    "CGImageGetHeight",
    "CGImageGetWidth",
    "CGImageSourceCopyPropertiesAtIndex",
    "CGImageSourceCreateImageAtIndex",
    "CGImageSourceCreateWithURL",
    "CGPDFDocumentCreateWithURL",
    "CGPDFDocumentGetNumberOfPages",
    "CGPDFDocumentGetPage",
    "CGPDFPageGetBoxRect",
    "CGRectMake",
    "kCGAnyInputEventType",
    "kCGColorSpaceGenericRGB",
    "kCGEventSourceStateCombinedSessionState",
    "kCGImageAlphaPremultipliedLast",
    "kCGPDFCropBox",
    "kCGPDFMediaBox",
    "kUTTypePNG",
)

_lock = threading.Lock()
_done = False


def warm() -> None:
    """Idempotent and thread-safe; a no-op off macOS."""
    global _done
    if _done:
        return
    with _lock:
        if _done:
            return
        try:
            import Quartz

            for name in NAMES:
                getattr(Quartz, name, None)  # a name this macOS lacks stays the caller's own error
        except ImportError:  # not macOS: nothing to warm
            pass
        _done = True
