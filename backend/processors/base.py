"""Base interface for all file processors."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Tuple

from backend.models.schemas import Objective


class FileProcessor(ABC):
    """Abstract base class for all file format processors."""

    @abstractmethod
    def profile(self, file_path: Path, session_id: str = "") -> dict:
        """Extract a structured schema/metadata profile for the file."""
        pass

    @abstractmethod
    def validate_input(self, file_path: Path, operation: Objective) -> Tuple[bool, str]:
        """Check if the given operation is valid for this file."""
        pass

    @abstractmethod
    def execute(self, file_path: Path, structured_operation: Any, **kwargs) -> Any:
        """Execute the structured operation against the file.
        Returns an ExecutionResult (or processor-specific result).
        """
        pass

    @abstractmethod
    def validate_output(self, before_state: Any, after_state: Any, structured_operation: Any, **kwargs) -> Any:
        """Validate that the operation correctly transformed the state.
        Returns a ValidationResult.
        """
        pass

    @abstractmethod
    def export(self, state: Any, output_format: str, output_dir: Path, **kwargs) -> Path:
        """Export the final state to disk."""
        pass

    @abstractmethod
    def cleanup(self, session_id: str) -> None:
        """Clean up any temporary resources."""
        pass
