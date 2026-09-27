"""File processors package."""

from backend.core.file_detection import FileCategory
from backend.processors.registry import register_processor
from backend.processors.tabular import TabularProcessor
from backend.processors.document import DocumentProcessor
from backend.processors.image import ImageProcessor
from backend.processors.audio import AudioProcessor
from backend.processors.video import VideoProcessor
from backend.processors.archive import ArchiveProcessor

# Register default processors
register_processor(FileCategory.TABULAR, TabularProcessor())
register_processor(FileCategory.DOCUMENT, DocumentProcessor())
register_processor(FileCategory.IMAGE, ImageProcessor())
register_processor(FileCategory.AUDIO, AudioProcessor())
register_processor(FileCategory.VIDEO, VideoProcessor())
register_processor(FileCategory.ARCHIVE, ArchiveProcessor())
