"""DataWise Tool Layer: Cleaning Tools.

Deterministic, pure functions for deduplication, missing-value imputation,
type casting, and date format standardization.
"""

from typing import Any
import pandas as pd

from backend.core.exceptions import ToolInputError


def _validate_columns_exist(df: pd.DataFrame, columns: list[str] | str) -> list[str]:
    """Helper to validate column existence and prevent injection or KeyErrors."""
    cols = [columns] if isinstance(columns, str) else list(columns)
    available = set(df.columns)
    for col in cols:
        if col not in available:
            raise ToolInputError(
                f"Column '{col}' does not exist in dataset. Available columns: {list(df.columns)}"
            )
    return cols


def drop_duplicates(
    df: pd.DataFrame,
    subset: list[str] | str | None = None,
) -> tuple[pd.DataFrame, int]:
    """Remove duplicate rows from a DataFrame.

    Args:
        df: Input DataFrame.
        subset: Optional column name or list of column names to consider for duplicates.

    Returns:
        Tuple of (deduplicated_df, number_of_rows_removed).

    Raises:
        ToolInputError: If specified subset column does not exist.
    """
    if subset is not None:
        validated_subset = _validate_columns_exist(df, subset)
    else:
        validated_subset = None

    initial_count = len(df)
    result_df = df.drop_duplicates(subset=validated_subset, keep="first").reset_index(drop=True)
    n_removed = initial_count - len(result_df)
    return result_df, n_removed


def handle_missing(
    df: pd.DataFrame,
    columns: list[str] | str,
    strategy: str = "median",
    fill_value: Any = None,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Handle missing (null) values using specified imputation or removal strategy.

    Supported strategies:
    - 'mean': Arithmetic average (numeric columns only).
    - 'median': Median value (for numeric; falls back to mode for categorical/text).
    - 'mode': Most frequent value.
    - 'drop': Remove any row containing null in specified columns.
    - 'fill_value': Fill with explicit constant `fill_value`.

    Args:
        df: Input DataFrame.
        columns: Column name or list of columns to handle.
        strategy: Imputation or drop method.
        fill_value: Explicit value when strategy='fill_value'.

    Returns:
        Tuple of (transformed_df, n_filled_per_column_dict).

    Raises:
        ToolInputError: If column does not exist or strategy is unsupported.
    """
    target_cols = _validate_columns_exist(df, columns)
    valid_strategies = {"mean", "median", "mode", "drop", "fill_value"}
    strat = strategy.lower().strip()
    if strat not in valid_strategies:
        raise ToolInputError(
            f"Unsupported strategy '{strategy}'. Supported strategies: {', '.join(sorted(valid_strategies))}."
        )

    result_df = df.copy()
    n_filled_per_column: dict[str, int] = {}

    if strat == "drop":
        initial_len = len(result_df)
        for col in target_cols:
            n_filled_per_column[col] = int(result_df[col].isna().sum())
        result_df = result_df.dropna(subset=target_cols).reset_index(drop=True)
        return result_df, n_filled_per_column

    for col in target_cols:
        null_count = int(result_df[col].isna().sum())
        n_filled_per_column[col] = null_count
        if null_count == 0:
            continue

        non_null = result_df[col].dropna()
        impute_val: Any = None

        if strat == "mean":
            if not pd.api.types.is_numeric_dtype(result_df[col]):
                raise ToolInputError(f"Cannot calculate mean on non-numeric column '{col}'.")
            impute_val = non_null.mean() if len(non_null) > 0 else 0.0

        elif strat == "median":
            if pd.api.types.is_numeric_dtype(result_df[col]):
                impute_val = non_null.median() if len(non_null) > 0 else 0.0
            else:
                # Sensible default fallback for categorical/text columns
                modes = non_null.mode()
                impute_val = modes.iloc[0] if len(modes) > 0 else (fill_value or "")

        elif strat == "mode":
            modes = non_null.mode()
            impute_val = modes.iloc[0] if len(modes) > 0 else (fill_value or "")

        elif strat == "fill_value":
            impute_val = fill_value

        result_df[col] = result_df[col].fillna(impute_val)

    return result_df, n_filled_per_column


def fix_type_mismatches(
    df: pd.DataFrame,
    column: str,
    target_type: str,
) -> pd.DataFrame:
    """Cast a column to a specified target data type.

    Args:
        df: Input DataFrame.
        column: Name of column to cast.
        target_type: 'numeric', 'float', 'int', 'string', 'date', 'bool'.

    Returns:
        DataFrame with transformed column.

    Raises:
        ToolInputError: If column does not exist or target_type is unsupported.
    """
    _validate_columns_exist(df, column)
    result_df = df.copy()
    tt = target_type.lower().strip()

    try:
        if tt in {"numeric", "float"}:
            result_df[column] = pd.to_numeric(result_df[column], errors="coerce")
        elif tt in {"int", "integer"}:
            result_df[column] = pd.to_numeric(result_df[column], errors="coerce").astype("Int64")
        elif tt in {"str", "string", "text"}:
            result_df[column] = result_df[column].astype(str)
        elif tt in {"date", "datetime"}:
            result_df[column] = pd.to_datetime(result_df[column], errors="coerce")
        elif tt in {"bool", "boolean"}:
            result_df[column] = result_df[column].astype(bool)
        else:
            supported = "numeric, float, int, string, date, bool"
            raise ToolInputError(
                f"Unsupported target type '{target_type}'. Supported types: {supported}."
            )
    except ToolInputError:
        raise
    except Exception as e:
        raise ToolInputError(f"Failed to cast column '{column}' to '{target_type}': {str(e)}")

    return result_df


def standardize_dates(
    df: pd.DataFrame,
    column: str,
    target_format: str = "%Y-%m-%d",
) -> pd.DataFrame:
    """Standardize mixed or irregular date strings in a column into a uniform format.

    Args:
        df: Input DataFrame.
        column: Column containing date representations.
        target_format: strftime format string (default: ISO '%Y-%m-%d').

    Returns:
        DataFrame with standardized date strings.

    Raises:
        ToolInputError: If column does not exist.
    """
    _validate_columns_exist(df, column)
    result_df = df.copy()

    try:
        # Convert to datetime using flexible parsing
        dt_series = pd.to_datetime(result_df[column], format="mixed", errors="coerce")
        # Format back to target string format, preserving nulls
        result_df[column] = dt_series.dt.strftime(target_format)
    except Exception as e:
        raise ToolInputError(f"Failed to standardize dates in column '{column}': {str(e)}")

    return result_df
