"""Registry for file processors."""

from backend.core.file_detection import FileCategory
from backend.processors.base import FileProcessor


class UnsupportedFileTypeError(Exception):
    """Raised when no processor is registered for a file category."""
    pass


_PROCESSOR_REGISTRY: dict[FileCategory, FileProcessor] = {}


def register_processor(category: FileCategory, processor: FileProcessor) -> None:
    """Register a processor instance for a specific file category."""
    _PROCESSOR_REGISTRY[category] = processor


def get_processor(category: FileCategory) -> FileProcessor:
    """Get the registered processor for a category.
    
    Raises:
        UnsupportedFileTypeError: If no processor is registered.
    """
    if category not in _PROCESSOR_REGISTRY:
        raise UnsupportedFileTypeError(f"No processor registered for category: {category}")
    return _PROCESSOR_REGISTRY[category]


def list_registered_categories() -> list[FileCategory]:
    """Return all categories currently registered with a processor."""
    return list(_PROCESSOR_REGISTRY.keys())

