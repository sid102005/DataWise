"""Tabular format processor."""

from pathlib import Path
from typing import Any, Tuple
import pandas as pd

from backend.models.schemas import Objective, Plan, ExecutionResult, ValidationResult
from backend.processors.base import FileProcessor

from backend.core.understanding import DataUnderstanding
from backend.core.executor import execute_plan, ExecutionError
from backend.core.validator import validate
from backend.core.output import export_result_file


class TabularProcessor(FileProcessor):
    """Processor for tabular files (CSV, XLSX, JSON)."""

    def __init__(self):
        self._df_cache: dict[Path, pd.DataFrame] = {}
        self._original_df: dict[Path, pd.DataFrame] = {}

    def _load_df(self, file_path: Path) -> pd.DataFrame:
        if file_path in self._df_cache:
            return self._df_cache[file_path]
            
        ext = file_path.suffix.lower().lstrip(".")
        # Let's use DataUnderstanding's parse_dataframe to ensure consistency with pipeline
        df, _ = DataUnderstanding.parse_dataframe(file_path, format_type=ext)
        self._df_cache[file_path] = df
        self._original_df[file_path] = df.copy(deep=True)
        return df

    def profile(self, file_path: Path, session_id: str = "") -> dict:
        df = self._load_df(file_path)
        ext = file_path.suffix.lower().lstrip(".")
        
        # We need to construct the profile using the cached df, not reading from disk again
        # parse_dataframe is static, but infer_column_types takes df
        columns = DataUnderstanding.infer_column_types(df)
        
        dup_count = df.duplicated().sum()
        profile = {
            "file_format": ext,
            "encoding": "utf-8",
            "row_count": len(df),
            "column_count": len(df.columns),
            "duplicate_row_count": dup_count,
            "duplicate_percentage": round((dup_count / len(df)) * 100, 2) if len(df) > 0 else 0.0,
            "columns": [c.model_dump() for c in columns],
            "sheet_names": [],
            "quality_flags": []
        }
        return profile

    def validate_input(self, file_path: Path, operation: Any) -> Tuple[bool, str]:
        try:
            self._load_df(file_path)
        except Exception as e:
            return False, f"Failed to load file: {e}"
        return True, ""

    def execute(self, file_path: Path, structured_operation: Any, **kwargs) -> Any:
        """structured_operation is a Plan in this context."""
        df = self._load_df(file_path)
        output_dir = kwargs.get("output_dir", file_path.parent)
        
        try:
            # Pass working df (a copy so we don't modify the cache inadvertently if executor mutates)
            final_df, step_results, chart_paths = execute_plan(df.copy(), structured_operation, output_dir=output_dir)
            
            # CACHE INVALIDATION: Update the cache so subsequent reads get the new state
            self._df_cache[file_path] = final_df
            
            return {
                "final_df": final_df,
                "step_results": step_results,
                "chart_paths": chart_paths,
                "plan": structured_operation
            }
        except Exception as e:
            # Re-raise to let the pipeline handle it, or wrap it
            raise e

    def validate_output(self, before_state: Any, after_state: Any, structured_operation: Any, **kwargs) -> ValidationResult:
        # before_state is typically the file_path in our pipeline usage
        if isinstance(before_state, Path):
            if before_state in self._original_df:
                original_df = self._original_df[before_state]
            else:
                original_df = self._load_df(before_state)
        else:
            original_df = before_state
            
        result_df = after_state["final_df"]
        plan = after_state["plan"]
        step_results = after_state["step_results"]
        chart_paths = after_state["chart_paths"]
        
        retry_count = kwargs.get("retry_count", 0)
        max_retries = kwargs.get("max_retries", 2)
        
        validation = validate(
            original_df=original_df,
            result_df=result_df,
            plan=plan,
            step_results=step_results,
            chart_paths=chart_paths,
            retry_count=retry_count,
            max_retries=max_retries
        )
        return validation

    def export(self, state: Any, output_format: str, output_dir: Path, **kwargs) -> Path:
        result_df = state["final_df"]
        filename_stem = kwargs.get("filename_stem", "result")
        exported_path = export_result_file(result_df, output_dir, fmt=output_format, filename_stem=filename_stem)
        return exported_path

    def cleanup(self, session_id: str) -> None:
        self._df_cache.clear()
        self._original_df.clear()
