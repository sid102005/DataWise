"""DataWise Pydantic Data Contracts and Models.

Defines the core data structures used across all stages of the DataWise pipeline:
Data Understanding, Intent Understanding, Task Planning, Execution, Validation,
and Output Delivery.
"""

from enum import Enum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class InferredType(str, Enum):
    """Semantic data type inferred for a tabular column."""
    NUMERIC = "numeric"
    DATE = "date"
    CATEGORICAL = "categorical"
    ID = "id"
    TEXT = "text"


class ObjectiveCategory(str, Enum):
    """Allowed objective categories from flow.md Stage 2."""
    CLEAN = "clean"
    TRANSFORM = "transform"
    AGGREGATE = "aggregate"
    STAT = "stat"
    ML = "ml"
    VISUALIZE = "visualize"
    EXTRACT = "extract"
    COMPARE = "compare"
    REPORT = "report"


class PipelineStatus(str, Enum):
    """Execution status for the end-to-end pipeline."""
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    NEEDS_CLARIFICATION = "needs_clarification"
    FAILED = "failed"


class ColumnInfo(BaseModel):
    """Detailed metadata and inferred semantic profile for a single column."""
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Column header name")
    inferred_type: InferredType = Field(..., description="Inferred semantic category")
    raw_dtype: str = Field(..., description="Underlying pandas/numpy data type string")
    null_count: int = Field(..., ge=0, description="Count of missing/null values")
    null_percentage: float = Field(..., ge=0.0, le=100.0, description="Percentage of missing values (0-100)")
    unique_count: int = Field(..., ge=0, description="Number of distinct non-null values")
    quality_issues: list[str] = Field(default_factory=list, description="Specific quality issues detected")


class DataProfile(BaseModel):
    """Metadata-only profile of an uploaded tabular dataset.

    Note: Per architectural decision, this profile transmits schema and statistical
    metadata only (no raw cell content) to uphold user privacy and token boundaries.
    """
    model_config = ConfigDict(extra="allow")

    file_format: Literal[
        "csv", "xlsx", "json",
        "pdf", "docx", "txt", "md",
        "jpg", "jpeg", "png", "gif", "bmp", "webp", "tiff", "tif",
        "mp3", "wav",
        "mp4", "mov", "avi", "mkv", "webm",
        "zip", "tar", "gz", "tgz"
    ] = Field(..., description="Validated file format extension")
    encoding: str = Field(default="utf-8", description="File text character encoding")
    # Tabular fields
    row_count: int | None = Field(default=None, ge=0, description="Total number of rows in the dataset")
    column_count: int | None = Field(default=None, ge=0, description="Total number of columns")
    duplicate_row_count: int | None = Field(default=None, ge=0, description="Count of duplicate rows")
    duplicate_percentage: float | None = Field(default=None, ge=0.0, le=100.0, description="Percentage of duplicate rows (0-100)")
    columns: list[ColumnInfo] | None = Field(default=None, description="Per-column schema and quality profiles")
    sheet_names: list[str] = Field(default_factory=list, description="Available sheet names for multi-sheet workbooks")
    quality_flags: list[str] = Field(default_factory=list, description="Global dataset quality observations")
    
    # Document fields
    page_count: int | None = Field(default=None, ge=0, description="Number of pages in the document")
    paragraph_count: int | None = Field(default=None, ge=0, description="Number of paragraphs in the document")
    word_count: int | None = Field(default=None, ge=0, description="Total number of words")
    has_text_layer: bool | None = Field(default=None, description="Whether the document has a machine-readable text layer")

    # Image fields
    width: int | None = Field(default=None, ge=0, description="Image width in pixels")
    height: int | None = Field(default=None, ge=0, description="Image height in pixels")
    color_mode: str | None = Field(default=None, description="Image color mode (e.g. RGB, RGBA, L, P)")

    # Audio fields
    duration_seconds: float | None = Field(default=None, ge=0.0, description="Audio duration in seconds")
    sample_rate: int | None = Field(default=None, ge=0, description="Audio sample rate in Hz")
    channels: int | None = Field(default=None, ge=0, description="Number of audio channels")
    sample_width: int | None = Field(default=None, ge=0, description="Audio sample width in bytes")
    bitrate: int | None = Field(default=None, ge=0, description="Audio bitrate in bps")

    @model_validator(mode="after")
    def validate_tabular_guarantees(self) -> "DataProfile":
        if self.file_format in {"csv", "xlsx", "json"}:
            if self.row_count is None or self.column_count is None:
                raise ValueError(f"Tabular profiles must have non-null row_count and column_count. Format: {self.file_format}")
        return self


class Objective(BaseModel):
    """A discrete goal parsed from the user's natural language prompt."""
    model_config = ConfigDict(extra="forbid")

    category: ObjectiveCategory = Field(..., description="Standardized operation category")
    description: str = Field(..., description="Plain-English description of what this objective achieves")
    target_columns: list[str] = Field(default_factory=list, description="Columns targeted by this operation")
    parameters: dict[str, str | int | float | bool | list[str]] = Field(
        default_factory=dict,
        description="Structured arguments extracted for this objective"
    )


class Step(BaseModel):
    """An atomic, ordered execution step mapping 1:1 to a tool-layer function."""
    model_config = ConfigDict(extra="forbid")

    step_number: int = Field(..., ge=1, description="1-indexed sequence order")
    tool_name: str = Field(..., description="Exact registered name of tool in backend/tools/")
    description: str = Field(..., description="Human-readable explanation of this step")
    parameters: dict[str, str | int | float | bool | list[str] | dict | None] = Field(
        default_factory=dict,
        description="Arguments passed to the tool function"
    )
    expected_output: str = Field(..., description="Expected state condition after step execution")


class Plan(BaseModel):
    """The inspectable task plan produced by Stage 3."""
    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(..., description="Unique identifier for this plan")
    session_id: str = Field(..., description="Session identifier this plan belongs to")
    objectives: list[Objective] = Field(..., description="List of parsed user objectives")
    steps: list[Step] = Field(..., description="Ordered sequence of executable steps")
    needs_clarification: bool = Field(default=False, description="Whether execution is paused for user input")
    clarification_question: str | None = Field(default=None, description="Question for the user if ambiguous")
    revision_count: int = Field(default=0, ge=0, description="Number of times this plan has been revised")
    rationale: str = Field(default="", description="High-level reasoning explaining why this plan was constructed")


class ExecutionResult(BaseModel):
    """Execution telemetry captured for a single tool-layer step."""
    model_config = ConfigDict(extra="forbid")

    step_number: int = Field(..., ge=1, description="Step number corresponding to Plan.steps")
    tool_name: str = Field(..., description="Name of executed tool")
    success: bool = Field(..., description="Whether tool execution completed without error")
    rows_before: int = Field(..., ge=0, description="Row count before step")
    rows_after: int = Field(..., ge=0, description="Row count after step")
    columns_before: int = Field(..., ge=0, description="Column count before step")
    columns_after: int = Field(..., ge=0, description="Column count after step")
    summary: str = Field(..., description="Plain-English explanation of changes performed by tool")
    error_message: str | None = Field(default=None, description="Diagnostic error string if failed")
    execution_time_ms: float = Field(default=0.0, ge=0.0, description="Elapsed wall-clock time in milliseconds")


class ValidationResult(BaseModel):
    """Post-execution validation report evaluating dataset sanity and plan fulfillment."""
    model_config = ConfigDict(extra="forbid")

    is_valid: bool = Field(..., description="True if all sanity and expectation checks passed")
    checks_passed: list[str] = Field(default_factory=list, description="Names of passed checks")
    checks_failed: list[str] = Field(default_factory=list, description="Names of failed checks")
    details: dict[str, str] = Field(default_factory=dict, description="Detailed diagnostic comments per check")
    can_retry: bool = Field(default=False, description="Whether plan revision retry is possible")
    retry_count: int = Field(default=0, ge=0, description="Current retry attempt number")
    max_retries: int = Field(default=2, ge=1, description="Maximum allowable retry attempts")


class BatchItemResult(BaseModel):
    """Execution and validation report for an individual file in a batch request."""
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(..., description="Original filename of the batch item")
    status: str = Field(..., description="Item status: 'success', 'failed', or 'excluded'")
    category: str = Field(..., description="Detected file category")
    reason: str | None = Field(default=None, description="Explanation for exclusion or failure")
    output_filename: str | None = Field(default=None, description="Filename in the packaged result archive")
    validation_passed: bool | None = Field(default=None, description="Whether item-level validation passed")
    details: dict[str, str] = Field(default_factory=dict, description="Diagnostic details")


class BatchSummary(BaseModel):
    """Aggregated metrics across a multi-file batch execution."""
    model_config = ConfigDict(extra="forbid")

    total_files: int = Field(..., ge=0, description="Total number of uploaded files in batch")
    processed_count: int = Field(..., ge=0, description="Count of files where operation was attempted")
    succeeded_count: int = Field(..., ge=0, description="Count of files successfully processed and validated")
    failed_count: int = Field(..., ge=0, description="Count of files that failed processing or validation")
    excluded_count: int = Field(..., ge=0, description="Count of files excluded due to incompatible type")


class PipelineOutput(BaseModel):
    """Final delivery payload returned to the user interface."""
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Session identifier")
    status: PipelineStatus = Field(..., description="Overall execution status")
    summary: str = Field(..., description="Plain-English summary of what was accomplished")
    result_file_path: str | None = Field(default=None, description="Absolute or relative path to processed artifact")
    result_filename: str | None = Field(default=None, description="Downloadable file basename")
    download_url: str | None = Field(default=None, description="API endpoint to download result file")
    preview_rows: list[dict[str, str | int | float | bool | None]] = Field(
        default_factory=list,
        description="Tabular preview rows (first N records)"
    )
    preview_columns: list[str] = Field(default_factory=list, description="Ordered list of column names in preview")
    total_rows: int | None = Field(default=None, ge=0, description="Total rows in final dataset")
    chart_paths: list[str] = Field(default_factory=list, description="Paths to generated chart images")
    executed_plan: Plan | None = Field(default=None, description="Audit plan that was executed")
    validation: ValidationResult | None = Field(default=None, description="Validation report")
    errors: list[str] = Field(default_factory=list, description="Sanitized plain-English error messages")
    batch_results: list[BatchItemResult] | None = Field(default=None, description="Per-file status report for batch processing")
    batch_summary: BatchSummary | None = Field(default=None, description="Aggregated summary metrics for batch processing")


class ErrorResponse(BaseModel):
    """Standardized error structure returned on client or server failure."""
    model_config = ConfigDict(extra="forbid")

    error: bool = Field(default=True, description="Always true for error responses")
    status: str = Field(default="error", description="Standard error status string")
    error_code: str = Field(..., description="Machine-readable error identifier")
    message: str = Field(..., description="Human-friendly, plain-English explanation")
    details: str | None = Field(default=None, description="Non-sensitive supplementary details")


class ClarificationRequest(BaseModel):
    """Prompt emitted when user intent or data structure is genuinely ambiguous."""
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Session identifier")
    question: str = Field(..., description="Targeted question asking the user to resolve ambiguity")
    context: str = Field(..., description="Background explanation of why clarification is required")
    options: list[str] = Field(default_factory=list, description="Suggested answers for the user")
    default_choice: str | None = Field(default=None, description="Safe default action taken if user proceeds")
    affected_column: str | None = Field(default=None, description="Name of the affected column, if applicable")
