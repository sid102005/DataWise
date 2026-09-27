"""DataWise Core Exception Classes."""


class DataWiseError(Exception):
    """Base exception for all DataWise domain errors."""

    def __init__(self, message: str, details: str | None = None):
        super().__init__(message)
        self.message = message
        self.details = details


class FileValidationError(DataWiseError):
    """Raised when an uploaded file violates format, size, or security constraints."""
    pass


class ArchiveSecurityError(FileValidationError):
    """Raised when an archive fails security checks (zip-slip, archive bomb, symlinks)."""
    pass


class ParsingError(DataWiseError):
    """Raised when an uploaded file cannot be parsed into a tabular DataFrame."""
    pass


class ToolInputError(DataWiseError):
    """Raised when an invalid column, operator, or argument is provided to a tool function."""
    pass


class ExecutionError(DataWiseError):
    """Raised when plan step execution fails in the tool layer."""
    pass


class DataWiseValidationError(DataWiseError):
    """Raised when post-execution validation fails."""
    pass


class LLMBudgetExceededError(DataWiseError):
    """Raised when the per-request LLM call budget is exhausted."""
    pass

